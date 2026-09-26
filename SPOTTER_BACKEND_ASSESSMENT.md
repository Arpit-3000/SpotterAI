# Spotter Backend Django Assessment — Fuel Route Optimizer

## 1. Assessment Summary

Build a backend API that accepts:

- Start location in the USA
- Finish location in the USA

The API must:

1. Calculate a drivable route between the two locations.
2. Return route/map geometry that can be displayed on a map.
3. Select cost-effective fuel stations along the route.
4. Respect the vehicle's maximum range of **500 miles**.
5. Allow multiple fuel stops when the trip is longer than 500 miles.
6. Assume fuel efficiency of **10 miles per gallon**.
7. Calculate total fuel cost.
8. Use the supplied fuel-price CSV as the source of fuel prices.
9. Minimize calls to the external routing API; ideally one route request per API request.
10. Be implemented using the latest stable Django release available when the project is built.
11. Include automated tests and clear documentation.
12. Be easy to demonstrate from Postman.

### Supplied data

The provided CSV contains **8,151 fuel-station rows** and these columns:

- `OPIS Truckstop ID`
- `Truckstop Name`
- `Address`
- `City`
- `State`
- `Rack ID`
- `Retail Price`

There are approximately **4,275 unique City + State combinations**.

---

# 2. Recommended Technical Approach

## Backend

- Python 3.12+
- Django
- Django REST Framework
- SQLite for local development
- PostgreSQL-compatible design where practical
- `requests` or `httpx` for external HTTP calls
- `pytest` + `pytest-django` for tests

## Routing / map provider

Use **OSRM** for driving directions.

OSRM can return route geometry as GeoJSON and provides route distance/duration. The application should make **one routing request** for the normal API request.

Example concept:

```text
GET /route/v1/driving/{start_lon},{start_lat};{finish_lon},{finish_lat}?overview=full&geometries=geojson
```

The routing provider should be isolated behind a service class such as:

```text
RoutingService
```

so that another provider can be substituted later.

## Geocoding

Do not geocode all fuel stations during every API request.

Instead, create a preprocessing/management command that geocodes the supplied station dataset and stores the resulting coordinates locally.

A suitable free preprocessing option is the US Census Geocoder batch API. It supports batch address geocoding with up to 10,000 records per batch.

The resulting coordinates should be stored locally in the application's database or in a generated data file.

This keeps the runtime API fast and avoids thousands of external requests.

---

# 3. Important Optimization Decision

The core challenge is not simply:

> Find the cheapest gas station.

It is:

> Find a sequence of affordable fuel stations along the selected route such that no driving segment exceeds the vehicle's 500-mile range, while minimizing total fuel cost.

The algorithm should therefore consider:

- Route position
- Distance from the previous stop
- Distance to the destination
- Fuel price
- Maximum range = 500 miles
- Fuel efficiency = 10 MPG

A practical implementation can model candidate stations as ordered points along the route.

For every candidate station, calculate:

```text
distance_from_route_start
```

Then discard stations that are too far from the route corridor.

A route corridor tolerance such as 25–40 miles can be configurable.

---

# 4. Recommended Fuel-Stop Algorithm

Use a dynamic-programming / shortest-path style optimization over candidate fuel stations.

### State

For each candidate station:

```text
station_id
route_distance_miles
price_per_gallon
```

Add the start and destination as special nodes.

### Feasibility

Two consecutive nodes can be connected only when:

```text
distance_between_nodes <= 500 miles
```

### Cost

The vehicle consumes:

```text
gallons = distance / 10
```

Fuel cost for a segment is:

```text
gallons * price_at_previous_fuel_stop
```

For a realistic strategy, model fuel purchases explicitly rather than blindly charging each segment at the next station's price.

A simpler and explainable assessment implementation is:

- Start with a full tank.
- At every selected fuel stop, purchase enough fuel to reach the next selected stop/destination.
- If a cheaper reachable station exists ahead, prefer carrying enough fuel to reach it.
- If the current station is cheaper than all reachable stations, fill the tank as much as possible.

This is the classic gas-station greedy strategy and can be implemented efficiently after route-position filtering.

The code should document the exact assumptions.

---

# 5. Important Edge Cases

The API must handle:

### Invalid locations

Return HTTP 400:

```json
{
  "error": "Unable to geocode start or finish location."
}
```

### Locations outside the USA

Reject the request with HTTP 400.

### No route

Return an appropriate error rather than crashing.

### Route longer than 500 miles

Return multiple fuel stops.

### No fuel station within range

Return a clear failure:

```json
{
  "error": "No feasible fuel-stop plan exists for this route within the 500 mile vehicle range."
}
```

### Start-to-finish distance <= 500 miles

It may be possible to return zero fuel stops if the assumed vehicle starts with a full tank.

Document this assumption clearly.

