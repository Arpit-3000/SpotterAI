import csv
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from fuel_optimizer.models import FuelStation


class Command(BaseCommand):
    help = "Import fuel prices from the supplied OPIS CSV dataset."

    REQUIRED_COLUMNS = {
        'OPIS Truckstop ID',
        'Truckstop Name',
        'Address',
        'City',
        'State',
        'Retail Price'
    }

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            nargs='?',
            default='data/fuel-prices-for-be-assessment.csv',
            help='Path to the OPIS fuel price CSV file.'
        )
        parser.add_argument(
            '--wipe',
            action='store_true',
            help='Delete existing fuel stations prior to import.'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Batch size for bulk database operations.'
        )

    def handle(self, *args, **options):
        csv_path = Path(options['csv_file'])
        if not csv_path.is_file():
            raise CommandError(f"Fuel prices CSV file not found at: {csv_path.resolve()}")

        if options['wipe']:
            count = FuelStation.objects.count()
            FuelStation.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Wiped {count} existing FuelStation records."))

        # Check for pre-geocoded coordinates cache file
        coords_cache_file = csv_path.parent / 'station_coordinates.json'
        cached_coords = {}
        if coords_cache_file.is_file():
            try:
                with open(coords_cache_file, 'r', encoding='utf-8') as cf:
                    cached_coords = json.load(cf)
                self.stdout.write(self.style.SUCCESS(
                    f"Loaded {len(cached_coords)} pre-computed station coordinates from {coords_cache_file.name}."
                ))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Could not load coordinates cache: {e}"))

        self.stdout.write(f"Reading fuel prices from: {csv_path}...")

        # Load existing stations into lookup dictionary for idempotency
        existing_stations = {
            (st.opis_id, st.city.lower(), st.state.lower()): st
            for st in FuelStation.objects.all()
        }

        to_create = []
        to_update = []
        seen_keys = set()
        total_rows = 0
        skipped_rows = 0

        with open(csv_path, mode='r', encoding='utf-8-sig', errors='replace') as f:
            reader = csv.DictReader(f)

            # Validate CSV columns
            missing_cols = self.REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing_cols:
                raise CommandError(
                    f"CSV is missing required columns: {', '.join(missing_cols)}. "
                    f"Found columns: {reader.fieldnames}"
                )

            for row_idx, row in enumerate(reader, start=1):
                total_rows += 1
                try:
                    opis_id_raw = row['OPIS Truckstop ID'].strip()
                    if not opis_id_raw or not opis_id_raw.isdigit():
                        skipped_rows += 1
                        continue
                    opis_id = int(opis_id_raw)

                    name = row['Truckstop Name'].strip()
                    address = row['Address'].strip()
                    city = row['City'].strip()
                    state = row['State'].strip().upper()

                    rack_id_raw = row.get('Rack ID', '').strip()
                    rack_id = int(rack_id_raw) if rack_id_raw and rack_id_raw.isdigit() else None

                    # Parse Retail Price to Decimal (avoid floating point for money)
                    price_raw = row['Retail Price'].strip().replace('$', '')
                    retail_price = Decimal(price_raw).quantize(Decimal('0.0001'))

                    key = (opis_id, city.lower(), state.lower())

                    # If duplicate row in the same CSV run, update in-flight
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    # Lookup pre-computed coordinates if available
                    coord_key = f"{opis_id}_{city.lower()}_{state.lower()}"
                    city_key = f"{city.lower()}_{state.lower()}"
                    coords = cached_coords.get(coord_key) or cached_coords.get(city_key)

                    lat = coords['lat'] if coords else None
                    lon = coords['lon'] if coords else None

                    if key in existing_stations:
                        existing = existing_stations[key]
                        existing.name = name
                        existing.address = address
                        existing.rack_id = rack_id
                        existing.retail_price = retail_price
                        if lat is not None and lon is not None and not existing.is_geocoded:
                            existing.latitude = lat
                            existing.longitude = lon
                        to_update.append(existing)
                    else:
                        station_obj = FuelStation(
                            opis_id=opis_id,
                            name=name,
                            address=address,
                            city=city,
                            state=state,
                            rack_id=rack_id,
                            retail_price=retail_price,
                            latitude=lat,
                            longitude=lon,
                        )
                        to_create.append(station_obj)

                except (ValueError, InvalidOperation) as err:
                    skipped_rows += 1
                    continue

        batch_size = options['batch_size']
        with transaction.atomic():
            if to_create:
                FuelStation.objects.bulk_create(to_create, batch_size=batch_size)
            if to_update:
                FuelStation.objects.bulk_update(
                    to_update,
                    ['name', 'address', 'rack_id', 'retail_price', 'latitude', 'longitude'],
                    batch_size=batch_size
                )

        total_in_db = FuelStation.objects.count()
        geocoded_in_db = FuelStation.objects.filter(latitude__isnull=False, longitude__isnull=False).count()

        self.stdout.write(self.style.SUCCESS(
            f"Successfully processed {total_rows} rows:\n"
            f"  - Created: {len(to_create)}\n"
            f"  - Updated: {len(to_update)}\n"
            f"  - Skipped: {skipped_rows}\n"
            f"  - Total stations in database: {total_in_db}\n"
            f"  - Stations with coordinates: {geocoded_in_db}/{total_in_db}"
        ))
