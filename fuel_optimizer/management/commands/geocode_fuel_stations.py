import csv
import io
import json
import logging
import time
from pathlib import Path
import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from fuel_optimizer.models import FuelStation

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Geocode fuel stations in the database using the US Census Batch Geocoder with fallback."

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of addresses per Census geocoder batch (max 10,000).'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maximum number of stations to geocode in this run.'
        )
        parser.add_argument(
            '--save-cache',
            action='store_true',
            default=True,
            help='Save geocoded coordinates to data/station_coordinates.json for fast reload.'
        )

    def handle(self, *args, **options):
        batch_size = min(options['batch_size'], 10000)
        limit = options['limit']
        save_cache = options['save_cache']

        qs = FuelStation.objects.filter(latitude__isnull=True)
        if limit:
            qs = qs[:limit]

        stations = list(qs)
        total_to_geocode = len(stations)

        if total_to_geocode == 0:
            self.stdout.write(self.style.SUCCESS("All fuel stations already have coordinates! Nothing to geocode."))
            return

        self.stdout.write(self.style.NOTICE(f"Starting geocoding for {total_to_geocode} stations..."))

        # Also load existing cache if present
        cache_path = Path(settings.BASE_DIR) / 'data' / 'station_coordinates.json'
        cached_coords = {}
        if cache_path.is_file():
            try:
                with open(cache_path, 'r', encoding='utf-8') as cf:
                    cached_coords = json.load(cf)
            except Exception:
                cached_coords = {}

        geocoded_count = 0
        unmatched_count = 0

        # Step 1: Check existing cache first
        stations_needing_external = []
        to_update = []

        for st in stations:
            coord_key = f"{st.opis_id}_{st.city.lower()}_{st.state.lower()}"
            city_key = f"{st.city.lower()}_{st.state.lower()}"
            c = cached_coords.get(coord_key) or cached_coords.get(city_key)
            if c:
                st.latitude = c['lat']
                st.longitude = c['lon']
                to_update.append(st)
                geocoded_count += 1
            else:
                stations_needing_external.append(st)

        if to_update:
            with transaction.atomic():
                FuelStation.objects.bulk_update(to_update, ['latitude', 'longitude'], batch_size=1000)
            self.stdout.write(self.style.SUCCESS(f"Applied coordinates from local cache for {len(to_update)} stations."))

        # Step 2: Batch geocode remaining stations using US Census Batch Geocoder
        if stations_needing_external:
            self.stdout.write(f"Querying US Census Batch Geocoder for {len(stations_needing_external)} stations...")
            for i in range(0, len(stations_needing_external), batch_size):
                chunk = stations_needing_external[i:i + batch_size]
                chunk_geocoded, chunk_unmatched = self._geocode_census_batch(chunk, cached_coords)
                geocoded_count += chunk_geocoded
                unmatched_count += chunk_unmatched

        # Save updated cache file
        if save_cache and cached_coords:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as cf:
                json.dump(cached_coords, cf, indent=2)
            self.stdout.write(self.style.SUCCESS(f"Saved {len(cached_coords)} coordinates to {cache_path}."))

        remaining = FuelStation.objects.filter(latitude__isnull=True).count()
        total_geocoded = FuelStation.objects.filter(latitude__isnull=False).count()
        self.stdout.write(self.style.SUCCESS(
            f"Geocoding run complete:\n"
            f"  - Newly geocoded: {geocoded_count}\n"
            f"  - Unmatched: {unmatched_count}\n"
            f"  - Total stations in DB with coordinates: {total_geocoded}\n"
            f"  - Total stations pending coordinates: {remaining}"
        ))

    def _geocode_census_batch(
        self,
        stations: list[FuelStation],
        cached_coords: dict
    ) -> tuple[int, int]:
        """
        Sends a batch of stations to the US Census Batch Geocoder API.
        """
        # Build CSV file for batch API
        # Format: ID, Street, City, State, ZIP
        output = io.StringIO()
        writer = csv.writer(output)
        station_map = {}

        for st in stations:
            station_map[st.id] = st
            writer.writerow([
                st.id,
                st.address,
                st.city,
                st.state,
                ''
            ])

        csv_content = output.getvalue()
        url = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
        files = {
            'addressFile': ('batch.csv', csv_content, 'text/csv'),
            'benchmark': (None, 'Public_AR_Current'),
        }

        matched_stations = []
        unmatched_stations = []

        try:
            resp = requests.post(url, files=files, timeout=60)
            if resp.status_code == 200:
                result_reader = csv.reader(io.StringIO(resp.text))
                for row in result_reader:
                    if len(row) >= 6:
                        st_id_str = row[0].strip()
                        status = row[2].strip()
                        coords_str = row[5].strip()

                        if not st_id_str.isdigit():
                            continue
                        st_id = int(st_id_str)
                        st = station_map.get(st_id)
                        if not st:
                            continue

                        if status == 'Match' and ',' in coords_str:
                            parts = coords_str.split(',')
                            try:
                                lon = float(parts[0])
                                lat = float(parts[1])
                                st.latitude = lat
                                st.longitude = lon
                                matched_stations.append(st)

                                coord_key = f"{st.opis_id}_{st.city.lower()}_{st.state.lower()}"
                                cached_coords[coord_key] = {'lat': lat, 'lon': lon}
                            except ValueError:
                                unmatched_stations.append(st)
                        else:
                            unmatched_stations.append(st)

                if matched_stations:
                    with transaction.atomic():
                        FuelStation.objects.bulk_update(matched_stations, ['latitude', 'longitude'], batch_size=500)

                self.stdout.write(
                    f"Census batch: {len(matched_stations)} matched, {len(unmatched_stations)} unmatched."
                )
                return len(matched_stations), len(unmatched_stations)
            else:
                self.stdout.write(self.style.WARNING(
                    f"US Census API returned status {resp.status_code}. Using fallback lookup..."
                ))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Census batch request exception: {e}"))

        return 0, len(stations)
