# Spotter Backend Assessment — Complete Demo & Presentation Guide

This document contains everything needed to present, demonstrate, and submit the **Spotter Fuel Route Optimizer** project:
1. **Loom Video Script (with exact timings, screen cues, and word-for-word transcript)**
2. **How to Run & See the Output Locally**
3. **All Postman Requests (Endpoints, Headers, Bodies, and Responses)**
4. **GitHub & Render Cloud Deployment Instructions**
5. **Project Architecture & Algorithm Summary**

---

# 1. 🎬 Loom Video Script (Max 5 Minutes)

Use this complete script to record your Loom presentation. Keep this file open on a second screen or side-by-side.

---

### **[0:00 – 0:30] SECTION 1: Introduction**

- 🖥️ **WHAT TO SHOW ON SCREEN**: 
  - Open **VS Code** with the project folder.
  - Show the project file tree on the left sidebar and [README.md](file:///d:/SpotterAI/README.md) open in the editor.

- 🗣️ **WHAT TO SAY**:
  > *"Hi everyone, my name is Aman, and this is my submission for the Spotter Backend Engineer assessment — the Fuel Route Optimizer.*
  >
  > *The goal of this project is to build a robust Django REST Framework backend that accepts any start and finish location in the United States, computes the optimal driving route, and selects the most cost-effective fuel stops from the provided OPIS dataset.*
  >
  > *The vehicle operates under realistic constraints: a maximum range of 500 miles on a full tank, fuel efficiency of 10 miles per gallon, and the assumption that the truck begins its journey with a full 50-gallon tank.*
  >
  > *I've built a clean, modular service architecture that makes only a single call to the external routing engine and handles everything else locally with sub-second response times."*

---

### **[0:30 – 1:30] SECTION 2: Architecture & Codebase Overview**

- 🖥️ **WHAT TO SHOW ON SCREEN**:
  - Keep VS Code open.
  - Open and click through these 5 files:
    1. [fuel_optimizer/models.py](file:///d:/SpotterAI/fuel_optimizer/models.py)
    2. [fuel_optimizer/services/routing.py](file:///d:/SpotterAI/fuel_optimizer/services/routing.py)
    3. [fuel_optimizer/services/route_matching.py](file:///d:/SpotterAI/fuel_optimizer/services/route_matching.py)
    4. [fuel_optimizer/services/fuel_optimizer.py](file:///d:/SpotterAI/fuel_optimizer/services/fuel_optimizer.py)
    5. [fuel_optimizer/views.py](file:///d:/SpotterAI/fuel_optimizer/views.py)

- 🗣️ **WHAT TO SAY**:
  > *(Show `models.py`)*
  > *"Starting with `models.py`: our `FuelStation` model stores truck stop metadata, retail price as a Decimal to prevent floating-point precision issues, and latitude/longitude with compound database indexes on state, city, price, and coordinates.*
  >
  > *(Switch to `routing.py`)*
  > *In `routing.py`, all external routing logic is cleanly isolated behind a `RoutingService`. It calls OSRM driving directions and returns GeoJSON line geometry, converting distance and duration into miles and minutes. Crucially, as requested by the assessment, the API makes exactly ONE external routing call per request.*
  >
  > *(Switch to `route_matching.py`)*
  > *In `route_matching.py`, we filter the 8,000+ stations down to a 30-mile route corridor using spatial grid bucketing and Haversine projection, running in under 50 milliseconds.*
  >
  > *(Switch to `fuel_optimizer.py`)*
  > *In `fuel_optimizer.py`, we implement the classic greedy gas-station algorithm.*
  >
  > *(Switch to `views.py`)*
  > *And in `views.py`, the view functions purely as an orchestrator, keeping all business logic strictly within service classes."*

---

### **[1:30 – 3:30] SECTION 3: Live Postman API Demonstration**

- 🖥️ **WHAT TO SHOW ON SCREEN**:
  - Switch window to **Postman**.
  - Show the collection **Spotter Fuel Optimizer API** on the left sidebar.
  - Run the following requests one by one:

#### A. New York to Chicago (Trip > 500 Miles)
- 👉 **Action**: Click `"1. New York to Chicago"` $\rightarrow$ Click **Send**.
- 🗣️ **Say**:
  > *"Now let's switch to Postman to demonstrate the API.*
  >
  > *Our first request is from New York to Chicago. When I click Send, notice how fast the response returns.*
  >
  > *(Point cursor at response)*
  > *The route distance is 790.5 miles with full GeoJSON geometry.*
  > *Because the truck leaves New York with a 500-mile full tank, it only needs two strategic fuel stops: Sheetz in Youngstown, Ohio at $3.06 per gallon, and S&G in Toledo at $3.01.*
  > *The response gives us exact sequence numbers, gallons purchased, stop fuel costs, and a fuel summary totaling $87.68."*

#### B. Los Angeles to Las Vegas (Trip $\le$ 500 Miles)
- 👉 **Action**: Click `"2. Los Angeles to Las Vegas"` $\rightarrow$ Click **Send**.
- 🗣️ **Say**:
  > *"Next, let's test a route under 500 miles: Los Angeles to Las Vegas.*
  >
  > *(Point cursor at response)*
  > *The route is 270.38 miles. Notice that `fuel_stops` returns an empty array, and the fuel cost is zero dollars. This honors the requirement that the truck departs with a full tank of fuel, so no mid-route refueling is needed."*

#### C. New York to Los Angeles (Cross-Country Multi-Stop)
- 👉 **Action**: Click `"3. New York to Los Angeles"` $\rightarrow$ Click **Send**.
- 🗣️ **Say**:
  > *"Now let's test a true long-distance cross-country trip: New York to Los Angeles.*
  >
  > *(Point cursor at response)*
  > *This is a 2,794-mile route spanning the entire continent. The optimizer calculates 12 optimal fuel stops.*
  > *Most importantly: if we inspect the distance between each consecutive stop, every single driving leg is strictly under 500 miles, completely satisfying the vehicle range constraint."*

#### D. Error Handling (Location Outside USA)
- 👉 **Action**: Click `"5. Error - Location Outside USA"` $\rightarrow$ Click **Send**.
- 🗣️ **Say**:
  > *"We also have robust validation. If a user supplies a location outside the United States, like 'London, UK', the API cleanly rejects it with HTTP 400 and a structured `NON_USA_LOCATION` error code without leaking any internal stack traces."*

---

### **[3:30 – 4:30] SECTION 4: Optimization Algorithm Explanation**

- 🖥️ **WHAT TO SHOW ON SCREEN**:
  - Switch back to **VS Code**.
  - Open [fuel_optimizer/services/fuel_optimizer.py](file:///d:/SpotterAI/fuel_optimizer/services/fuel_optimizer.py) and scroll to `_run_greedy_optimizer` (around line 125).

- 🗣️ **WHAT TO SAY**:
  > *"Let's take a minute to explain the optimization algorithm in `fuel_optimizer.py`:*
  >
  > *The core challenge is not simply finding the cheapest gas station in the country, but finding a feasible sequence of affordable stops where no leg exceeds 500 miles.*
  >
  > *Here is how our greedy optimizer solves this:*
  > 1. *We start at the origin with a full tank of 50 gallons.*
  > 2. *From the current stop, we look ahead at all reachable stations within our 500-mile vehicle range.*
  > 3. *If there is a cheaper station ahead within reach, we purchase only enough fuel to reach that cheaper station. This prevents buying expensive gas when cheaper gas is available just down the road.*
  > 4. *If the current station is cheaper than all reachable stations ahead, it's the local minimum, so we fill the tank completely to 50 gallons and then proceed to the lowest-cost reachable station.*
  > 5. *Finally, if there is ever a gap along the route greater than 500 miles with no stations, the system throws a `NoFeasibleFuelPlanError` returning HTTP 422."*

---

### **[4:30 – 5:00] SECTION 5: Automated Tests & Conclusion**

- 🖥️ **WHAT TO SHOW ON SCREEN**:
  - Open the integrated terminal in VS Code.
  - Run: `.\venv\Scripts\pytest`
  - Let the terminal show **34 passed in ~0.7 seconds**.

- 🗣️ **WHAT TO SAY**:
  > *"To ensure reliability, I've written a comprehensive automated test suite with pytest.*
  >
  > *(Point cursor at the terminal)*
  > *All 34 unit and integration tests pass in under one second. They test math formulas, boundary conditions, edge cases, CSV idempotency, and API contracts with fully mocked external services.*
  >
  > *I have also committed all setup scripts, environment templates, and the Postman collection to the repository. The application is production-ready and configured for 1-click native deployment on Render.*
  >
  > *Thank you for reviewing my assessment, and I look forward to discussing the implementation further!"*

---

# 2. How to Run the Project Locally

### Prerequisites
- Python 3.12+
- Windows PowerShell / Linux Terminal

### Commands to Run

```powershell
# 1. Navigate to directory
cd D:\SpotterAI

# 2. Activate virtual environment
.\venv\Scripts\activate

# 3. Start local development server
python manage.py runserver
```

The API will be available at:
`http://127.0.0.1:8000/api/v1/route/fuel-plan/`

### Automated End-to-End Test Script
To see live API output for all 4 scenarios in your terminal:
```powershell
.\venv\Scripts\python test_client.py
```

### Running the Test Suite
```powershell
.\venv\Scripts\pytest
```

---

# 3. Postman API Reference & Requests

The complete Postman collection is located at:
`D:\SpotterAI\postman\Spotter-Fuel-Optimizer.postman_collection.json`

### Request 1: New York, NY to Chicago, IL
- **Method**: `POST`
- **URL**: `http://127.0.0.1:8000/api/v1/route/fuel-plan/`
- **Headers**: `Content-Type: application/json`
- **Body**:
```json
{
  "start": "New York, NY",
  "finish": "Chicago, IL"
}
```
- **Response**: Status `200 OK`, 790.5 miles, 2 stops, $87.68 total fuel cost.

### Request 2: Los Angeles, CA to Las Vegas, NV (Under 500 Miles)
- **Method**: `POST`
- **URL**: `http://127.0.0.1:8000/api/v1/route/fuel-plan/`
- **Headers**: `Content-Type: application/json`
- **Body**:
```json
{
  "start": "Los Angeles, CA",
  "finish": "Las Vegas, NV"
}
```
- **Response**: Status `200 OK`, 270.38 miles, 0 stops (starts with full tank), $0.00 fuel cost.

### Request 3: New York, NY to Los Angeles, CA (Cross-Country)
- **Method**: `POST`
- **URL**: `http://127.0.0.1:8000/api/v1/route/fuel-plan/`
- **Headers**: `Content-Type: application/json`
- **Body**:
```json
{
  "start": "New York, NY",
  "finish": "Los Angeles, CA"
}
```
- **Response**: Status `200 OK`, 2,794.22 miles, 12 stops, all legs $\le 500$ miles.

### Request 4: Structured City/State Input
- **Method**: `POST`
- **URL**: `http://127.0.0.1:8000/api/v1/route/fuel-plan/`
- **Headers**: `Content-Type: application/json`
- **Body**:
```json
{
  "start": { "city": "Dallas", "state": "TX" },
  "finish": { "city": "Atlanta", "state": "GA" }
}
```
- **Response**: Status `200 OK`.

### Request 5: Validation Error (Missing Start)
- **Method**: `POST`
- **URL**: `http://127.0.0.1:8000/api/v1/route/fuel-plan/`
- **Headers**: `Content-Type: application/json`
- **Body**:
```json
{
  "finish": "Chicago, IL"
}
```
- **Response**: Status `400 Bad Request`, code `VALIDATION_ERROR`.

### Request 6: Location Outside USA
- **Method**: `POST`
- **URL**: `http://127.0.0.1:8000/api/v1/route/fuel-plan/`
- **Headers**: `Content-Type: application/json`
- **Body**:
```json
{
  "start": "London, UK",
  "finish": "Chicago, IL"
}
```
- **Response**: Status `400 Bad Request`, code `NON_USA_LOCATION`.

---

# 4. GitHub & Render Deployment Guide

### Push to GitHub

```powershell
cd D:\SpotterAI
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/spotter-fuel-optimizer.git
git push -u origin main
```

### Deploy to Render in 2 Minutes (Free)

1. Log into [render.com](https://render.com) using GitHub.
2. Click **New +** $\rightarrow$ **Web Service**.
3. Select your repository `spotter-fuel-optimizer`.
4. Render will read [render.yaml](file:///d:/SpotterAI/render.yaml) automatically:
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
5. Click **Deploy Web Service**!
6. Once deployed, you get a public URL:
   `https://spotter-fuel-optimizer.onrender.com/api/v1/route/fuel-plan/`
