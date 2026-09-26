import logging
from decimal import Decimal
from typing import Any
from django.conf import settings
from .calculator import calculate_gallons, calculate_cost

logger = logging.getLogger(__name__)


class NoFeasibleFuelPlanError(Exception):
    """Raised when no feasible fuel stops exist within the vehicle's 500-mile range."""
    pass


class FuelOptimizerService:
    """
    Optimizes fuel stops along a driving route according to vehicle range and fuel prices.
    
    Vehicle Assumptions:
    - Maximum range: 500 miles (configurable via VEHICLE_MAX_RANGE_MILES).
    - Fuel efficiency: 10 miles per gallon (configurable via VEHICLE_MPG).
    - Full tank capacity: 50 gallons (500 miles / 10 MPG).
    - Vehicle departs start location with a full tank (50 gallons).
    - Initial fuel is pre-existing; incremental fuel cost reflects fuel purchased during the trip.
    
    Algorithm:
    Classic minimum-cost gas-station greedy algorithm:
    1. Start at origin with full tank (50 gallons).
    2. If destination is reachable within current fuel, complete route without stopping.
    3. Look ahead up to 500 miles:
       - If a cheaper station exists ahead within reach, travel to it and purchase just
         enough fuel to reach it (or 0 if starting tank already covers it).
       - If current station is cheaper than all reachable stations, fill the tank to maximum (50 gal)
         and proceed to the next reachable station that minimizes cost.
    """

    def __init__(
        self,
        max_range_miles: float | None = None,
        mpg: float | None = None
    ):
        if max_range_miles is None:
            max_range_miles = getattr(settings, 'VEHICLE_MAX_RANGE_MILES', 500.0)
        if mpg is None:
            mpg = getattr(settings, 'VEHICLE_MPG', 10.0)

        self.max_range_miles = float(max_range_miles)
        self.mpg = float(mpg)
        self.tank_capacity = self.max_range_miles / self.mpg

    def optimize(
        self,
        route_distance_miles: float,
        candidate_stations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Calculates the optimal fuel stops and total costs.

        Returns:
            {
                "fuel_stops": [...],
                "fuel_summary": {
                    "total_distance_miles": float,
                    "total_gallons_consumed": float,
                    "total_fuel_cost": float
                }
            }
        """
        route_distance = round(float(route_distance_miles), 2)
        total_gallons_consumed = round(route_distance / self.mpg, 2)

        # Edge case: Destination reachable on initial full tank
        if route_distance <= self.max_range_miles:
            logger.info(
                f"Route distance {route_distance} mi <= {self.max_range_miles} mi max range. "
                "0 fuel stops required with starting full tank."
            )
            return {
                'fuel_stops': [],
                'fuel_summary': {
                    'total_distance_miles': route_distance,
                    'total_gallons_consumed': total_gallons_consumed,
                    'total_fuel_cost': 0.00,
                }
            }

        # Filter and sanitize candidate stations
        valid_candidates = [
            c for c in candidate_stations
            if 0.0 < c['distance_from_route_start_miles'] < route_distance
        ]
        valid_candidates.sort(key=lambda c: c['distance_from_route_start_miles'])

        # Deduplicate candidates within 1.5 miles by keeping the cheapest
        deduped_candidates = []
        for cand in valid_candidates:
            if not deduped_candidates:
                deduped_candidates.append(cand)
            else:
                prev = deduped_candidates[-1]
                if abs(cand['distance_from_route_start_miles'] - prev['distance_from_route_start_miles']) <= 1.5:
                    if cand['retail_price'] < prev['retail_price']:
                        deduped_candidates[-1] = cand
                else:
                    deduped_candidates.append(cand)

        # 1. Feasibility check: Can we bridge the entire route without any hop > max_range_miles?
        self._verify_feasibility(route_distance, deduped_candidates)

        # 2. Run greedy fuel optimization
        fuel_stops = self._run_greedy_optimizer(route_distance, deduped_candidates)

        # Compute total fuel cost from stops
        total_fuel_cost = Decimal('0.00')
        for stop in fuel_stops:
            total_fuel_cost += Decimal(str(stop['fuel_cost']))

        return {
            'fuel_stops': fuel_stops,
            'fuel_summary': {
                'total_distance_miles': route_distance,
                'total_gallons_consumed': total_gallons_consumed,
                'total_fuel_cost': float(total_fuel_cost.quantize(Decimal('0.01'))),
            }
        }

    def _verify_feasibility(
        self,
        route_distance: float,
        candidates: list[dict[str, Any]]
    ) -> None:
        """
        Verify that a reachable path exists from start (0) to finish (route_distance)
        where no consecutive hop exceeds max_range_miles.
        """
        if not candidates:
            raise NoFeasibleFuelPlanError(
                f"No fuel stations found along the route, and route distance ({route_distance:.1f} mi) "
                f"exceeds vehicle maximum range ({self.max_range_miles:.1f} mi)."
            )

        # Check if first station is reachable from start
        if candidates[0]['distance_from_route_start_miles'] > self.max_range_miles:
            raise NoFeasibleFuelPlanError(
                f"First fuel station is at mile {candidates[0]['distance_from_route_start_miles']:.1f}, "
                f"which exceeds the {self.max_range_miles:.1f} mile vehicle range from start."
            )

        # Check connectivity to destination
        curr_reach = self.max_range_miles
        for c in candidates:
            c_dist = c['distance_from_route_start_miles']
            if c_dist <= curr_reach:
                curr_reach = max(curr_reach, c_dist + self.max_range_miles)
            else:
                # Gap cannot be bridged
                break

        if curr_reach < route_distance:
            raise NoFeasibleFuelPlanError(
                f"No feasible fuel-stop plan exists for this route within the {self.max_range_miles:.0f} mile vehicle range. "
                "There is a gap exceeding vehicle range that cannot be bridged."
            )

    def _run_greedy_optimizer(
        self,
        route_distance: float,
        candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Simulate vehicle travel and select fuel stops.
        """
        curr_dist = 0.0
        curr_fuel = self.tank_capacity  # Starts with full tank (50 gallons)
        curr_price = float('inf')       # Starting price is virtual/infinite
        prev_stop_dist = 0.0
        stops = []

        while curr_dist < route_distance:
            remaining_to_dest = route_distance - curr_dist

            # Can we reach destination with current fuel?
            if curr_fuel * self.mpg >= remaining_to_dest - 1e-4:
                # Arrived at destination
                break

            # Find all reachable candidates ahead with a full tank from current position
            reachable = [
                c for c in candidates
                if curr_dist < c['distance_from_route_start_miles'] <= curr_dist + self.max_range_miles
            ]

            if not reachable and remaining_to_dest > self.max_range_miles:
                raise NoFeasibleFuelPlanError(
                    f"No reachable fuel station found within {self.max_range_miles:.0f} miles from mile {curr_dist:.1f}."
                )

            # Check if destination itself is reachable with a full tank
            dest_in_reach = remaining_to_dest <= self.max_range_miles

            # Case 1: Currently at START (mile 0)
            if curr_dist == 0.0:
                # From start, we have a full tank (500 miles range).
                # To maximize usage of free initial fuel, find candidates within (0, 500]
                # that can reach forward (or destination).
                # Among them, pick the cheapest candidate, or the best positioned one.
                # Specifically: find candidate that can reach forward with minimum price.
                viable = []
                for c in reachable:
                    # Can c reach another station or destination?
                    c_dist = c['distance_from_route_start_miles']
                    if (route_distance - c_dist <= self.max_range_miles or
                            any(other['distance_from_route_start_miles'] > c_dist and
                                other['distance_from_route_start_miles'] <= c_dist + self.max_range_miles
                                for other in candidates)):
                        viable.append(c)

                if not viable:
                    viable = reachable

                # Look for the cheapest station in the reachable window.
                # If there are multiple cheap stations, pick the one furthest along.
                best_stop = min(viable, key=lambda c: (float(c['retail_price']), -c['distance_from_route_start_miles']))

                dist_traveled = best_stop['distance_from_route_start_miles'] - curr_dist
                fuel_used = dist_traveled / self.mpg
                curr_fuel -= fuel_used
                curr_dist = best_stop['distance_from_route_start_miles']
                curr_price = float(best_stop['retail_price'])
                curr_candidate = best_stop

                # We arrive at best_stop with curr_fuel remaining.
                # The purchase decision for this station will be handled in the next loop iteration!
                continue

            # Case 2: Currently AT a fuel station `curr_candidate`
            # Look ahead for a station cheaper than curr_price
            cheaper_ahead = [
                c for c in reachable
                if float(c['retail_price']) < curr_price
            ]

            if cheaper_ahead:
                # Subcase 2A: There is a cheaper station ahead within reach!
                # Prefer the first or cheapest station ahead that is cheaper than current.
                # To avoid premature stops, select the best cheaper station ahead:
                next_stop = min(cheaper_ahead, key=lambda c: (float(c['retail_price']), c['distance_from_route_start_miles']))
                dist_to_next = next_stop['distance_from_route_start_miles'] - curr_dist
                fuel_needed = dist_to_next / self.mpg

                gallons_to_buy = max(0.0, fuel_needed - curr_fuel)
                gallons_to_buy = min(gallons_to_buy, self.tank_capacity - curr_fuel)

                if gallons_to_buy > 0.01:
                    cost = calculate_cost(gallons_to_buy, curr_candidate['retail_price'])
                    stops.append(self._format_stop(
                        len(stops) + 1,
                        curr_candidate,
                        prev_stop_dist,
                        gallons_to_buy,
                        cost
                    ))
                    prev_stop_dist = curr_dist
                    curr_fuel += gallons_to_buy

                # Drive to next stop
                curr_fuel -= fuel_needed
                curr_dist = next_stop['distance_from_route_start_miles']
                curr_price = float(next_stop['retail_price'])
                curr_candidate = next_stop

            else:
                # Subcase 2B: No station ahead within reach is cheaper than current station!
                # Current station is the cheapest in reach.
                if dest_in_reach:
                    # Buy just enough to reach destination comfortably
                    fuel_needed = remaining_to_dest / self.mpg
                    gallons_to_buy = max(0.0, fuel_needed - curr_fuel)
                    gallons_to_buy = min(gallons_to_buy, self.tank_capacity - curr_fuel)

                    if gallons_to_buy > 0.01:
                        cost = calculate_cost(gallons_to_buy, curr_candidate['retail_price'])
                        stops.append(self._format_stop(
                            len(stops) + 1,
                            curr_candidate,
                            prev_stop_dist,
                            gallons_to_buy,
                            cost
                        ))
                    # Trip completed to destination
                    break
                else:
                    # Fill tank to full capacity since this station is the cheapest available!
                    gallons_to_buy = self.tank_capacity - curr_fuel
                    cost = calculate_cost(gallons_to_buy, curr_candidate['retail_price'])
                    stops.append(self._format_stop(
                        len(stops) + 1,
                        curr_candidate,
                        prev_stop_dist,
                        gallons_to_buy,
                        cost
                    ))
                    prev_stop_dist = curr_dist
                    curr_fuel = self.tank_capacity

                    # Now choose next stop from reachable stations that can continue the journey
                    # Pick the one with lowest price among those reachable
                    viable_next = [
                        c for c in reachable
                        if (route_distance - c['distance_from_route_start_miles'] <= self.max_range_miles or
                            any(other['distance_from_route_start_miles'] > c['distance_from_route_start_miles'] and
                                other['distance_from_route_start_miles'] <= c['distance_from_route_start_miles'] + self.max_range_miles
                                for other in candidates))
                    ]
                    if not viable_next:
                        viable_next = reachable

                    next_stop = min(viable_next, key=lambda c: (float(c['retail_price']), -c['distance_from_route_start_miles']))
                    dist_to_next = next_stop['distance_from_route_start_miles'] - curr_dist
                    fuel_used = dist_to_next / self.mpg
                    curr_fuel -= fuel_used
                    curr_dist = next_stop['distance_from_route_start_miles']
                    curr_price = float(next_stop['retail_price'])
                    curr_candidate = next_stop

        return stops

    def _format_stop(
        self,
        sequence: int,
        candidate: dict[str, Any],
        prev_stop_dist: float,
        gallons_purchased: float,
        cost: Decimal
    ) -> dict[str, Any]:
        """Format individual stop dictionary matching API contract."""
        dist_from_start = candidate['distance_from_route_start_miles']
        dist_from_prev = round(dist_from_start - prev_stop_dist, 2)

        return {
            'sequence': sequence,
            'station_id': candidate['station_id'],
            'opis_id': candidate['opis_id'],
            'name': candidate['name'],
            'address': candidate['address'],
            'city': candidate['city'],
            'state': candidate['state'],
            'latitude': candidate['latitude'],
            'longitude': candidate['longitude'],
            'price_per_gallon': float(candidate['retail_price']),
            'distance_from_route_start_miles': dist_from_start,
            'distance_from_previous_stop_miles': dist_from_prev,
            'gallons_purchased': round(gallons_purchased, 2),
            'fuel_cost': float(cost),
        }
