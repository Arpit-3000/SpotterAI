import pytest
from decimal import Decimal
from fuel_optimizer.services.calculator import (
    calculate_gallons,
    calculate_cost,
    haversine_distance,
    point_to_segment_projection,
    get_route_bounding_box,
)


class TestCalculator:
    """Test suite for mathematical and geographic helper calculations."""

    def test_calculate_gallons_standard(self):
        # 100 miles / 10 MPG = 10 gallons
        gallons = calculate_gallons(100.0, mpg=10.0)
        assert gallons == Decimal('10.00')

    def test_calculate_gallons_fractional(self):
        # 790.4 miles / 10 MPG = 79.04 gallons
        gallons = calculate_gallons(790.4, mpg=10.0)
        assert gallons == Decimal('79.04')

    def test_calculate_gallons_invalid_mpg(self):
        with pytest.raises(ValueError):
            calculate_gallons(100.0, mpg=0.0)

    def test_calculate_cost_standard(self):
        # 10 gallons * $3.00 = $30.00
        cost = calculate_cost(Decimal('10.0'), Decimal('3.00'))
        assert cost == Decimal('30.00')

    def test_calculate_cost_decimal_precision(self):
        # 35.02 gallons * $3.19 = $111.7138 -> $111.71
        cost = calculate_cost(Decimal('35.02'), Decimal('3.19'))
        assert cost == Decimal('111.71')

    def test_haversine_same_point(self):
        dist = haversine_distance(40.7128, -74.0060, 40.7128, -74.0060)
        assert dist == pytest.approx(0.0, abs=1e-4)

    def test_haversine_nyc_to_chicago(self):
        # Great-circle distance between NYC and Chicago is ~712 miles
        dist = haversine_distance(40.7128, -74.0060, 41.8781, -87.6298)
        assert 700.0 < dist < 730.0

    def test_point_to_segment_projection_on_line(self):
        # Point right in middle of segment
        dist, t, seg_len = point_to_segment_projection(
            plat=40.0, plon=-80.0,
            alat=40.0, alon=-82.0,
            blat=40.0, blon=-78.0
        )
        assert dist == pytest.approx(0.0, abs=0.5)
        assert t == pytest.approx(0.5, abs=0.05)

    def test_get_route_bounding_box(self):
        coords = [[-74.0, 40.0], [-87.0, 41.0]]
        min_lat, max_lat, min_lon, max_lon = get_route_bounding_box(coords, buffer_miles=35.0)
        # Lat range should enclose 40.0 to 41.0 + buffer (~0.5 deg)
        assert min_lat < 40.0
        assert max_lat > 41.0
        assert min_lon < -87.0
        assert max_lon > -74.0
