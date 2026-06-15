// ============================================================
// THOOKU MADURAI — MongoDB Atlas Schema
// Run in MongoDB Atlas Shell or Compass
// ============================================================

// Create database
use("thooku_madurai");

// ===== CUSTOMERS =====
db.createCollection("customers");
db.customers.createIndex({ "phone": 1 }, { unique: true });
db.customers.createIndex({ "email": 1 }, { sparse: true });
db.customers.createIndex({ "created_at": -1 });

// Sample document
db.customers.insertOne({
  phone: "9876543210",
  name: "",
  email: null,
  profile_pic: null,
  loyalty_points: 0,
  referral_code: "TM9876",
  referred_by: null,
  total_orders: 0,
  total_spent: 0,
  is_active: true,
  created_at: new Date(),
  updated_at: new Date()
});

// ===== ADDRESSES =====
db.createCollection("addresses");
db.addresses.createIndex({ "customer_id": 1 });
db.addresses.createIndex({ "location": "2dsphere" }); // Geospatial

// ===== RESTAURANTS =====
db.createCollection("restaurants");
db.restaurants.createIndex({ "owner_phone": 1 }, { unique: true });
db.restaurants.createIndex({ "location": "2dsphere" });
db.restaurants.createIndex({ "status": 1, "is_open": 1 });
db.restaurants.createIndex({ "area_slug": 1 });

// ===== MENU CATEGORIES =====
db.createCollection("menu_categories");
db.menu_categories.createIndex({ "restaurant_id": 1, "sort_order": 1 });

// ===== MENU ITEMS =====
db.createCollection("menu_items");
db.menu_items.createIndex({ "restaurant_id": 1, "category_id": 1 });
db.menu_items.createIndex({ "name": "text", "description": "text" });
db.menu_items.createIndex({ "is_available": 1 });

// ===== MENU ADD-ONS =====
db.createCollection("menu_addons");
db.menu_addons.createIndex({ "item_id": 1 });

// ===== ORDERS =====
db.createCollection("orders");
db.orders.createIndex({ "customer_id": 1, "created_at": -1 });
db.orders.createIndex({ "restaurant_id": 1, "status": 1, "created_at": -1 });
db.orders.createIndex({ "rider_id": 1, "status": 1 });
db.orders.createIndex({ "status": 1, "created_at": -1 });
db.orders.createIndex({ "payment_status": 1 });
db.orders.createIndex({ "idempotency_key": 1 }, { unique: true, sparse: true });

// Sample order document
db.orders.insertOne({
  order_number: "TM-10001",
  customer_id: "cust_id_here",
  restaurant_id: "rest_id_here",
  rider_id: null,
  items: [
    { item_id: "item_1", name: "Chicken Biryani", price: 180, qty: 2, addons: [] }
  ],
  delivery_address: {
    street: "12, Gandhi Nagar",
    area: "Anna Nagar",
    city: "Madurai",
    pincode: "625020",
    lat: 9.9252,
    lng: 78.1198
  },
  amounts: {
    item_total: 360,
    delivery_fee: 30,
    platform_fee: 20,
    coupon_discount: 0,
    total: 410
  },
  payment_method: "gpay",
  payment_status: "paid",
  razorpay_payment_id: "pay_XXXXX",
  status: "preparing",
  coupon_code: null,
  customer_rating: null,
  rider_rating: null,
  cancellation_reason: null,
  idempotency_key: "idem_key_here",
  created_at: new Date(),
  updated_at: new Date()
});

// ===== ORDER ITEMS =====
db.createCollection("order_items"); // Denormalized in orders.items

// ===== PAYMENTS =====
db.createCollection("payments");
db.payments.createIndex({ "order_id": 1 }, { unique: true });
db.payments.createIndex({ "razorpay_payment_id": 1 }, { sparse: true });
db.payments.createIndex({ "status": 1, "created_at": -1 });

// ===== REFUNDS =====
db.createCollection("refunds");
db.refunds.createIndex({ "order_id": 1 });
db.refunds.createIndex({ "status": 1 });

// ===== DELIVERY PARTNERS =====
db.createCollection("delivery_partners");
db.delivery_partners.createIndex({ "phone": 1 }, { unique: true });
db.delivery_partners.createIndex({ "current_location": "2dsphere" });
db.delivery_partners.createIndex({ "is_online": 1, "current_orders": 1 });
db.delivery_partners.createIndex({ "approval_status": 1 });

// ===== RIDER DOCUMENTS =====
db.createCollection("rider_documents");
db.rider_documents.createIndex({ "rider_id": 1 });

// ===== RIDER ASSIGNMENTS =====
db.createCollection("rider_assignments");
db.rider_assignments.createIndex({ "order_id": 1 });
db.rider_assignments.createIndex({ "rider_id": 1, "status": 1 });
db.rider_assignments.createIndex({ "assigned_at": -1 });

// ===== REVIEWS =====
db.createCollection("reviews");
db.reviews.createIndex({ "restaurant_id": 1, "created_at": -1 });
db.reviews.createIndex({ "order_id": 1 }, { unique: true });
db.reviews.createIndex({ "customer_id": 1 });

// ===== COUPONS =====
db.createCollection("coupons");
db.coupons.createIndex({ "code": 1 }, { unique: true });
db.coupons.createIndex({ "is_active": 1, "valid_until": 1 });

// ===== REFERRALS =====
db.createCollection("referrals");
db.referrals.createIndex({ "referrer_id": 1 });
db.referrals.createIndex({ "referred_phone": 1 });

// ===== NOTIFICATIONS =====
db.createCollection("notifications");
db.notifications.createIndex({ "user_id": 1, "is_read": 1, "created_at": -1 });

// ===== SUPPORT TICKETS =====
db.createCollection("support_tickets");
db.support_tickets.createIndex({ "status": 1, "created_at": -1 });
db.support_tickets.createIndex({ "user_id": 1 });

// ===== ADMINS =====
db.createCollection("admins");
db.admins.createIndex({ "email": 1 }, { unique: true });

// ===== AUDIT LOGS =====
db.createCollection("audit_logs");
db.audit_logs.createIndex({ "created_at": -1 });
db.audit_logs.createIndex({ "user_id": 1 });
db.audit_logs.createIndex({ "action": 1 });

// ===== SETTINGS =====
db.createCollection("settings");
db.settings.insertOne({
  key: "platform_config",
  platform_fee: 20,
  base_delivery_fee: 30,
  per_km_rate: 8,
  max_delivery_radius_km: 15,
  maintenance_mode: false,
  updated_at: new Date()
});

// ===== CALL RECORDS =====
db.createCollection("call_records");
db.call_records.createIndex({ "caller_masked": 1 });
db.call_records.createIndex({ "agent_id": 1, "created_at": -1 });
db.call_records.createIndex({ "status": 1 });

print("✅ Thooku Madurai MongoDB schema created successfully!");
print("Collections: customers, restaurants, orders, payments, delivery_partners, reviews, coupons, and more.");
