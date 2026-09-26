import requests
import json

url = 'http://127.0.0.1:8000/api/v1/route/fuel-plan/'
headers = {'Content-Type': 'application/json'}

print("=== TEST 1: New York, NY -> Chicago, IL ===")
payload1 = {'start': 'New York, NY', 'finish': 'Chicago, IL'}
resp1 = requests.post(url, json=payload1, headers=headers, timeout=30)
print(f"Status: {resp1.status_code}")
data1 = resp1.json()
print("Route distance:", data1.get('route', {}).get('distance_miles'), "miles")
print("Route duration:", data1.get('route', {}).get('duration_minutes'), "minutes")
print(f"Stops returned: {len(data1.get('fuel_stops', []))}")
for stop in data1.get('fuel_stops', []):
    print(f"  Stop {stop['sequence']}: {stop['name']} at {stop['city']}, {stop['state']} (${stop['price_per_gallon']:.2f}/gal) | {stop['gallons_purchased']:.2f} gal | ${stop['fuel_cost']:.2f}")
print("Fuel summary:", data1.get('fuel_summary'))

print("\n=== TEST 2: Los Angeles, CA -> Las Vegas, NV (under 500 miles) ===")
payload2 = {'start': 'Los Angeles, CA', 'finish': 'Las Vegas, NV'}
resp2 = requests.post(url, json=payload2, headers=headers, timeout=30)
print(f"Status: {resp2.status_code}")
data2 = resp2.json()
print("Route distance:", data2.get('route', {}).get('distance_miles'), "miles")
print("Fuel stops count:", len(data2.get('fuel_stops', [])))
print("Fuel summary:", data2.get('fuel_summary'))

print("\n=== TEST 3: Cross-Country Multi-Stop (New York, NY -> Los Angeles, CA) ===")
payload3 = {'start': 'New York, NY', 'finish': 'Los Angeles, CA'}
resp3 = requests.post(url, json=payload3, headers=headers, timeout=30)
print(f"Status: {resp3.status_code}")
data3 = resp3.json()
print("Route distance:", data3.get('route', {}).get('distance_miles'), "miles")
print("Fuel stops count:", len(data3.get('fuel_stops', [])))
for stop in data3.get('fuel_stops', []):
    print(f"  Stop {stop['sequence']}: {stop['name']} in {stop['city']}, {stop['state']} (mile {stop['distance_from_route_start_miles']:.1f}) | ${stop['price_per_gallon']:.2f}/gal | {stop['gallons_purchased']:.2f} gal | ${stop['fuel_cost']:.2f}")
print("Fuel summary:", data3.get('fuel_summary'))

# Check that every leg <= 500 miles
stops = data3.get('fuel_stops', [])
prev = 0.0
for s in stops:
    leg = s['distance_from_route_start_miles'] - prev
    assert leg <= 500.0, f"Leg {leg} exceeded 500 miles!"
    prev = s['distance_from_route_start_miles']
dest_leg = data3['route']['distance_miles'] - prev
assert dest_leg <= 500.0, f"Destination leg {dest_leg} exceeded 500 miles!"
print("Verified: ALL driving legs are strictly <= 500 miles!")

print("\n=== TEST 4: Invalid Non-USA Location (London, UK) ===")
payload4 = {'start': 'London, UK', 'finish': 'Chicago, IL'}
resp4 = requests.post(url, json=payload4, headers=headers, timeout=30)
print(f"Status: {resp4.status_code}")
print("Error payload:", resp4.json())
