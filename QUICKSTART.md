# Spotter Fuel Route Optimizer — Quick Start & Notes

Hey there! This is my submission for the Spotter Backend Engineer coding assessment.

Here is a quick overview of what the application does, how I designed it, and how you can run it locally in under two minutes.

---

## What My Project Does

The API accepts any **start** and **finish** location in the United States (as text like `"New York, NY"` or structured JSON like `{"city": "New York", "state": "NY"}`) and returns:
1. The drivable route with full GeoJSON line geometry, total miles, and estimated trip time.
2. A cost-effective sequence of fuel stops along the route corridor.
3. Fuel purchased, price per gallon, and the total fuel cost.

### Key Rules & Logic I Implemented:
- **Vehicle Constraints**: 500-mile max range on a full tank, 10 MPG fuel efficiency (meaning tank capacity is exactly 50 gallons).
- **Starting Condition**: The truck departs with a full 50-gallon tank. If the trip is 500 miles or less (e.g., LA to Las Vegas), 0 stops are needed and cost is $0.00.
- **Single Routing Request**: The service calls OSRM driving directions **only once** per route query. It never makes slow per-station routing calls.
- **Fast Corridor Matching**: Fuel stations are pre-geocoded in SQLite. At runtime, the API filters stations within a 30-mile corridor using spatial grid cells and projects them onto the polyline in under 50ms.
- **Greedy Optimization**:
  - While driving, if a cheaper station exists ahead within 500 miles, the truck buys just enough fuel to reach that cheaper station.
  - If the current station is the cheapest in the 500-mile neighborhood, it fills the tank completely to 50 gallons.
  - No single driving leg between stops ever exceeds 500 miles.

---

## How to Run It Locally

### 1. Setup Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup Environment Variables & Database
```bash
# Copy env template
copy .env.example .env    # On Linux/macOS: cp .env.example .env

# Run database migrations
python manage.py migrate

# Import the OPIS fuel prices dataset (coordinates are loaded automatically)
python manage.py import_fuel_prices data/fuel-prices-for-be-assessment.csv
```

### 4. Run the Server
```bash
python manage.py runserver
```
The API is now live at: `http://127.0.0.1:8000/api/v1/route/fuel-plan/`

### 5. Run the Automated Tests
```bash
pytest
```
All 34 unit and integration tests run offline with mocked network calls and pass in under 1 second.

---

## Quick API Test

You can test the running server with `curl`:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/route/fuel-plan/ \
  -H "Content-Type: application/json" \
  -d '{"start": "New York, NY", "finish": "Chicago, IL"}'
```

Or import `postman/Spotter-Fuel-Optimizer.postman_collection.json` into Postman to test all routes and validation errors with one click.