### Very long route

Do not assume that every station in the CSV is a candidate.

First reduce the candidate set using route proximity and route order.

---

# 6. Suggested API

## Endpoint

```http
POST /api/v1/route/fuel-plan/
```

## Request

```json
{
  "start": "New York, NY",
  "finish": "Chicago, IL"
}
```

Optionally support structured input:

```json
{
  "start": {
    "city": "New York",
    "state": "NY"
  },
  "finish": {
    "city": "Chicago",
    "state": "IL"
  }
}
```

## Response

Suggested structure:

```json
{
  "start": {
    "input": "New York, NY",
    "latitude": 40.7128,
    "longitude": -74.0060
  },
  "finish": {
    "input": "Chicago, IL",
    "latitude": 41.8781,
    "longitude": -87.6298
  },
  "route": {
    "distance_miles": 790.4,
    "duration_minutes": 735,
    "geometry": {
      "type": "LineString",
      "coordinates": []
    }
  },
  "vehicle": {
    "max_range_miles": 500,
    "miles_per_gallon": 10
  },
  "fuel_stops": [
    {
      "sequence": 1,
      "station_id": 123,
      "name": "Example Truck Stop",
      "address": "Example address",
      "city": "Example City",
      "state": "OH",
      "latitude": 40.123,
      "longitude": -82.123,
      "price_per_gallon": 3.19,
      "distance_from_route_start_miles": 350.2,
      "distance_from_previous_stop_miles": 350.2,
      "gallons_purchased": 35.02,
      "fuel_cost": 111.71
    }
  ],
  "fuel_summary": {
    "total_distance_miles": 790.4,
    "total_gallons_consumed": 79.04,
    "total_fuel_cost": 250.00
  }
}
```

The exact cost numbers above are illustrative only.

---

# 7. Database Design

A simple model is enough.

## FuelStation

```text
id
opis_id
name
address
city
state
rack_id
retail_price
latitude
longitude
created_at
updated_at
```

Create indexes on:

```text
state
city
retail_price
latitude
longitude
```

Do not require PostGIS for the assessment unless it materially simplifies the implementation.

---

# 8. Suggested Project Structure

```text
spotter-fuel-optimizer/
│
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── SPOTTER_BACKEND_ASSESSMENT.md
│
├── data/
│   ├── fuel-prices-for-be-assessment.csv
│   └── ...
│
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
│
├── fuel_optimizer/
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── serializers.py
│   ├── urls.py
│   ├── views.py
│   │
│   ├── services/
│   │   ├── routing.py
│   │   ├── geocoding.py
│   │   ├── route_matching.py
│   │   ├── fuel_optimizer.py
│   │   └── calculator.py
│   │
│   ├── management/
│   │   └── commands/
│   │       ├── import_fuel_prices.py
│   │       └── geocode_fuel_stations.py
│   │
│   └── tests/
│       ├── test_api.py
│       ├── test_optimizer.py
│       ├── test_calculator.py
│       └── test_services.py
│
└── postman/
    └── Spotter-Fuel-Optimizer.postman_collection.json
```

---

# 9. Environment Variables

Create:

```text
DJANGO_SECRET_KEY=change-me
DEBUG=True

ROUTING_PROVIDER=osrm

OSRM_BASE_URL=https://router.project-osrm.org

GEOCODER_BASE_URL=https://geocoding.geo.census.gov/geocoder
```

If the selected routing/geocoding provider requires an API key, keep it in `.env` and never commit it.

---

# 10. Local Setup

## Windows

Create virtual environment:

```powershell
python -m venv venv
```

Activate:

```powershell
venv\Scripts\activate
```

Install:

```powershell
pip install -r requirements.txt
```

Copy environment file:

```powershell
copy .env.example .env
```

Run migrations:

```powershell
python manage.py migrate
```

Import the fuel data:

```powershell
python manage.py import_fuel_prices data/fuel-prices-for-be-assessment.csv
```

If station coordinates have not already been prepared:

```powershell
python manage.py geocode_fuel_stations
```

Run server:

```powershell
python manage.py runserver
```

API:

```text
http://127.0.0.1:8000/api/v1/route/fuel-plan/
```

---

# 11. Testing with Postman

Method:

```text
POST
```

URL:

```text
http://127.0.0.1:8000/api/v1/route/fuel-plan/
```

Headers:

```text
Content-Type: application/json
```

Body:

```json
{
  "start": "New York, NY",
  "finish": "Chicago, IL"
}
```

Expected response:

- Route distance
- Route duration
- GeoJSON route
- Fuel stops
- Station prices
- Gallons purchased
- Cost per stop
- Total gallons
- Total fuel cost

---

# 12. Performance Strategy

The assessment explicitly asks for fast responses and minimal routing API calls.

Use these principles:

