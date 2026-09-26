from decimal import Decimal
from django.db import models


class FuelStation(models.Model):
    """
    Represents a fuel station with its location, metadata, and retail fuel price.
    Data is populated from the OPIS fuel price CSV and enriched via geocoding.
    """
    opis_id = models.IntegerField(
        db_index=True,
        help_text="OPIS Truckstop ID from fuel data"
    )
    name = models.CharField(
        max_length=255,
        help_text="Truckstop brand or business name"
    )
    address = models.CharField(
        max_length=255,
        help_text="Street address or highway junction"
    )
    city = models.CharField(
        max_length=128,
        db_index=True,
        help_text="City name"
    )
    state = models.CharField(
        max_length=10,
        db_index=True,
        help_text="US state two-letter postal abbreviation"
    )
    rack_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="Rack identifier from fuel pricing feed"
    )
    retail_price = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        db_index=True,
        help_text="Retail diesel price in USD per gallon"
    )
    latitude = models.FloatField(
        null=True,
        blank=True,
        db_index=True,
        help_text="WGS-84 latitude in decimal degrees"
    )
    longitude = models.FloatField(
        null=True,
        blank=True,
        db_index=True,
        help_text="WGS-84 longitude in decimal degrees"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fuel_stations'
        ordering = ['state', 'city', 'retail_price']
        indexes = [
            models.Index(fields=['state', 'city'], name='idx_station_state_city'),
            models.Index(fields=['latitude', 'longitude'], name='idx_station_lat_lon'),
            models.Index(fields=['retail_price'], name='idx_station_price'),
        ]

    def __str__(self) -> str:
        return f"{self.name} - {self.city}, {self.state} (${self.retail_price:.2f}/gal)"

    @property
    def is_geocoded(self) -> bool:
        """Returns True if station has valid coordinates."""
        return self.latitude is not None and self.longitude is not None

    @property
    def coordinates(self) -> tuple[float, float] | None:
        """Returns (latitude, longitude) tuple or None."""
        if self.is_geocoded:
            return (self.latitude, self.longitude)
        return None
