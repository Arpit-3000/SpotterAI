import logging
import time
import requests
from typing import Any
from django.conf import settings
from django.core.cache import cache
from .geocoding import GeocodingService

logger = logging.getLogger(__name__)

METERS_TO_MILES = 1.0 / 1609.344
SECONDS_TO_MINUTES = 1.0 / 60.0


class RoutingError(Exception):
    """Raised when routing fails or route cannot be computed."""
    pass


class RoutingService:
    """
    Service responsible for calculating driving routes between coordinates or locations.
    Default implementation uses the Open Source Routing Machine (OSRM).
    """

    def __init__(self):
        self.osrm_base_url = getattr(
            settings,
            'OSRM_BASE_URL',
            'https://router.project-osrm.org'
        ).rstrip('/')
        self.geocoder = GeocodingService()

    def geocode_location(self, location_input: Any) -> tuple[float, float, str]:
        """Geocode location to (lat, lon, label)."""
        return self.geocoder.geocode(location_input)

    def get_route(
        self,
        start_lat: float,
        start_lon: float,
        finish_lat: float,
        finish_lon: float,
        use_cache: bool = True
    ) -> dict[str, Any]:
        """
        Request driving route from start to finish.
        Makes exactly ONE routing request (or 0 if cached).

        Returns:
            {
                "distance_miles": float,
                "duration_minutes": float,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon, lat], ...]
                }
            }
        """
        cache_key = f"osrm_route:{start_lat:.4f}:{start_lon:.4f}:{finish_lat:.4f}:{finish_lon:.4f}"

        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info(f"Route retrieved from cache: {cache_key}")
                return cached_data

        url = (
            f"{self.osrm_base_url}/route/v1/driving/"
            f"{start_lon:.6f},{start_lat:.6f};{finish_lon:.6f},{finish_lat:.6f}"
        )
        params = {
            'overview': 'full',
            'geometries': 'geojson',
            'steps': 'false',
        }

        start_time = time.perf_counter()
        logger.info(f"Calling external OSRM routing API: {url}")

        try:
            resp = requests.get(url, params=params, timeout=12)
            elapsed = time.perf_counter() - start_time
            logger.info(f"OSRM API call completed in {elapsed:.3f}s with status {resp.status_code}")

            if resp.status_code != 200:
                raise RoutingError(
                    f"Routing service returned HTTP status {resp.status_code}: {resp.text[:200]}"
                )

            data = resp.json()
            if data.get('code') != 'Ok' or not data.get('routes'):
                code = data.get('code', 'Unknown')
                message = data.get('message', 'No route found between the specified locations.')
                raise RoutingError(f"Route calculation failed ({code}): {message}")

            primary_route = data['routes'][0]
            distance_meters = float(primary_route.get('distance', 0.0))
            duration_seconds = float(primary_route.get('duration', 0.0))
            geometry = primary_route.get('geometry', {})

            if not geometry or not geometry.get('coordinates'):
                raise RoutingError("Route response did not contain valid GeoJSON geometry.")

            result = {
                'distance_miles': round(distance_meters * METERS_TO_MILES, 2),
                'duration_minutes': round(duration_seconds * SECONDS_TO_MINUTES, 1),
                'geometry': geometry,
            }

            if use_cache:
                cache.set(cache_key, result, timeout=3600 * 24)

            return result

        except requests.Timeout:
            logger.error("OSRM routing request timed out.")
            raise RoutingError("The routing service timed out. Please try again.")
        except requests.RequestException as e:
            logger.error(f"OSRM routing request error: {e}")
            raise RoutingError(f"Failed to communicate with routing provider: {str(e)}")
