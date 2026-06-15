# -*- coding: utf-8 -*-
"""
Admin (SuperAdmin) API module for Thooku Madurai.
All endpoints require JWT role == 'superadmin'.
In development mode a bearer token of any value gives fallback superadmin access.
"""

import os
import time
import uuid
import logging

import bcrypt
import jwt
from bson import ObjectId
from flask import Blueprint, current_app, jsonify, request

from services.platform_settings import get_platform_settings

# ---------------------------------------------------------------------------
# Blueprint & constants
# ---------------------------------------------------------------------------
admin_bp = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get(
    "JWT_SECRET", "thooku-madurai-secret-2026-change-in-production"
)
IS_PRODUCTION = os.environ.get("FLASK_ENV", "development") == "production"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_db():
    return current_app.extensions.get("mongo_db")


def _to_str_id(doc: dict) -> dict:
    """Convert ObjectId _id to string in place."""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _require_superadmin():
    """
    Returns (payload_dict, None) on success, or (None, error_response) on failure.
    In dev mode any valid-looking bearer token is accepted as superadmin fallback.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, (jsonify({"success": False, "message": "Authorization token required"}), 401)

    token = auth_header.split(" ", 1)[1].strip()

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("role") != "superadmin":
            if IS_PRODUCTION:
                return None, (jsonify({"success": False, "message": "Superadmin access required"}), 403)
            # Dev fallback
            logger.warning("DEV: non-superadmin token accepted as superadmin fallback")
            payload["role"] = "superadmin"
        return payload, None
    except jwt.ExpiredSignatureError:
        if not IS_PRODUCTION:
            logger.warning("DEV: expired token accepted as superadmin fallback")
            return {"role": "superadmin", "name": "dev_admin"}, None
        return None, (jsonify({"success": False, "message": "Token expired"}), 401)
    except jwt.InvalidTokenError:
        if not IS_PRODUCTION:
            logger.warning("DEV: invalid token accepted as superadmin fallback")
            return {"role": "superadmin", "name": "dev_admin"}, None
        return None, (jsonify({"success": False, "message": "Invalid token"}), 401)


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@admin_bp.route("/dashboard", methods=["GET"])
def dashboard():
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    total_restaurants = db.restaurants.count_documents({})
    total_riders = db.delivery_partners.count_documents({})
    total_customers = db.customers.count_documents({})
    total_orders = db.orders.count_documents({})
    delivered_orders = db.orders.count_documents({"status": "delivered"})
    pending_orders = db.orders.count_documents({"status": "pending"})
    active_riders = db.delivery_partners.count_documents({"is_online": True})

    # Revenue: sum of totals for delivered orders
    pipeline = [
        {"$match": {"status": "delivered"}},
        {"$group": {"_id": None, "total_revenue": {"$sum": "$total"}}},
    ]
    revenue_result = list(db.orders.aggregate(pipeline))
    total_revenue = revenue_result[0]["total_revenue"] if revenue_result else 0

    return jsonify(
        {
            "success": True,
            "data": {
                "total_restaurants": total_restaurants,
                "total_riders": total_riders,
                "total_customers": total_customers,
                "total_orders": total_orders,
                "delivered_orders": delivered_orders,
                "pending_orders": pending_orders,
                "active_riders": active_riders,
                "total_revenue": total_revenue,
            },
        }
    ), 200


# ---------------------------------------------------------------------------
# Restaurants
# ---------------------------------------------------------------------------

@admin_bp.route("/restaurants", methods=["GET"])
def list_restaurants():
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    docs = list(db.restaurants.find({}))
    for d in docs:
        d.pop("password_hash", None)
        _to_str_id(d)

    return jsonify({"success": True, "data": docs}), 200


@admin_bp.route("/restaurants", methods=["POST"])
def create_restaurant():
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    data = request.get_json(silent=True) or {}
    required = ["name", "username", "password"]
    for field in required:
        if not data.get(field):
            return jsonify({"success": False, "message": f"'{field}' is required"}), 400

    # Check username uniqueness
    if db.restaurants.find_one({"username": data["username"]}):
        return jsonify({"success": False, "message": "Username already taken"}), 409

    plain_password = data["password"]
    restaurant_doc = {
        "_id": str(uuid.uuid4()),
        "name": data["name"],
        "username": data["username"],
        "password_hash": _hash_password(plain_password),
        "owner_name": data.get("owner_name", ""),
        "owner_phone": data.get("owner_phone", ""),
        "cuisine": data.get("cuisine", ""),
        "area": data.get("area", ""),
        "address": data.get("address", ""),
        "lat": float(data.get("lat", 0)),
        "lng": float(data.get("lng", 0)),
        "is_open": False,
        "rating": 0.0,
        "total_orders": 0,
        "fssai": data.get("fssai", ""),
        "upi_id": data.get("upi_id", ""),
        "menu": [],
        "created_at": int(time.time()),
    }
    db.restaurants.insert_one(restaurant_doc)

    return jsonify(
        {
            "success": True,
            "data": {
                "id": restaurant_doc["_id"],
                "username": restaurant_doc["username"],
                "password": plain_password,  # show once so admin can share
            },
        }
    ), 201


@admin_bp.route("/restaurants/<restaurant_id>", methods=["PUT"])
def update_restaurant(restaurant_id):
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    data = request.get_json(silent=True) or {}
    allowed = [
        "name", "owner_name", "owner_phone", "cuisine", "area",
        "address", "lat", "lng", "fssai", "upi_id", "is_open",
    ]
    update_fields = {k: data[k] for k in allowed if k in data}

    # Accept fssai_no as alias for fssai
    if "fssai_no" in data and "fssai" not in update_fields:
        update_fields["fssai"] = data["fssai_no"]

    # Optional password update
    new_password = data.get("password", "").strip()
    if new_password:
        import bcrypt as _bcrypt
        pw_hash = _bcrypt.hashpw(new_password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")
        update_fields["password_hash"] = pw_hash

    if not update_fields:
        return jsonify({"success": False, "message": "No valid fields to update"}), 400

    result = db.restaurants.update_one(
        {"_id": restaurant_id}, {"$set": update_fields}
    )
    if result.matched_count == 0:
        return jsonify({"success": False, "message": "Restaurant not found"}), 404

    return jsonify({"success": True, "message": "Restaurant updated"}), 200


@admin_bp.route("/restaurants/<restaurant_id>", methods=["DELETE"])
def delete_restaurant(restaurant_id):
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    result = db.restaurants.delete_one({"_id": restaurant_id})
    if result.deleted_count == 0:
        return jsonify({"success": False, "message": "Restaurant not found"}), 404

    # Delete all orders belonging to this restaurant
    db.orders.delete_many({"restaurant_id": restaurant_id})

    return jsonify({"success": True, "message": "Restaurant and its orders deleted"}), 200


@admin_bp.route("/restaurants/<restaurant_id>/status", methods=["PATCH"])
def toggle_restaurant_status(restaurant_id):
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    restaurant = db.restaurants.find_one({"_id": restaurant_id})
    if restaurant is None:
        return jsonify({"success": False, "message": "Restaurant not found"}), 404

    new_status = not restaurant.get("is_open", False)
    db.restaurants.update_one({"_id": restaurant_id}, {"$set": {"is_open": new_status}})

    return jsonify(
        {"success": True, "data": {"is_open": new_status}}
    ), 200


# ---------------------------------------------------------------------------
# Riders
# ---------------------------------------------------------------------------

@admin_bp.route("/riders", methods=["GET"])
def list_riders():
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    docs = list(db.delivery_partners.find({}))
    for d in docs:
        d.pop("password_hash", None)
        _to_str_id(d)

    return jsonify({"success": True, "data": docs}), 200


@admin_bp.route("/riders", methods=["POST"])
def create_rider():
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    data = request.get_json(silent=True) or {}
    required = ["name", "username", "password", "phone"]
    for field in required:
        if not data.get(field):
            return jsonify({"success": False, "message": f"'{field}' is required"}), 400

    if db.delivery_partners.find_one({"username": data["username"]}):
        return jsonify({"success": False, "message": "Username already taken"}), 409

    plain_password = data["password"]
    rider_doc = {
        "_id": str(uuid.uuid4()),
        "name": data["name"],
        "username": data["username"],
        "password_hash": _hash_password(plain_password),
        "phone": data["phone"],
        "vehicle_type": data.get("vehicle_type", "bike"),
        "vehicle_number": data.get("vehicle_number", ""),
        "is_online": False,
        "is_available": True,
        "approval_status": "approved",
        "current_location": {"lat": 0.0, "lng": 0.0},
        "rating": 5.0,
        "total_deliveries": 0,
        "earnings_today": 0,
        "created_at": int(time.time()),
    }
    db.delivery_partners.insert_one(rider_doc)

    return jsonify(
        {
            "success": True,
            "data": {
                "id": rider_doc["_id"],
                "username": rider_doc["username"],
                "password": plain_password,  # show once
            },
        }
    ), 201


@admin_bp.route("/riders/<rider_id>", methods=["PUT"])
def update_rider(rider_id):
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    data = request.get_json(silent=True) or {}
    allowed = ["name", "phone", "vehicle_type", "vehicle_number", "approval_status", "is_online", "username"]
    update_fields = {k: data[k] for k in allowed if k in data}
    if data.get("password"):
        from werkzeug.security import generate_password_hash
        update_fields["password_hash"] = generate_password_hash(data["password"])

    if not update_fields:
        return jsonify({"success": False, "message": "No valid fields to update"}), 400

    result = db.delivery_partners.update_one({"_id": rider_id}, {"$set": update_fields})
    if result.matched_count == 0:
        return jsonify({"success": False, "message": "Rider not found"}), 404

    return jsonify({"success": True, "message": "Rider updated"}), 200


@admin_bp.route("/riders/<rider_id>", methods=["DELETE"])
def delete_rider(rider_id):
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    result = db.delivery_partners.delete_one({"_id": rider_id})
    if result.deleted_count == 0:
        return jsonify({"success": False, "message": "Rider not found"}), 404

    return jsonify({"success": True, "message": "Rider deleted"}), 200


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

@admin_bp.route("/customers", methods=["GET"])
def list_customers():
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    docs = list(db.customers.find({}))
    for d in docs:
        _to_str_id(d)

    return jsonify({"success": True, "data": docs}), 200


@admin_bp.route("/customers/<customer_id>", methods=["DELETE"])
def delete_customer(customer_id):
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    result = db.customers.delete_one({"_id": customer_id})
    if result.deleted_count == 0:
        return jsonify({"success": False, "message": "Customer not found"}), 404

    return jsonify({"success": True, "message": "Customer deleted"}), 200


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

@admin_bp.route("/orders", methods=["GET"])
def list_orders():
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    status_filter = request.args.get("status", None)

    query = {}
    if status_filter:
        query["status"] = status_filter

    total = db.orders.count_documents(query)
    docs = list(
        db.orders.find(query)
        .sort("created_at", -1)
        .skip((page - 1) * per_page)
        .limit(per_page)
    )
    for d in docs:
        _to_str_id(d)

    return jsonify(
        {
            "success": True,
            "data": docs,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page,
            },
        }
    ), 200


@admin_bp.route("/orders/<order_id>/assign", methods=["PATCH"])
def assign_rider_to_order(order_id):
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    data = request.get_json(silent=True) or {}
    rider_id = data.get("rider_id", "")
    if not rider_id:
        return jsonify({"success": False, "message": "rider_id is required"}), 400

    order = db.orders.find_one({"_id": order_id})
    if order is None:
        return jsonify({"success": False, "message": "Order not found"}), 404

    rider = db.delivery_partners.find_one({"_id": rider_id})
    if rider is None:
        return jsonify({"success": False, "message": "Rider not found"}), 404

    db.orders.update_one(
        {"_id": order_id},
        {
            "$set": {
                "rider_id": rider_id,
                "rider_name": rider.get("name", ""),
                "rider_phone": rider.get("phone", ""),
                "status": "preparing",
            }
        },
    )
    db.delivery_partners.update_one({"_id": rider_id}, {"$set": {"is_available": False}})

    return jsonify({"success": True, "message": "Rider assigned successfully"}), 200


# ---------------------------------------------------------------------------
# Coupons
# ---------------------------------------------------------------------------

@admin_bp.route("/coupons", methods=["GET"])
def list_coupons():
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    docs = list(db.coupons.find({}))
    for d in docs:
        _to_str_id(d)

    return jsonify({"success": True, "data": docs}), 200


@admin_bp.route("/coupons", methods=["POST"])
def create_coupon():
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    data = request.get_json(silent=True) or {}
    required = ["code", "discount_type", "discount_value"]
    for field in required:
        if data.get(field) is None:
            return jsonify({"success": False, "message": f"'{field}' is required"}), 400

    code = str(data["code"]).upper().strip()
    if db.coupons.find_one({"code": code}):
        return jsonify({"success": False, "message": "Coupon code already exists"}), 409

    coupon_doc = {
        "_id": str(uuid.uuid4()),
        "code": code,
        "discount_type": data["discount_type"],   # 'percent' | 'flat'
        "discount_value": float(data["discount_value"]),
        "min_order": float(data.get("min_order", 0)),
        "max_uses": int(data.get("max_uses", 0)),  # 0 = unlimited
        "uses": 0,
        "is_active": True,
        "expires_at": data.get("expires_at", None),
        "created_at": int(time.time()),
    }
    db.coupons.insert_one(coupon_doc)

    return jsonify({"success": True, "data": coupon_doc}), 201


@admin_bp.route("/coupons/<coupon_id>", methods=["DELETE"])
def delete_coupon(coupon_id):
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    result = db.coupons.delete_one({"_id": coupon_id})
    if result.deleted_count == 0:
        return jsonify({"success": False, "message": "Coupon not found"}), 404

    return jsonify({"success": True, "message": "Coupon deleted"}), 200


# ---------------------------------------------------------------------------
# DB Reset (wipe all except admins)
# ---------------------------------------------------------------------------

@admin_bp.route("/db/reset", methods=["POST"])
def db_reset():
    payload, err = _require_superadmin()
    if err:
        return err

    if IS_PRODUCTION:
        return jsonify({"success": False, "message": "DB reset not allowed in production"}), 403

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    collections_to_wipe = [
        "restaurants",
        "delivery_partners",
        "customers",
        "orders",
        "coupons",
    ]
    report = {}
    for col in collections_to_wipe:
        result = db[col].delete_many({})
        report[col] = result.deleted_count

    return jsonify(
        {
            "success": True,
            "message": "All data wiped (admins preserved)",
            "deleted": report,
        }
    ), 200


# ---------------------------------------------------------------------------
# Platform Settings (GET + POST stored in MongoDB "settings" collection)
# ---------------------------------------------------------------------------

@admin_bp.route("/settings", methods=["GET"])
def get_settings():
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    settings = get_platform_settings(db)
    return jsonify({"success": True, "data": settings}), 200


@admin_bp.route("/settings", methods=["POST", "PUT", "PATCH"])
def save_settings():
    payload, err = _require_superadmin()
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    data = request.get_json(silent=True) or {}
    update = {"_id": "platform", "updated_at": int(time.time())}

    if "platform_fee" in data:
        try:
            update["platform_fee"] = max(0.0, float(data["platform_fee"]))
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "Invalid platform_fee"}), 400
    if "delivery_base_fee" in data:
        try:
            update["delivery_base_fee"] = max(0.0, float(data["delivery_base_fee"]))
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "Invalid delivery_base_fee"}), 400
    if "support_phone" in data:
        update["support_phone"] = str(data["support_phone"]).strip()

    db.settings.update_one(
        {"_id": "platform"},
        {"$set": update},
        upsert=True,
    )

    saved = get_platform_settings(db)
    return jsonify({
        "success": True,
        "message": "Settings saved successfully",
        "data": saved,
    }), 200


# alias so frontend calling /admin/reset-database still works
@admin_bp.route("/reset-database", methods=["POST"])
def reset_database_alias():
    return db_reset()

