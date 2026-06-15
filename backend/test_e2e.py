"""Full end-to-end API test for Thooku Madurai v2.0"""
import requests, time

BASE = 'http://127.0.0.1:5000/api/v1'
DEV_H = {'Authorization': 'Bearer dev-token', 'Content-Type': 'application/json'}

ok = 0; fail = 0
def check(label, cond, extra=''):
    global ok, fail
    if cond:
        print(f'  ✅ {label}' + (f' — {extra}' if extra else ''))
        ok += 1
    else:
        print(f'  ❌ FAIL: {label}' + (f' — {extra}' if extra else ''))
        fail += 1

print('\n══════════════════════════════════')
print('   THOOKU MADURAI API TEST v2.0')
print('══════════════════════════════════\n')

# ─── Admin Login ───────────────────────────────────
print('1. ADMIN LOGIN')
r = requests.post(BASE + '/auth/admin-login', json={'email':'admin@thookumadurai.in','password':'admin@123'})
d = r.json()
check('Admin login status 200', r.status_code == 200, str(r.status_code))
check('Admin JWT issued', bool(d.get('data',{}).get('token')))
admin_token = d.get('data',{}).get('token','')
ADM_H = {'Authorization': f'Bearer {admin_token}', 'Content-Type': 'application/json'}

# ─── Dashboard ─────────────────────────────────────
print('\n2. DASHBOARD')
r = requests.get(BASE + '/admin/dashboard', headers=ADM_H)
d = r.json()
check('Dashboard 200', r.status_code == 200)
check('Dashboard has data', 'data' in d)

# ─── Create Restaurant ──────────────────────────────
print('\n3. CREATE RESTAURANT')
r = requests.post(BASE + '/admin/restaurants', headers=ADM_H, json={
    'name': 'Royal Biriyani Corner',
    'username': 'royal_biriyani_test',
    'password': 'biriyani123',
    'owner_name': 'Murugan K',
    'owner_phone': '9876543210',
    'cuisine': 'Biryani',
    'area': 'KK Nagar',
    'address': '10, Main Street, KK Nagar, Madurai'
})
d = r.json()
check('Create restaurant 201', r.status_code == 201, str(r.status_code))
check('Returns credentials', bool(d.get('data',{}).get('password')))
rest_id = d.get('data',{}).get('id','')
check('Has restaurant ID', bool(rest_id))

# ─── Restaurant Login ───────────────────────────────
print('\n4. RESTAURANT LOGIN')
r = requests.post(BASE + '/auth/restaurant-login', json={'username':'royal_biriyani_test','password':'biriyani123'})
d = r.json()
check('Restaurant login 200', r.status_code == 200, str(r.status_code))
check('Restaurant JWT has restaurant_id', bool(d.get('data',{}).get('restaurant_id')))
rest_token = d.get('data',{}).get('token','')
REST_H = {'Authorization': f'Bearer {rest_token}', 'Content-Type': 'application/json'}

# ─── Create Rider ───────────────────────────────────
print('\n5. CREATE RIDER')
r = requests.post(BASE + '/admin/riders', headers=ADM_H, json={
    'name': 'Ravi Kumar',
    'username': 'ravi_rider_test',
    'password': 'rider456',
    'phone': '9876543211',
    'vehicle_type': 'bike',
    'vehicle_number': 'TN58AB1234'
})
d = r.json()
check('Create rider 201', r.status_code == 201, str(r.status_code))
check('Rider returns credentials', bool(d.get('data',{}).get('password')))
rider_id = d.get('data',{}).get('id','')

# ─── Rider Login ────────────────────────────────────
print('\n6. RIDER LOGIN')
r = requests.post(BASE + '/auth/rider-login', json={'username':'ravi_rider_test','password':'rider456'})
d = r.json()
check('Rider login 200', r.status_code == 200, str(r.status_code))
check('Rider JWT has rider_id', bool(d.get('data',{}).get('rider_id')))
rider_token = d.get('data',{}).get('token','')
RIDER_H = {'Authorization': f'Bearer {rider_token}', 'Content-Type': 'application/json'}

# ─── Open Restaurant ────────────────────────────────
print('\n7. OPEN RESTAURANT (admin toggles status)')
r = requests.patch(BASE + f'/admin/restaurants/{rest_id}/status', headers=ADM_H)
check('Toggle status 200', r.status_code == 200, r.json().get('data',{}))

# ─── Public Restaurants List ───────────────────────
print('\n8. PUBLIC RESTAURANTS (customer page)')
r = requests.get(BASE + '/restaurants')
d = r.json()
check('Public list 200', r.status_code == 200)
rests = d.get('data',{}).get('restaurants',[])
check('Restaurant appears in list', any(x.get('name')=='Royal Biriyani Corner' for x in rests), f'{len(rests)} restaurants')
check('Password NOT in public response', not any('password_hash' in x for x in rests))

# ─── Add Menu Item ──────────────────────────────────
print('\n9. MENU MANAGEMENT')
# Add category via restaurant auth
r = requests.post(BASE + f'/restaurants/{rest_id}/menu/category', headers=REST_H,
                  json={'name':'Biryani','emoji':'🍛'})
check('Add category 201', r.status_code == 201, str(r.status_code))
cat_id = r.json().get('data',{}).get('category_id','')

r = requests.post(BASE + f'/restaurants/{rest_id}/menu/item', headers=REST_H, json={
    'name':'Chicken Biryani','description':'Dum biryani','price':180,
    'category_id':cat_id,'is_veg':False,'is_available':True
})
check('Add menu item 201', r.status_code == 201, str(r.status_code))
item_id = r.json().get('data',{}).get('item_id','')

# ─── Get Menu ───────────────────────────────────────
r = requests.get(BASE + f'/restaurants/{rest_id}/menu')
d = r.json()
check('Get menu 200', r.status_code == 200)
menu = d.get('data',{}).get('menu',[])
check('Menu has items', len(menu) > 0)

# ─── Place Order ────────────────────────────────────
print('\n10. CUSTOMER ORDER')
r = requests.post(BASE + '/orders', json={
    'restaurant_id': rest_id,
    'items': [{'item_id':item_id,'name':'Chicken Biryani','price':180,'qty':2}],
    'delivery_address': {'street':'12, Main Road','area':'Anna Nagar','city':'Madurai','pincode':'625020'},
    'payment_method': 'gpay',
    'customer_phone': '9999999999'
})
d = r.json()
check('Place order 201', r.status_code == 201, str(r.status_code))
order_id = d.get('data',{}).get('order_id','')
check('Order ID starts with TM-', order_id.startswith('TM-'), order_id)
total = d.get('data',{}).get('total',0)
check('Total = 180*2 + 30 + 20 = 410', total == 410, f'Got {total}')

# ─── Track Order ────────────────────────────────────
print('\n11. ORDER TRACKING')
r = requests.get(BASE + f'/orders/{order_id}')
d = r.json()
check('Get order 200', r.status_code == 200)
check('Status is pending', d.get('data',{}).get('status') == 'pending')

# ─── Cleanup ────────────────────────────────────────
print('\n12. CLEANUP')
r = requests.delete(BASE + f'/admin/restaurants/{rest_id}', headers=ADM_H)
check('Delete restaurant 200', r.status_code == 200)
r = requests.delete(BASE + f'/admin/riders/{rider_id}', headers=ADM_H)
check('Delete rider 200', r.status_code == 200)

# ─── Summary ────────────────────────────────────────
print(f'\n══════════════════════════════════')
print(f'   RESULTS: {ok} passed, {fail} failed')
print(f'══════════════════════════════════\n')
