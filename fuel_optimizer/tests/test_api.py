import pytest
from unittest.mock import patch
from decimal import Decimal
from rest_framework.test import APIClient
from rest_framework import status
from fuel_optimizer.models import FuelStation


@pytest.mark.django_db
class TestFuelPlanAPI:
    """Test suite for POST /api/v1/route/fuel-plan/ endpoint."""

    def setup_method(self):
        self.client = APIClient()
        self.url = '/api/v1/route/fuel-plan/'

    def test_missing_start_rejected(self):
        resp = self.client.post(self.url, {'finish': 'Chicago, IL'}, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in resp.data
        assert resp.data['error']['code'] == 'VALIDATION_ERROR'

    def test_missing_finish_rejected(self):
        resp = self.client.post(self.url, {'start': 'New York, NY'}, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data['error']['code'] == 'VALIDATION_ERROR'

    def test_empty_string_location_rejected(self):
        resp = self.client.post(self.url, {'start': '   ', 'finish': 'Chicago, IL'}, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data['error']['code'] == 'VALIDATION_ERROR'

    def test_non_usa_location_rejected(self):
        resp = self.client.post(
            self.url,
            {'start': 'Paris, France', 'finish': 'Chicago, IL'},
            format='json'
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data['error']['code'] == 'NON_USA_LOCATION'

    @patch('fuel_optimizer.services.routing.RoutingService.get_route')
    def test_successful_fuel_plan_response_contract(self, mock_get_route):
        # Create stations in DB along the route
        FuelStation.objects.create(
            opis_id=101,
            name="Midway Travel Plaza",
            address="Milepost 150 I-80",
            city="Clearfield",
            state="PA",
            retail_price=Decimal("3.199"),
            latitude=41.0,
            longitude=-78.4,
        )
        FuelStation.objects.create(
            opis_id=102,
            name="Buckeye Truck Stop",
            address="Exit 110 I-80",
            city="Youngstown",
            state="OH",
            retail_price=Decimal("3.059"),
            latitude=41.1,
            longitude=-80.6,
        )

        mock_get_route.return_value = {
            'distance_miles': 790.4,
            'duration_minutes': 735.0,
            'geometry': {
                'type': 'LineString',
                'coordinates': [
                    [-74.0060, 40.7128],
                    [-78.4000, 41.0000],
                    [-80.6000, 41.1000],
                    [-87.6298, 41.8781]
                ]
            }
        }

        payload = {
            'start': 'New York, NY',
            'finish': 'Chicago, IL'
        }
        resp = self.client.post(self.url, payload, format='json')

        assert resp.status_code == status.HTTP_200_OK

        # Verify all contract fields
        data = resp.data
        assert 'start' in data
        assert 'finish' in data
        assert 'route' in data
        assert 'vehicle' in data
        assert 'fuel_stops' in data
        assert 'fuel_summary' in data

        # Route fields
        assert data['route']['distance_miles'] == 790.4
        assert data['route']['duration_minutes'] == 735.0
        assert data['route']['geometry']['type'] == 'LineString'

        # Vehicle fields
        assert data['vehicle']['max_range_miles'] == 500.0
        assert data['vehicle']['miles_per_gallon'] == 10.0

        # Stops
        stops = data['fuel_stops']
        assert isinstance(stops, list)
        assert len(stops) >= 1
        first_stop = stops[0]
        assert 'sequence' in first_stop
        assert 'station_id' in first_stop
        assert 'name' in first_stop
        assert 'price_per_gallon' in first_stop
        assert 'gallons_purchased' in first_stop
        assert 'fuel_cost' in first_stop

        # Summary
        summary = data['fuel_summary']
        assert summary['total_distance_miles'] == 790.4
        assert summary['total_gallons_consumed'] == 79.04
        assert summary['total_fuel_cost'] > 0.0

    @patch('fuel_optimizer.services.routing.RoutingService.get_route')
    def test_structured_input_format(self, mock_get_route):
        mock_get_route.return_value = {
            'distance_miles': 270.0,
            'duration_minutes': 260.0,
            'geometry': {
                'type': 'LineString',
                'coordinates': [
                    [-118.2437, 34.0522],
                    [-115.1398, 36.1699]
                ]
            }
        }

        payload = {
            'start': {'city': 'Los Angeles', 'state': 'CA'},
            'finish': {'city': 'Las Vegas', 'state': 'NV'}
        }
        resp = self.client.post(self.url, payload, format='json')
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['route']['distance_miles'] == 270.0
        # Distance <= 500 miles requires 0 stops
        assert len(resp.data['fuel_stops']) == 0
