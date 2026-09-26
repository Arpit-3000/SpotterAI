import math
from decimal import Decimal, ROUND_HALF_UP

EARTH_RADIUS_MILES = 3958.8  # Mean Earth radius in miles


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth in miles
    using the Haversine formula.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_MILES * c


def point_to_segment_projection(
    plat: float, plon: float,
    alat: float, alon: float,
    blat: float, blon: float
) -> tuple[float, float, float]:
    """
    Project point P onto line segment AB.
    Returns:
        - min_distance_miles: Shortest distance from P to segment AB in miles.
        - t: Clamped projection fraction [0.0, 1.0] along AB.
        - segment_length_miles: Length of segment AB in miles.
    """
    seg_len = haversine_distance(alat, alon, blat, blon)
    if seg_len < 1e-6:
        dist = haversine_distance(plat, plon, alat, alon)
        return dist, 0.0, 0.0

    # Use flat-earth projection for local segment geometry
    # x = distance east in miles, y = distance north in miles relative to A
    avg_lat_rad = math.radians((alat + blat) / 2.0)
    miles_per_deg_lat = 69.0
    miles_per_deg_lon = 69.0 * math.cos(avg_lat_rad)

    # Segment vector A -> B
    ab_x = (blon - alon) * miles_per_deg_lon
    ab_y = (blat - alat) * miles_per_deg_lat

    # Vector A -> P
    ap_x = (plon - alon) * miles_per_deg_lon
    ap_y = (plat - alat) * miles_per_deg_lat

    # Dot product and squared segment length
    ab_sq = ab_x * ab_x + ab_y * ab_y
    if ab_sq < 1e-8:
        dist = haversine_distance(plat, plon, alat, alon)
        return dist, 0.0, seg_len

    t = (ap_x * ab_x + ap_y * ab_y) / ab_sq
    t_clamped = max(0.0, min(1.0, t))

    # Nearest point on segment
    near_lon = alon + t_clamped * (blon - alon)
    near_lat = alat + t_clamped * (blat - alat)

    dist = haversine_distance(plat, plon, near_lat, near_lon)
    return dist, t_clamped, seg_len


def get_route_bounding_box(
    coordinates: list[list[float]],
    buffer_miles: float = 35.0
) -> tuple[float, float, float, float]:
    """
    Compute geographic bounding box (min_lat, max_lat, min_lon, max_lon)
    for a GeoJSON LineString coordinates list [[lon, lat], ...],
    expanded by buffer_miles.
    """
    if not coordinates:
        return (0.0, 0.0, 0.0, 0.0)

    lons = [c[0] for c in coordinates]
    lats = [c[1] for c in coordinates]

    min_lat = min(lats)
    max_lat = max(lats)
    min_lon = min(lons)
    max_lon = max(lons)

    avg_lat_rad = math.radians((min_lat + max_lat) / 2.0)
    buffer_lat = buffer_miles / 69.0
    cos_lat = math.cos(avg_lat_rad)
    buffer_lon = buffer_miles / (69.0 * cos_lat) if abs(cos_lat) > 1e-4 else buffer_lat

    return (
        min_lat - buffer_lat,
        max_lat + buffer_lat,
        min_lon - buffer_lon,
        max_lon + buffer_lon,
    )


def calculate_gallons(distance_miles: float, mpg: float = 10.0) -> Decimal:
    """
    Calculate fuel consumed in gallons for a given distance in miles.
    Formula: gallons = distance_miles / mpg
    """
    if mpg <= 0:
        raise ValueError("Fuel efficiency (MPG) must be greater than zero.")
    gallons = Decimal(str(distance_miles)) / Decimal(str(mpg))
    return gallons.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def calculate_cost(gallons: Decimal | float, price_per_gallon: Decimal | float) -> Decimal:
    """
    Calculate total fuel cost in USD.
    Formula: cost = gallons * price_per_gallon
    """
    if not isinstance(gallons, Decimal):
        gallons = Decimal(str(round(gallons, 4)))
    if not isinstance(price_per_gallon, Decimal):
        price_per_gallon = Decimal(str(round(price_per_gallon, 4)))

    cost = gallons * price_per_gallon
    return cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
