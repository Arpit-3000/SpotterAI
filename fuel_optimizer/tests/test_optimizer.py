import pytest
from decimal import Decimal
from fuel_optimizer.services.fuel_optimizer import FuelOptimizerService, NoFeasibleFuelPlanError


def make_candidate(station_id: int, dist: float, price: float, name: str = "Test Stop"):
    return {
        'station': None,
        'station_id': station_id,
        'opis_id': 1000 + station_id,
        'name': f"{name} #{station_id}",
        'address': f"{station_id} Main St",
        'city': "TestCity",
        'state': "TX",
        'latitude': 32.0,
        'longitude': -97.0,
        'retail_price': Decimal(str(price)),
        'distance_from_route_start_miles': dist,
        'distance_to_route_miles': 2.0,
    }


class TestFuelOptimizer:
    """Test suite for the fuel stop selection and cost optimization algorithm."""

    def setup_method(self):
        self.optimizer = FuelOptimizerService(max_range_miles=500.0, mpg=10.0)

    def test_route_under_500_miles_zero_stops(self):
        """A route under 500 miles requires 0 fuel stops since vehicle starts with full tank."""
        candidates = [
            make_candidate(1, 150.0, 3.50),
            make_candidate(2, 250.0, 3.20),
        ]
        res = self.optimizer.optimize(route_distance_miles=400.0, candidate_stations=candidates)

        assert len(res['fuel_stops']) == 0
        assert res['fuel_summary']['total_distance_miles'] == 400.0
        assert res['fuel_summary']['total_gallons_consumed'] == 40.0
        assert res['fuel_summary']['total_fuel_cost'] == 0.00

    def test_route_exact_500_miles(self):
        """Exact 500 miles boundary requires 0 fuel stops."""
        candidates = [make_candidate(1, 250.0, 3.20)]
        res = self.optimizer.optimize(route_distance_miles=500.0, candidate_stations=candidates)
        assert len(res['fuel_stops']) == 0
        assert res['fuel_summary']['total_gallons_consumed'] == 50.0
        assert res['fuel_summary']['total_fuel_cost'] == 0.00

    def test_single_stop_route_750_miles(self):
        """A 750-mile trip requires at least 1 stop before mile 500."""
        candidates = [
            make_candidate(1, 200.0, 3.80),
            make_candidate(2, 350.0, 3.10),  # Cheapest reachable
            make_candidate(3, 450.0, 3.90),
        ]
        res = self.optimizer.optimize(route_distance_miles=750.0, candidate_stations=candidates)

        stops = res['fuel_stops']
        assert len(stops) >= 1

        # Check that no leg exceeds 500 miles
        legs = []
        prev = 0.0
        for s in stops:
            legs.append(s['distance_from_route_start_miles'] - prev)
            prev = s['distance_from_route_start_miles']
        legs.append(750.0 - prev)

        for leg in legs:
            assert leg <= 500.0, f"Driving leg {leg} exceeds 500 miles"

        assert res['fuel_summary']['total_distance_miles'] == 750.0
        assert res['fuel_summary']['total_gallons_consumed'] == 75.0
        assert res['fuel_summary']['total_fuel_cost'] > 0.0

    def test_prefers_cheaper_fuel_station(self):
        """Verify the optimizer chooses the lower cost station."""
        candidates = [
            make_candidate(1, 300.0, 4.50),  # Expensive
            make_candidate(2, 350.0, 2.80),  # Much cheaper
        ]
        res = self.optimizer.optimize(route_distance_miles=800.0, candidate_stations=candidates)
        stops = res['fuel_stops']

        # Should select the cheaper station
        chosen_ids = [s['station_id'] for s in stops]
        assert 2 in chosen_ids

    def test_multi_stop_long_distance_1400_miles(self):
        """A 1400-mile route requires multiple stops."""
        candidates = [
            make_candidate(1, 350.0, 3.20),
            make_candidate(2, 700.0, 3.15),
            make_candidate(3, 1050.0, 3.25),
        ]
        res = self.optimizer.optimize(route_distance_miles=1400.0, candidate_stations=candidates)
        stops = res['fuel_stops']

        assert len(stops) >= 2
        # Verify no leg exceeds 500 miles
        prev = 0.0
        for s in stops:
            leg = s['distance_from_route_start_miles'] - prev
            assert leg <= 500.0, f"Leg {leg} exceeds 500 miles"
            assert s['gallons_purchased'] <= 50.0, "Cannot buy more than tank capacity"
            prev = s['distance_from_route_start_miles']

        assert 1400.0 - prev <= 500.0

    def test_gap_exceeding_range_raises_error(self):
        """A route with a station gap > 500 miles cannot be bridged."""
        candidates = [
            make_candidate(1, 300.0, 3.20),
            # Gap of 600 miles between mile 300 and mile 900!
            make_candidate(2, 900.0, 3.10),
        ]
        with pytest.raises(NoFeasibleFuelPlanError):
            self.optimizer.optimize(route_distance_miles=1200.0, candidate_stations=candidates)

    def test_no_stations_on_long_route_raises_error(self):
        """A 600-mile route with zero stations fails with NoFeasibleFuelPlanError."""
        with pytest.raises(NoFeasibleFuelPlanError):
            self.optimizer.optimize(route_distance_miles=600.0, candidate_stations=[])
