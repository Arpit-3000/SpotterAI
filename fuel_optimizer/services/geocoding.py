import logging
import requests
from typing import Any
from django.conf import settings

logger = logging.getLogger(__name__)

# Common US Cities lookup cache for ultra-fast, zero-latency resolution
COMMON_US_CITIES = {
    "new york, ny": (40.7128, -74.0060, "New York, NY, USA"),
    "chicago, il": (41.8781, -87.6298, "Chicago, IL, USA"),
    "los angeles, ca": (34.0522, -118.2437, "Los Angeles, CA, USA"),
    "las vegas, nv": (36.1699, -115.1398, "Las Vegas, NV, USA"),
    "san francisco, ca": (37.7749, -122.4194, "San Francisco, CA, USA"),
    "miami, fl": (25.7617, -80.1918, "Miami, FL, USA"),
    "seattle, wa": (47.6062, -122.3321, "Seattle, WA, USA"),
    "dallas, tx": (32.7767, -96.7970, "Dallas, TX, USA"),
    "houston, tx": (29.7604, -95.3698, "Houston, TX, USA"),
    "austin, tx": (30.2672, -97.7431, "Austin, TX, USA"),
    "boston, ma": (42.3601, -71.0589, "Boston, MA, USA"),
    "atlanta, ga": (33.7490, -84.3880, "Atlanta, GA, USA"),
    "denver, co": (39.7392, -104.9903, "Denver, CO, USA"),
    "phoenix, az": (33.4484, -112.0740, "Phoenix, AZ, USA"),
    "philadelphia, pa": (39.9526, -75.1652, "Philadelphia, PA, USA"),
    "washington, dc": (38.9072, -77.0369, "Washington, DC, USA"),
    "detroit, mi": (42.3314, -83.0458, "Detroit, MI, USA"),
    "minneapolis, mn": (44.9778, -93.2650, "Minneapolis, MN, USA"),
    "st. louis, mo": (38.6270, -90.1994, "St. Louis, MO, USA"),
    "kansas city, mo": (39.0997, -94.5786, "Kansas City, MO, USA"),
    "nashville, tn": (36.1627, -86.7816, "Nashville, TN, USA"),
    "charlotte, nc": (35.2271, -80.8431, "Charlotte, NC, USA"),
    "orlando, fl": (28.5383, -81.3792, "Orlando, FL, USA"),
    "san diego, ca": (32.7157, -117.1611, "San Diego, CA, USA"),
    "portland, or": (45.5152, -122.6784, "Portland, OR, USA"),
    "salt lake city, ut": (40.7608, -111.8910, "Salt Lake City, UT, USA"),
    "albuquerque, nm": (35.0844, -106.6504, "Albuquerque, NM, USA"),
    "cleveland, oh": (41.4993, -81.6944, "Cleveland, OH, USA"),
    "columbus, oh": (39.9612, -82.9988, "Columbus, OH, USA"),
    "indianapolis, in": (39.7684, -86.1581, "Indianapolis, IN, USA"),
    "pittsburgh, pa": (40.4406, -79.9959, "Pittsburgh, PA, USA"),
}

# Valid US State abbreviations
US_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
    'DC', 'PR', 'VI', 'GU', 'AS', 'MP'
}


class GeocodingError(Exception):
    """Raised when geocoding fails or location is invalid."""
    pass


class NonUSALocationError(Exception):
    """Raised when location is outside the United States."""
    pass


def is_coordinate_in_usa(latitude: float, longitude: float) -> bool:
    """
    Check if geographic coordinates fall within US territory bounds:
    - Contiguous US: Lat [24.0, 50.0], Lon [-125.0, -66.0]
    - Alaska: Lat [51.0, 72.0], Lon [-180.0, -129.0] or [172.0, 180.0]
    - Hawaii: Lat [18.0, 29.0], Lon [-161.0, -154.0]
    - Puerto Rico / Virgin Islands: Lat [17.5, 18.6], Lon [-67.5, -64.5]
    """
    # Contiguous US
    if 24.0 <= latitude <= 50.0 and -125.0 <= longitude <= -66.0:
        return True
    # Alaska
    if 51.0 <= latitude <= 72.0 and (-180.0 <= longitude <= -129.0 or 172.0 <= longitude <= 180.0):
        return True
    # Hawaii
    if 18.0 <= latitude <= 29.0 and -161.0 <= longitude <= -154.0:
        return True
    # Puerto Rico & USVI
    if 17.5 <= latitude <= 18.6 and -67.5 <= longitude <= -64.5:
        return True

    return False


