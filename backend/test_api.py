import requests

BASE = 'http://127.0.0.1:5000/api/v1'
H = {'Authorization': 'Bearer dev-token', 'Content-Type': 'application/json'}

# Test 1: Dashboard
r = requests.get(BASE + '/admin/dashboard', headers=H)
d = r.json()
print("Dashboard:", r.status_code, "success=", d.get("success"), "data=", d.get("data"))

# Test 2: Create Restaurant
data = {
    'name': 'Test Biriyani House',
    'owner_name': 'Murugan K',
    'owner_phone': '9876543210',
    'cuisine': 'Biryani',
    'area': 'KK Nagar',
    'address': '10, Main Street, KK Nagar, Madurai'
}
r = requests.post(BASE + '/admin/restaurants', headers=H, json=data)
print("Create Restaurant:", r.status_code, r.json())

# Test 3: List Restaurants
r = requests.get(BASE + '/admin/restaurants', headers=H)
d = r.json()
rests = d.get("data", {}).get("restaurants", [])
print("List Restaurants:", r.status_code, "count=", len(rests))
for rest in rests:
    print("  -", rest.get("name"), "|", rest.get("area"))
