# Spotter Backend Assessment — Fuel Route Optimizer

A high-performance Django REST Framework API that accepts a start and destination location within the United States, calculates a drivable route via OSRM, and identifies optimal, cost-effective fuel stops along the route corridor while respecting vehicle range and fuel tank constraints.

---

## 1. Overview & Core Requirements

- **Vehicle Range**: 500 miles on a full tank.
- **Fuel Efficiency**: 10 miles per gallon (MPG).
- **Tank Capacity**: 50 gallons ($500 \text{ miles} / 10 \text{ MPG}$).
- **Starting Condition**: Vehicle departs the start location with a full tank (50 gallons).
- **Cost Calculation**: Fuel consumed is calculated as $\text{distance} / 10$. Initial fuel is pre-existing; incremental fuel cost reflects fuel purchased at selected stops.
- **Data Source**: Supplied OPIS fuel pricing CSV containing 8,151 truck stops across North America.
- **Performance Strategy**: Exactly **one** external routing API request per route query; zero runtime geocoding of stations; local spatial indexing and distance calculations.

---

## 2. Architecture & Pipeline

```text
HTTP POST /api/v1/route/fuel-plan/
                │
        Input Validation & Geocoding
 (Fast cache / Census Geocoder / Nominatim)
                │
      Single External OSRM Route Request
                │
      Route Geometry & Distance (GeoJSON)
                │
      Route Corridor Spatial Filtering
   (Bounding box query + segment bucketing)
                │
   Candidate Station Projection & Ordering
                │
    Greedy Fuel Stop & Purchase Optimizer
 (Max range: 500 mi | Tank cap: 50 gal | 10 MPG)
                │
          JSON Response
```

### Key Services

- **`fuel_optimizer/services/routing.py` (`RoutingService`)**: Encapsulates external routing communication with OSRM (`/route/v1/driving/`). Translates GeoJSON geometries, distances (meters to miles), and durations (seconds to minutes) with in-memory caching.
- **`fuel_optimizer/services/geocoding.py` (`GeocodingService`)**: Converts city/state or addresses to geographic coordinates. Validates US boundary constraints and rejects non-USA queries.
- **`fuel_optimizer/services/route_matching.py` (`RouteMatchingService`)**: Performs bounding-box pre-filtering in the database and projects candidate stations onto the route polyline using spatial segment grid bucketing in under 20ms.
- **`fuel_optimizer/services/calculator.py`**: Pure utility functions for Haversine distance, perpendicular cross-track projection, gallon usage, and monetary rounding using `Decimal`.
- **`fuel_optimizer/services/fuel_optimizer.py` (`FuelOptimizerService`)**: Implements the classic minimum-cost greedy gas-station algorithm.

---

## 3. Technology Stack

- **Language**: Python 3.12+
- **Framework**: Django 5.2 / Django REST Framework 3.18
- **Database**: SQLite (PostgreSQL compatible design)
- **Routing**: Open Source Routing Machine (OSRM)
- **Geocoding**: US Census Bureau Geocoder Batch API + Nominatim fallback
- **Testing**: `pytest` and `pytest-django`

---

## 4. Setup & Installation

### Windows PowerShell

1. **Clone the repository and enter the directory**:
   ```powershell
   cd D:\SpotterAI
   ```

2. **Create and activate a virtual environment**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   ```powershell
   copy .env.example .env
   ```

5. **Apply database migrations**:
   ```powershell
   python manage.py migrate
   ```

6. **Import fuel prices dataset**:
   ```powershell
   python manage.py import_fuel_prices data/fuel-prices-for-be-assessment.csv
   ```
   *(Pre-computed coordinates in `data/station_coordinates.json` will automatically populate coordinates for 6,600+ US stations immediately).*

7. **(Optional) Run batch geocoding**:
   ```powershell
   python manage.py geocode_fuel_stations
   ```

8. **Start the local server**:
   ```powershell
   python manage.py runserver
   ```
   The API will be accessible at: `http://127.0.0.1:8000/api/v1/route/fuel-plan/`

---

## 5. API Reference

### Endpoint

```http
POST /api/v1/route/fuel-plan/
Content-Type: application/json
```

### Request Payload

