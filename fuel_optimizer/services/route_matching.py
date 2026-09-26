import logging
import math
from typing import Any
from collections import defaultdict
from django.conf import settings
from ..models import FuelStation
from .calculator import (
    haversine_distance,
    point_to_segment_projection,
    get_route_bounding_box,
)

logger = logging.getLogger(__name__)


class RouteMatchingService:
    """
    Filters and projects database FuelStations onto the route polyline within a corridor tolerance.
    Uses spatial bucketing to maintain millisecond-level runtime performance without external GIS.
    """

    def __init__(self, corridor_radius_miles: float | None = None):
        if corridor_radius_miles is None:
            corridor_radius_miles = getattr(settings, 'CORRIDOR_RADIUS_MILES', 30.0)
        self.corridor_radius_miles = float(corridor_radius_miles)

    def find_candidate_stations(
        self,
        geometry: dict[str, Any],
        route_distance_miles: float
    ) -> list[dict[str, Any]]:
        """
        Identify fuel stations within the corridor radius along the route geometry,
        project them onto the route, and order them by distance from route start.
        """
        raw_coords = geometry.get('coordinates', [])
        if len(raw_coords) < 2:
            return []

        # Downsample polyline for fast spatial indexing if geometry has tens of thousands of points
        if len(raw_coords) > 2000:
            coords = [raw_coords[0]]
            last_lon, last_lat = raw_coords[0]
            for pt in raw_coords[1:-1]:
                if abs(pt[0] - last_lon) > 0.02 or abs(pt[1] - last_lat) > 0.02:
                    coords.append(pt)
                    last_lon, last_lat = pt[0], pt[1]
            coords.append(raw_coords[-1])
        else:
            coords = raw_coords

        # 1. Precalculate segment cumulative distances
        seg_count = len(coords) - 1
        seg_lengths = []
        cum_dists = [0.0]
        total_poly_dist = 0.0

        for i in range(seg_count):
            lon1, lat1 = coords[i]
            lon2, lat2 = coords[i + 1]
            d = haversine_distance(lat1, lon1, lat2, lon2)
            seg_lengths.append(d)
            total_poly_dist += d
            cum_dists.append(total_poly_dist)

        # Scale factor if polyline distance slightly differs from OSRM road distance
        scale = (route_distance_miles / total_poly_dist) if total_poly_dist > 0 else 1.0

        # 2. Build spatial bucket grid for line segments (cell size approx 0.5 degrees ~ 35 miles)
        cell_size = 0.5
        grid: dict[tuple[int, int], list[int]] = defaultdict(list)

        for idx in range(seg_count):
            lon1, lat1 = coords[idx]
            lon2, lat2 = coords[idx + 1]
            min_lat, max_lat = min(lat1, lat2), max(lat1, lat2)
            min_lon, max_lon = min(lon1, lon2), max(lon1, lon2)

            r_min = int(math.floor(min_lat / cell_size))
            r_max = int(math.floor(max_lat / cell_size))
            c_min = int(math.floor(min_lon / cell_size))
            c_max = int(math.floor(max_lon / cell_size))

            for r in range(r_min, r_max + 1):
                for c in range(c_min, c_max + 1):
                    grid[(r, c)].append(idx)

        # 3. Database query: filter stations inside the route's overall bounding box
        min_lat, max_lat, min_lon, max_lon = get_route_bounding_box(
            coords,
            buffer_miles=self.corridor_radius_miles + 5.0
        )

        stations_qs = FuelStation.objects.filter(
            latitude__gte=min_lat,
            latitude__lte=max_lat,
            longitude__gte=min_lon,
            longitude__lte=max_lon,
            latitude__isnull=False,
            longitude__isnull=False,
        ).only(
            'id', 'opis_id', 'name', 'address', 'city', 'state',
            'rack_id', 'retail_price', 'latitude', 'longitude'
        )

        stations = list(stations_qs)
        logger.info(
            f"Candidate matching: {len(stations)} stations within bounding box "
            f"[{min_lat:.2f}, {max_lat:.2f}, {min_lon:.2f}, {max_lon:.2f}]"
        )

        candidates = []
        corridor_limit = self.corridor_radius_miles

        # 4. Project each station to the closest polyline segment
        for st in stations:
            s_lat = st.latitude
            s_lon = st.longitude

            r_cell = int(math.floor(s_lat / cell_size))
            c_cell = int(math.floor(s_lon / cell_size))

            # Query neighboring cells (3x3 grid around station)
            tested_segments = set()
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    for seg_idx in grid.get((r_cell + dr, c_cell + dc), []):
                        tested_segments.add(seg_idx)

            # If no bucket segments found in adjacent cells, the station is outside the corridor
            if not tested_segments:
                continue

            best_dist = float('inf')
            best_route_dist = 0.0

            for seg_idx in tested_segments:
                lon1, lat1 = coords[seg_idx]
                lon2, lat2 = coords[seg_idx + 1]
                dist_to_seg, t, _ = point_to_segment_projection(
                    s_lat, s_lon, lat1, lon1, lat2, lon2
                )

                if dist_to_seg < best_dist:
                    best_dist = dist_to_seg
                    # Projected distance along polyline
                    raw_route_dist = cum_dists[seg_idx] + t * seg_lengths[seg_idx]
                    best_route_dist = raw_route_dist * scale

            if best_dist <= corridor_limit:
                # Keep if station is between route start and finish (with small 5-mile tolerance)
                if -5.0 <= best_route_dist <= route_distance_miles + 5.0:
                    clamped_dist = max(0.0, min(route_distance_miles, best_route_dist))
                    candidates.append({
                        'station': st,
                        'station_id': st.id,
                        'opis_id': st.opis_id,
                        'name': st.name,
                        'address': st.address,
                        'city': st.city,
                        'state': st.state,
                        'latitude': st.latitude,
                        'longitude': st.longitude,
                        'retail_price': st.retail_price,
                        'distance_from_route_start_miles': round(clamped_dist, 2),
                        'distance_to_route_miles': round(best_dist, 2),
                    })

        # Sort candidates strictly by distance from start
        candidates.sort(key=lambda c: c['distance_from_route_start_miles'])
        logger.info(f"Retained {len(candidates)} candidate stations within {corridor_limit} mi corridor.")
        return candidates
