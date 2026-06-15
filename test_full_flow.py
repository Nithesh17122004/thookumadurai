import requests, json, time, sys, os

BASE = "http://127.0.0.1:5000"
API = BASE + "/api/v1"

# Disable keep-alive to avoid eventlet hang
s = requests.Session()
s.headers.update({"Connection": "close"})

def log(label, data):
    print(f"\n=== {label} ===")
    if isinstance(data, dict):
        print(json.dumps(data, indent=2, default=str))
    else:
        print(data)

# 1. Health
log("HEALTH", s.get(f"{BASE}/health").json())

# 2. Login as rider_1
log("RIDER LOGIN", s.post(f"{API}/auth/rider-login", json={"username": "rider_1", "password": "rider123"}).json())

# 3. Login as rider_2
log("RIDER2 LOGIN", s.post(f"{API}/auth/rider-login", json={"username": "rider_2", "password": "rider123"}).json())

# 4. List restaurants
log("RESTAURANTS", s.get(f"{API}/restaurants").json())

# 5. Login as Google customer (mock)
log("CUSTOMER LOGIN", s.post(f"{API}/auth/google", json={"credential": "test_mock", "name": "Test User", "email": "test@example.com"}).json())

# 6. Get menu for restaurant
restaurants = s.get(f"{API}/restaurants").json().get("data", [])
if restaurants:
    r_id = restaurants[0].get("_id") or restaurants[0].get("id")
    log(f"MENU for {r_id}", s.get(f"{API}/restaurants/{r_id}/menu").json())

# 7. Create an order
log("PLACE ORDER", s.post(f"{API}/orders", json={
    "restaurant_id": r_id,
    "items": [{"menu_item_id": "test_item", "name": "Test Food", "price": 100, "quantity": 1}],
    "delivery_address": "Test Address, Madurai",
    "delivery_lat": 9.94,
    "delivery_lng": 78.09,
    "customer_name": "Test User",
    "customer_phone": "+918220927361",
    "payment_method": "mock"
}).json())

# 8. Check rider orders
print("\n=== RIDER ORDERS (need token from step 2) ===")
print("To run this, first extract the token from step 2 output above")

# Test Socket.IO connection
print("\n\n=== SOCKET.IO TEST ===")
try:
    from socketio import Client
    sio = Client()
    sio.connect(BASE, transports=['polling'])
    print(f"Socket.IO connected: {sio.connected}")
    sio.disconnect()
except Exception as e:
    print(f"Socket.IO test skipped: {e}")

print("\n\nDone. Check the outputs above to verify each step.")
