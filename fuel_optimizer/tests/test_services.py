import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from fuel_optimizer.models import FuelStation
from fuel_optimizer.services.geocoding import (
    GeocodingService,
    GeocodingError,
    NonUSALocationError,
    is_coordinate_in_usa,
)
from fuel_optimizer.services.routing import RoutingService, RoutingError
from fuel_optimizer.services.route_matching import RouteMatchingService


class TestGeocodingService:
    def setup_method(self):
        self.geocoder = GeocodingService()

    def test_usa_coordinate_boundary_check(self):
        # NYC
        assert is_coordinate_in_usa(40.7128, -74.0060) is True
        # LA
        assert is_coordinate_in_usa(34.0522, -118.2437) is True
        # Paris, France
        assert is_coordinate_in_usa(48.8566, 2.3522) is False
        # Sydney, Australia
        assert is_coordinate_in_usa(-33.8688, 151.2093) is False

    def test_common_us_city_fast_cache(self):
        lat, lon, label = self.geocoder.geocode("New York, NY")
        assert 40.0 < lat < 41.5
        assert -74.5 < lon < -73.5
        assert "New York" in label

    def test_structured_dict_location(self):
        lat, lon, label = self.geocoder.geocode({"city": "Chicago", "state": "IL"})
        assert 41.5 < lat < 42.5
        assert -88.0 < lon < -87.0

    def test_direct_coordinate_input(self):
        lat, lon, _ = self.geocoder.geocode({"latitude": 39.7392, "longitude": -104.9903})
        assert lat == pytest.approx(39.7392)
        assert lon == pytest.approx(-104.9903)

    def test_empty_location_raises_error(self):
        with pytest.raises(GeocodingError):
            self.geocoder.geocode("")
        with pytest.raises(GeocodingError):
            self.geocoder.geocode(None)

    def test_non_usa_location_rejected(self):
        with pytest.raises(NonUSALocationError):
            self.geocoder.geocode("Paris, France")
        with pytest.raises(NonUSALocationError):
            self.geocoder.geocode("Toronto, Canada")


class TestRoutingService:
    def setup_method(self):
        self.routing = RoutingService()

    @patch('fuel_optimizer.services.routing.requests.get')
    def test_get_route_success(self, mock_get):
        # 1,272,000 meters = 790.38 miles, 44,100 seconds = 735.0 minutes
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'code': 'Ok',
            'routes': [
                {
                    'distance': 1272000.0,
                    'duration': 44100.0,
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': [[-74.0060, 40.7128], [-87.6298, 41.8781]]
                    }
                }
            ]
        }
        mock_get.return_value = mock_response

        res = self.routing.get_route(40.7128, -74.0060, 41.8781, -87.6298, use_cache=False)
        assert res['distance_miles'] == 790.38
        assert res['duration_minutes'] == 735.0
        assert res['geometry']['type'] == 'LineString'

    @patch('fuel_optimizer.services.routing.requests.get')
    def test_get_route_failure(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'code': 'NoRoute',
            'message': 'No route could be found.'
        }
        mock_get.return_value = mock_response

        with pytest.raises(RoutingError):
            self.routing.get_route(40.7128, -74.0060, 41.8781, -87.6298, use_cache=False)


@pytest.mark.django_db
class TestRouteMatchingService:
    def test_candidate_matching_along_corridor(self):
        # Create stations
        st_on_route = FuelStation.objects.create(
            opis_id=901,
            name="Near Route Station",
            address="100 Route Rd",
            city="Midway",
            state="PA",
            retail_price=Decimal("3.15"),
            latitude=40.5,
            longitude=-78.0,
        )
        st_far_off = FuelStation.objects.create(
            opis_id=902,
            name="Far Off Station",
            address="200 Away Rd",
            city="FarCity",
            state="FL",
            retail_price=Decimal("2.99"),
            latitude=28.0,
            longitude=-81.0,
        )

        geometry = {
            'type': 'LineString',
            'coordinates': [
                [-74.0060, 40.7128],
                [-78.0000, 40.5000],
                [-87.6298, 41.8781]
            ]
        }

        service = RouteMatchingService(corridor_radius_miles=30.0)
        candidates = service.find_candidate_stations(geometry, route_distance_miles=790.0)

        candidate_ids = [c['opis_id'] for c in candidates]
        assert 901 in candidate_ids
        assert 902 not in candidate_ids
