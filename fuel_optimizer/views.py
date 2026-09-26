import time
import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings

from .serializers import FuelPlanRequestSerializer
from .services.geocoding import GeocodingService, GeocodingError, NonUSALocationError
from .services.routing import RoutingService, RoutingError
from .services.route_matching import RouteMatchingService
from .services.fuel_optimizer import FuelOptimizerService, NoFeasibleFuelPlanError

logger = logging.getLogger(__name__)


class FuelPlanView(APIView):
    """
    POST /api/v1/route/fuel-plan/
    
    Accepts start and finish locations (USA only), computes driving directions via OSRM,
    filters fuel stations along the route corridor, and solves the optimal fuel purchase plan.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.geocoding_service = GeocodingService()
        self.routing_service = RoutingService()
        self.route_matching_service = RouteMatchingService()
        self.fuel_optimizer_service = FuelOptimizerService()

    def post(self, request, *args, **kwargs):
        req_start_time = time.perf_counter()

        serializer = FuelPlanRequestSerializer(data=request.data)
        if not serializer.is_valid():
            first_err = next(iter(serializer.errors.values()))
            err_msg = first_err[0] if isinstance(first_err, list) else str(first_err)
            return Response(
                {
                    'error': {
                        'code': 'VALIDATION_ERROR',
                        'message': err_msg,
                        'details': serializer.errors,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        start_input = serializer.validated_data['start']
        finish_input = serializer.validated_data['finish']

        # 1. Geocode Start & Finish Locations
        try:
            start_lat, start_lon, start_label = self.geocoding_service.geocode(start_input)
            finish_lat, finish_lon, finish_label = self.geocoding_service.geocode(finish_input)
        except NonUSALocationError as e:
            logger.warning(f"Non-USA location rejected: {e}")
            return Response(
                {
                    'error': {
                        'code': 'NON_USA_LOCATION',
                        'message': str(e),
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except GeocodingError as e:
            logger.warning(f"Geocoding failed: {e}")
            return Response(
                {
                    'error': {
                        'code': 'INVALID_LOCATION',
                        'message': str(e),
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected geocoding exception: {e}")
            return Response(
                {
                    'error': {
                        'code': 'GEOCODING_SERVICE_ERROR',
                        'message': 'Failed to resolve location coordinates.',
                    }
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 2. Driving Route Calculation (1 routing API call)
        try:
            route_data = self.routing_service.get_route(
                start_lat=start_lat,
                start_lon=start_lon,
                finish_lat=finish_lat,
                finish_lon=finish_lon
            )
        except RoutingError as e:
            logger.error(f"Routing error: {e}")
            return Response(
                {
                    'error': {
                        'code': 'ROUTING_FAILED',
                        'message': str(e),
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected routing exception: {e}")
            return Response(
                {
                    'error': {
                        'code': 'ROUTING_UNAVAILABLE',
                        'message': 'Unable to calculate driving route.',
                    }
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        route_distance_miles = route_data['distance_miles']
        route_geometry = route_data['geometry']

        # 3. Candidate Station Corridor Matching
        match_start = time.perf_counter()
        candidate_stations = self.route_matching_service.find_candidate_stations(
            geometry=route_geometry,
            route_distance_miles=route_distance_miles
        )
        match_elapsed = time.perf_counter() - match_start

        # 4. Optimal Fuel Plan Calculation
        opt_start = time.perf_counter()
        try:
            plan = self.fuel_optimizer_service.optimize(
                route_distance_miles=route_distance_miles,
                candidate_stations=candidate_stations
            )
        except NoFeasibleFuelPlanError as e:
            logger.warning(f"No feasible fuel plan: {e}")
            return Response(
                {
                    'error': {
                        'code': 'NO_FEASIBLE_FUEL_PLAN',
                        'message': str(e),
                    }
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        opt_elapsed = time.perf_counter() - opt_start

        total_req_elapsed = time.perf_counter() - req_start_time

        logger.info(
            f"Fuel plan successfully generated: "
            f"Distance: {route_distance_miles} mi | "
            f"Candidates: {len(candidate_stations)} | "
            f"Stops: {len(plan['fuel_stops'])} | "
            f"Matching: {match_elapsed:.3f}s | "
            f"Opt: {opt_elapsed:.4f}s | "
            f"Total: {total_req_elapsed:.3f}s"
        )

        response_payload = {
            'start': {
                'input': start_input if isinstance(start_input, str) else f"{start_input.get('city')}, {start_input.get('state')}",
                'formatted_address': start_label,
                'latitude': start_lat,
                'longitude': start_lon,
            },
            'finish': {
                'input': finish_input if isinstance(finish_input, str) else f"{finish_input.get('city')}, {finish_input.get('state')}",
                'formatted_address': finish_label,
                'latitude': finish_lat,
                'longitude': finish_lon,
            },
            'route': {
                'distance_miles': route_distance_miles,
                'duration_minutes': route_data['duration_minutes'],
                'geometry': route_geometry,
            },
            'vehicle': {
                'max_range_miles': self.fuel_optimizer_service.max_range_miles,
                'miles_per_gallon': self.fuel_optimizer_service.mpg,
            },
            'fuel_stops': plan['fuel_stops'],
            'fuel_summary': plan['fuel_summary'],
        }

        return Response(response_payload, status=status.HTTP_200_OK)