Supports standard string inputs or structured city/state dictionaries:

```json
{
  "start": "New York, NY",
  "finish": "Chicago, IL"
}
```

*Or structured:*

```json
{
  "start": { "city": "New York", "state": "NY" },
  "finish": { "city": "Chicago", "state": "IL" }
}
```

### Successful Response Example (`200 OK`)

```json
{
  "start": {
    "input": "New York, NY",
    "formatted_address": "New York, NY, USA",
    "latitude": 40.7128,
    "longitude": -74.006
  },
  "finish": {
    "input": "Chicago, IL",
    "formatted_address": "Chicago, IL, USA",
    "latitude": 41.8781,
    "longitude": -87.6298
  },
  "route": {
    "distance_miles": 790.38,
    "duration_minutes": 735.0,
    "geometry": {
      "type": "LineString",
      "coordinates": [
        [-74.006, 40.7128],
        [-87.6298, 41.8781]
      ]
    }
  },
  "vehicle": {
    "max_range_miles": 500.0,
    "miles_per_gallon": 10.0
  },
  "fuel_stops": [
    {
      "sequence": 1,
      "station_id": 481,
      "opis_id": 1420,
      "name": "PILOT TRAVEL CENTER #481",
      "address": "I-80 EXIT 173 & PA-64",
      "city": "Lamar",
      "state": "PA",
      "latitude": 41.0114,
      "longitude": -77.5258,
      "price_per_gallon": 3.129,
      "distance_from_route_start_miles": 352.4,
      "distance_from_previous_stop_miles": 352.4,
      "gallons_purchased": 29.04,
      "fuel_cost": 90.87
    }
  ],
  "fuel_summary": {
    "total_distance_miles": 790.38,
    "total_gallons_consumed": 79.04,
    "total_fuel_cost": 90.87
  }
}
```

### Error Responses

#### Non-USA Location (`400 Bad Request`)
```json
{
  "error": {
    "code": "NON_USA_LOCATION",
    "message": "Location 'Paris, France' is outside the United States."
  }
}
```

#### Validation Error (`400 Bad Request`)
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "This field is required.",
    "details": { "finish": ["This field is required."] }
  }
}
```

#### Infeasible Route Gap (`422 Unprocessable Entity`)
```json
{
  "error": {
    "code": "NO_FEASIBLE_FUEL_PLAN",
    "message": "No feasible fuel-stop plan exists for this route within the 500 mile vehicle range."
  }
}
```

---

## 6. Optimization Algorithm Details

The optimizer models vehicle progression as a discrete greedy decision process:
1. **Initial Full Tank**: The vehicle leaves the start location with 50 gallons (500-mile capacity).
2. **Short Trips ($\le 500$ miles)**: If the destination distance is less than or equal to 500 miles, zero stops are returned because the initial full tank safely reaches the destination.
3. **Long Trips ($> 500$ miles)**:
   - Stations outside the 30-mile route corridor are discarded.
   - Remaining candidates are projected onto the route line string and ordered by distance from start.
   - From the current station / start, the algorithm inspects all reachable stations within the 500-mile range.
   - **Case A (Cheaper station ahead)**: The vehicle buys just enough fuel to reach the cheaper station ahead, minimizing fuel bought at the more expensive current price.
   - **Case B (Current station is the cheapest in range)**: If the destination is within range, it buys just enough fuel to reach the destination. If the destination is farther than 500 miles, it fills the tank to maximum capacity (50 gallons) and proceeds to the lowest-priced reachable station.

---

## 7. Running Tests

Execute the automated test suite with pytest:

```powershell
.\venv\Scripts\pytest
```

Output:
```text
============================= 34 passed in 0.66s ==============================
```

All 34 unit, integration, and service tests pass completely offline using mocked network fixtures.

---

## 8. Postman Collection

Import `postman/Spotter-Fuel-Optimizer.postman_collection.json` into Postman.
Preconfigured requests include:
1. `New York to Chicago (Single Stop)`
2. `Los Angeles to Las Vegas (Under 500 mi - 0 Stops)`
3. `New York to Los Angeles (Long-Distance Multi-Stop)`
4. `Structured City/State Input`
5. `Error - Location Outside USA`
6. `Error - Missing Required Field`
