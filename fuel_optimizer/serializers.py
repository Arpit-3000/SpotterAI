from rest_framework import serializers


class LocationField(serializers.Field):
    """
    Custom field accepting either a location string (e.g. "New York, NY")
    or a structured dictionary (e.g. {"city": "New York", "state": "NY"}).
    """
    def to_internal_value(self, data):
        if data is None:
            raise serializers.ValidationError("Location cannot be null.")
        if isinstance(data, str):
            val = data.strip()
            if not val:
                raise serializers.ValidationError("Location cannot be an empty string.")
            return val
        if isinstance(data, dict):
            # Check for city/state format
            if 'city' in data or 'state' in data:
                city = str(data.get('city', '')).strip()
                state = str(data.get('state', '')).strip()
                if not city or not state:
                    raise serializers.ValidationError("Both 'city' and 'state' are required in structured location.")
                return {'city': city, 'state': state}
            # Check for latitude/longitude format
            if 'latitude' in data and 'longitude' in data:
                try:
                    lat = float(data['latitude'])
                    lon = float(data['longitude'])
                    return {'latitude': lat, 'longitude': lon, 'name': str(data.get('name', ''))}
                except (ValueError, TypeError):
                    raise serializers.ValidationError("Latitude and longitude must be numbers.")
            raise serializers.ValidationError("Structured location must specify ('city', 'state') or ('latitude', 'longitude').")
        raise serializers.ValidationError("Location must be a string or an object.")

    def to_representation(self, value):
        return value


class FuelPlanRequestSerializer(serializers.Serializer):
    """Serializer for POST /api/v1/route/fuel-plan/"""
    start = LocationField(required=True)
    finish = LocationField(required=True)


class FuelStopSerializer(serializers.Serializer):
    """Serializer for individual fuel stops."""
    sequence = serializers.IntegerField()
    station_id = serializers.IntegerField()
    opis_id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    price_per_gallon = serializers.FloatField()
    distance_from_route_start_miles = serializers.FloatField()
    distance_from_previous_stop_miles = serializers.FloatField()
    gallons_purchased = serializers.FloatField()
    fuel_cost = serializers.FloatField()


class FuelSummarySerializer(serializers.Serializer):
    """Serializer for total fuel cost and consumption summary."""
    total_distance_miles = serializers.FloatField()
    total_gallons_consumed = serializers.FloatField()
    total_fuel_cost = serializers.FloatField()


class FuelPlanResponseSerializer(serializers.Serializer):
    """Serializer documenting the complete fuel plan response."""
    start = serializers.DictField()
    finish = serializers.DictField()
    route = serializers.DictField()
    vehicle = serializers.DictField()
    fuel_stops = FuelStopSerializer(many=True)
    fuel_summary = FuelSummarySerializer()