class GeocodingService:
    """
    Service responsible for converting location strings/dicts into US coordinates (lat, lon).
    """

    def __init__(self):
        self.census_base_url = getattr(
            settings,
            'GEOCODER_BASE_URL',
            'https://geocoding.geo.census.gov/geocoder'
        )
        self.nominatim_base_url = getattr(
            settings,
            'NOMINATIM_BASE_URL',
            'https://nominatim.openstreetmap.org'
        )

    def geocode(self, location_input: Any) -> tuple[float, float, str]:
        """
        Geocodes a location input into (latitude, longitude, formatted_address).
        Accepts:
            - str: "New York, NY", "Chicago, IL", "350 5th Ave, New York, NY 10118"
            - dict: {"city": "New York", "state": "NY"} or {"latitude": 40.7128, "longitude": -74.0060}
        Returns:
            (latitude, longitude, formatted_name)
        Raises:
            GeocodingError: If location cannot be resolved.
            NonUSALocationError: If location is resolved outside the USA.
        """
        if not location_input:
            raise GeocodingError("Location input cannot be empty.")

        # Handle direct coordinate input
        if isinstance(location_input, dict) and 'latitude' in location_input and 'longitude' in location_input:
            try:
                lat = float(location_input['latitude'])
                lon = float(location_input['longitude'])
            except (ValueError, TypeError):
                raise GeocodingError("Latitude and longitude must be valid numbers.")

            if not is_coordinate_in_usa(lat, lon):
                raise NonUSALocationError(f"Coordinates ({lat}, {lon}) are outside the United States.")
            name = location_input.get('name') or f"{lat:.4f}, {lon:.4f}"
            return lat, lon, name

        # Handle structured city/state dict
        if isinstance(location_input, dict):
            city = str(location_input.get('city', '')).strip()
            state = str(location_input.get('state', '')).strip().upper()
            if not city or not state:
                raise GeocodingError("Structured location requires both 'city' and 'state'.")
            if state not in US_STATES:
                raise NonUSALocationError(f"State '{state}' is not a valid US state.")
            query_str = f"{city}, {state}"
        elif isinstance(location_input, str):
            query_str = location_input.strip()
            if not query_str:
                raise GeocodingError("Location cannot be an empty string.")
        else:
            raise GeocodingError("Invalid location format. Expected string or dictionary.")

        norm_query = query_str.lower().strip()

        # Check in-memory fast cache first
        if norm_query in COMMON_US_CITIES:
            lat, lon, label = COMMON_US_CITIES[norm_query]
            return lat, lon, label

        # Check explicit non-USA inputs before network call
        lower_parts = norm_query.replace(',', ' ').split()
        non_us_keywords = {'canada', 'mexico', 'france', 'uk', 'england', 'germany', 'india', 'china', 'australia', 'japan', 'london', 'paris', 'tokyo', 'toronto'}
        if any(kw in lower_parts for kw in non_us_keywords):
            raise NonUSALocationError(f"Location '{query_str}' is outside the United States.")

        # Attempt Census Geocoder first (strictly US)
        coords = self._geocode_census(query_str)
        if coords:
            lat, lon, label = coords
            if not is_coordinate_in_usa(lat, lon):
                raise NonUSALocationError(f"Resolved location for '{query_str}' is outside the United States.")
            return lat, lon, label

        # Attempt Nominatim as fallback
        coords = self._geocode_nominatim(query_str)
        if coords:
            lat, lon, label, country_code = coords
            if country_code != 'us' or not is_coordinate_in_usa(lat, lon):
                raise NonUSALocationError(f"Location '{query_str}' is outside the United States.")
            return lat, lon, label

        raise GeocodingError(f"Unable to geocode location: '{query_str}'.")

    def _geocode_census(self, address: str) -> tuple[float, float, str] | None:
        """Call US Census Geocoder onelineaddress API."""
        url = f"{self.census_base_url}/locations/onelineaddress"
        params = {
            'address': address,
            'benchmark': 'Public_AR_Current',
            'format': 'json'
        }
        try:
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                matches = data.get('result', {}).get('addressMatches', [])
                if matches:
                    match = matches[0]
                    coords = match.get('coordinates', {})
                    lon = float(coords['x'])
                    lat = float(coords['y'])
                    label = match.get('matchedAddress', address)
                    return lat, lon, label
        except Exception as e:
            logger.debug(f"US Census geocoding error for '{address}': {e}")
        return None

    def _geocode_nominatim(self, query: str) -> tuple[float, float, str, str] | None:
        """Call OpenStreetMap Nominatim API."""
        url = f"{self.nominatim_base_url}/search"
        params = {
            'q': query,
            'format': 'json',
            'addressdetails': 1,
            'limit': 1
        }
        headers = {
            'User-Agent': 'SpotterFuelOptimizer/1.0 (backend assessment)'
        }
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    first = data[0]
                    lat = float(first['lat'])
                    lon = float(first['lon'])
                    country_code = first.get('address', {}).get('country_code', '').lower()
                    label = first.get('display_name', query)
                    return lat, lon, label, country_code
        except Exception as e:
            logger.debug(f"Nominatim geocoding error for '{query}': {e}")
        return None