### 1. One routing API call

Do not call the routing API separately for every fuel station.

Call it once:

```text
origin -> destination
```

Use the returned route geometry locally.

### 2. Pre-geocode station data

Do not geocode 8,151 stations during an API request.

Run geocoding as a preprocessing command.

### 3. Filter stations locally

Use:

```text
state
bounding box
route corridor
route position
```

to reduce 8,151 stations to a small candidate set.

### 4. Calculate distances locally

Use Haversine distance or a geometry library for candidate filtering.

Do not call a routing API to calculate every station-to-station distance.

### 5. Cache repeated routes

Optionally cache route responses using Django cache.

Cache key example:

```text
route:{start_lat}:{start_lon}:{finish_lat}:{finish_lon}
```

This is especially useful during Postman demos.

---

# 13. Testing Requirements

Write tests for:

### API

- Valid request
- Missing start
- Missing finish
- Invalid location
- Non-USA location
- No route

### Fuel calculations

Example:

```text
100 miles / 10 MPG = 10 gallons
```

If fuel costs $3/gallon:

```text
10 * 3 = $30
```

### Range

Ensure no selected driving segment exceeds:

```text
500 miles
```

### Optimization

Given a controlled set of stations, verify that the optimizer chooses the lower-cost feasible plan.

### Multiple stops

Create a synthetic route longer than 500 miles and verify multiple stations are returned.

---

# 14. README / Documentation Should Explain

The repository README should contain:

1. Project overview
2. Architecture
3. Setup
4. Environment variables
5. CSV import
6. Geocoding preparation
7. Running the server
8. API request example
9. API response example
10. Algorithm explanation
11. External APIs
12. Performance considerations
13. Testing
14. Postman collection
15. Assumptions and limitations

---

# 15. Implementation Deliverables

The implementation delivers:

1. Clean, modular Django & Django REST Framework project structure.
2. Complete OSRM routing integration isolated behind `RoutingService`.
3. Preprocessed fuel station dataset with local spatial bounding-box and corridor matching.
4. Greedy fuel-cost optimizer respecting the 500-mile vehicle range and 10 MPG fuel efficiency.
5. Production-ready test suite covering API contracts, calculators, and optimization edge cases.
6. Postman collection for evaluation and demonstration.


---

# 16. Suggested Loom Demo — Maximum 5 Minutes

Use this structure:

### 0:00–0:30 — Introduction

Say:

> "This is my implementation of the Spotter Backend Engineer assessment. It accepts a US start and finish location, calculates a driving route, finds cost-effective fuel stops within a 500-mile vehicle range, and calculates total fuel cost using 10 MPG."

### 0:30–1:30 — Code overview

Show:

```text
models.py
routing.py
fuel_optimizer.py
views.py
management commands
tests
```

Explain that the external route API is called once and station processing happens locally.

### 1:30–3:30 — Postman

Show:

```http
POST /api/v1/route/fuel-plan/
```

Example:

```json
{
  "start": "New York, NY",
  "finish": "Chicago, IL"
}
```

Show:

- Route distance
- Route geometry
- Fuel stations
- Fuel prices
- Gallons
- Total cost

Then demonstrate a longer route requiring multiple stops.

### 3:30–4:30 — Algorithm

Explain:

> "I first calculate the route, project nearby fuel stations onto the route, remove stations outside the route corridor, and then use the 500-mile range constraint to find a cost-effective sequence of stops."

### 4:30–5:00 — Performance

Explain:

> "The route provider is called once per uncached request. Fuel stations are pre-geocoded and stored locally, so the runtime request does not make thousands of geocoding calls."

---

# 17. GitHub Checklist

Before submitting:

```text
[ ] Clean README.md
[ ] SPOTTER_BACKEND_ASSESSMENT.md
[ ] requirements.txt
[ ] .env.example
[ ] .gitignore
[ ] CSV included or setup instructions provided
[ ] Database migrations
[ ] Import command
[ ] Geocoding command
[ ] API implemented
[ ] Optimization implemented
[ ] Tests passing
[ ] Postman collection
[ ] No API keys committed
[ ] No __pycache__
[ ] No .env committed
[ ] GitHub repository is accessible
```

Never commit:

```text
.env
secret keys
API tokens
local virtual environment
__pycache__
*.pyc
```

---

# 18. Engineering Notes

The most important thing to demonstrate in the interview/assessment is not just that the endpoint works.

Demonstrate that you understood the constraints:

```text
8,151 fuel stations
        ↓
preprocessed/geocoded once
        ↓
local database
        ↓
ONE route API call
        ↓
route geometry
        ↓
local candidate filtering
        ↓
500-mile feasibility
        ↓
fuel-cost optimization
        ↓
JSON response
```

This architecture directly addresses the assessment's performance requirement while keeping the implementation understandable.
