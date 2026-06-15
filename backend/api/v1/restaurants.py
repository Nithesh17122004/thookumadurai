# -*- coding: utf-8 -*-
"""
Restaurants API module for Thooku Madurai.
Public endpoints (GET) require no auth.
Management endpoints require JWT role == 'restaurant' and matching restaurant_id.
"""

import os
import time
import uuid
import logging

import jwt
from flask import Blueprint, current_app, jsonify, request

# ---------------------------------------------------------------------------
# Blueprint & constants
# ---------------------------------------------------------------------------
restaurants_bp = Blueprint("restaurants", __name__)
logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get("JWT_SECRET", "thooku-madurai-secret-key-2026")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_db():
    return current_app.extensions.get("mongo_db")


def _to_str_id(doc: dict) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _require_restaurant_auth(restaurant_id: str = None):
    """
    Validates JWT for role='restaurant'.
    If restaurant_id is provided, also checks the token's restaurant_id matches.
    Returns (payload, None) on success or (None, error_response) on failure.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, (jsonify({"success": False, "message": "Authorization token required"}), 401)

    token = auth_header.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None, (jsonify({"success": False, "message": "Token expired"}), 401)
    except jwt.InvalidTokenError:
        return None, (jsonify({"success": False, "message": "Invalid token"}), 401)

    role = payload.get("role")
    # Allow superadmin to manage any restaurant's menu
    if role == "superadmin":
        return payload, None

    if role != "restaurant":
        return None, (jsonify({"success": False, "message": "Restaurant access required"}), 403)

    if restaurant_id and payload.get("restaurant_id") != restaurant_id:
        return None, (jsonify({"success": False, "message": "Access denied: wrong restaurant"}), 403)

    return payload, None


def _public_restaurant(doc: dict) -> dict:
    """Strip sensitive fields and build menu summary for public listing."""
    doc.pop("password_hash", None)
    doc.pop("username", None)
    doc.pop("upi_id", None)

    # Build menu summary: list of {category_name, emoji, item_count}
    raw_menu = doc.get("menu", [])
    menu_summary = []
    for cat in raw_menu:
        menu_summary.append(
            {
                "category_id": cat.get("category_id", ""),
                "category_name": cat.get("category_name", ""),
                "emoji": cat.get("emoji", ""),
                "item_count": len(cat.get("items", [])),
            }
        )
    doc["menu_summary"] = menu_summary
    doc.pop("menu", None)

    return doc


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@restaurants_bp.route("", methods=["GET"])
def list_restaurants():
    """Return all open restaurants with public info only."""
    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    docs = list(db.restaurants.find({"is_open": True}))
    result = []
    for doc in docs:
        _to_str_id(doc)
        result.append(_public_restaurant(doc))

    return jsonify({"success": True, "data": result}), 200


@restaurants_bp.route("/<restaurant_id>", methods=["GET"])
def get_restaurant(restaurant_id):
    """Return full restaurant details (minus credentials) for a single restaurant."""
    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    doc = db.restaurants.find_one({"_id": restaurant_id})
    if doc is None:
        return jsonify({"success": False, "message": "Restaurant not found"}), 404

    _to_str_id(doc)
    doc.pop("password_hash", None)
    doc.pop("username", None)
    doc.pop("upi_id", None)

    return jsonify({"success": True, "data": doc}), 200


@restaurants_bp.route("/<restaurant_id>/menu", methods=["GET"])
def get_menu(restaurant_id):
    """Return full menu for a restaurant."""
    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    doc = db.restaurants.find_one({"_id": restaurant_id}, {"menu": 1, "name": 1})
    if doc is None:
        return jsonify({"success": False, "message": "Restaurant not found"}), 404

    return jsonify(
        {
            "success": True,
            "data": {
                "restaurant_id": restaurant_id,
                "restaurant_name": doc.get("name", ""),
                "menu": doc.get("menu", []),
            },
        }
    ), 200


# ---------------------------------------------------------------------------
# Restaurant-authenticated: status toggle
# ---------------------------------------------------------------------------

@restaurants_bp.route("/<restaurant_id>/status", methods=["PATCH"])
def toggle_status(restaurant_id):
    payload, err = _require_restaurant_auth(restaurant_id)
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    doc = db.restaurants.find_one({"_id": restaurant_id})
    if doc is None:
        return jsonify({"success": False, "message": "Restaurant not found"}), 404

    body = request.get_json(silent=True) or {}
    if "is_open" in body:
        new_status = bool(body["is_open"])
    else:
        new_status = not doc.get("is_open", False)
    db.restaurants.update_one({"_id": restaurant_id}, {"$set": {"is_open": new_status}})

    return jsonify({"success": True, "data": {"is_open": new_status}}), 200


# ---------------------------------------------------------------------------
# Menu: categories
# ---------------------------------------------------------------------------

@restaurants_bp.route("/<restaurant_id>/menu/category", methods=["POST"])
def add_category(restaurant_id):
    """Add a new menu category. Body: {name, emoji}"""
    payload, err = _require_restaurant_auth(restaurant_id)
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"success": False, "message": "Category name is required"}), 400

    category = {
        "category_id": str(uuid.uuid4()),
        "category_name": name,
        "emoji": data.get("emoji", "🍽️"),
        "items": [],
    }

    result = db.restaurants.update_one(
        {"_id": restaurant_id}, {"$push": {"menu": category}}
    )
    if result.matched_count == 0:
        return jsonify({"success": False, "message": "Restaurant not found"}), 404

    return jsonify({"success": True, "data": category}), 201


@restaurants_bp.route("/<restaurant_id>/menu/category/<category_id>", methods=["PUT"])
def update_category(restaurant_id, category_id):
    """Update category name and emoji."""
    payload, err = _require_restaurant_auth(restaurant_id)
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    data = request.get_json(silent=True) or {}
    update_fields = {}
    if "name" in data:
        update_fields["menu.$[cat].category_name"] = str(data["name"]).strip()
    if "emoji" in data:
        update_fields["menu.$[cat].emoji"] = str(data["emoji"]).strip()

    if not update_fields:
        return jsonify({"success": False, "message": "No valid fields to update"}), 400

    result = db.restaurants.update_one(
        {"_id": restaurant_id},
        {"$set": update_fields},
        array_filters=[{"cat.category_id": category_id}],
    )
    if result.matched_count == 0:
        return jsonify({"success": False, "message": "Restaurant not found"}), 404
    if result.modified_count == 0:
        return jsonify({"success": False, "message": "Category not found or no changes"}), 404

    return jsonify({"success": True, "message": "Category updated"}), 200


@restaurants_bp.route("/<restaurant_id>/menu/category/<category_id>", methods=["DELETE"])
def delete_category(restaurant_id, category_id):
    """Delete a menu category and all its items."""
    payload, err = _require_restaurant_auth(restaurant_id)
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    result = db.restaurants.update_one(
        {"_id": restaurant_id},
        {"$pull": {"menu": {"category_id": category_id}}},
    )
    if result.matched_count == 0:
        return jsonify({"success": False, "message": "Restaurant not found"}), 404
    if result.modified_count == 0:
        return jsonify({"success": False, "message": "Category not found"}), 404

    return jsonify({"success": True, "message": "Category deleted"}), 200


# ---------------------------------------------------------------------------
# Menu: items
# ---------------------------------------------------------------------------

@restaurants_bp.route("/<restaurant_id>/menu/item", methods=["POST"])
def add_item(restaurant_id):
    """
    Add a menu item to an existing category.
    Body: {name, description, price, category_id, is_veg, is_available}
    """
    payload, err = _require_restaurant_auth(restaurant_id)
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    data = request.get_json(silent=True) or {}
    required = ["name", "price", "category_id"]
    for field in required:
        if data.get(field) is None:
            return jsonify({"success": False, "message": f"'{field}' is required"}), 400

    item_id = str(uuid.uuid4())
    item = {
        "item_id": item_id,
        "id": item_id,  # alias for frontend compatibility
        "name": str(data["name"]).strip(),
        "description": str(data.get("description", data.get("desc", ""))).strip(),
        "price": float(data["price"]),
        "type": str(data.get("type", "veg")),
        "emoji": str(data.get("emoji", "🍽️")),
        "is_veg": data.get("type", "veg") == "veg",
        "is_available": bool(data.get("is_available", True)),
    }

    category_id = str(data["category_id"]).strip()
    category_name = str(data.get("category_name", data.get("name", "Menu"))).strip()

    # Try to push into existing category first
    result = db.restaurants.update_one(
        {"_id": restaurant_id, "menu.category_id": category_id},
        {"$push": {"menu.$.items": item}},
    )

    if result.matched_count == 0:
        # Category doesn't exist → auto-create it and add item
        new_category = {
            "category_id": category_id,
            "category_name": category_name,
            "emoji": str(data.get("category_emoji", "🍽️")),
            "items": [item],
        }
        result2 = db.restaurants.update_one(
            {"_id": restaurant_id},
            {"$push": {"menu": new_category}},
        )
        if result2.matched_count == 0:
            return jsonify({"success": False, "message": "Restaurant not found"}), 404

    return jsonify({"success": True, "message": "Item added", "data": {"id": item_id, "item_id": item_id, **item}}), 201


@restaurants_bp.route("/<restaurant_id>/menu/item/<item_id>", methods=["PUT"])
def update_item(restaurant_id, item_id):
    """Update a menu item. Finds item across all categories."""
    payload, err = _require_restaurant_auth(restaurant_id)
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    data = request.get_json(silent=True) or {}
    allowed = ["name", "description", "price", "is_veg", "is_available", "type", "emoji"]
    update_fields = {}
    for k in allowed:
        if k in data:
            update_fields[f"menu.$[cat].items.$[item].{k}"] = data[k]
    if "desc" in data and "description" not in data:
        update_fields["menu.$[cat].items.$[item].description"] = data["desc"]
    if "type" in data:
        update_fields["menu.$[cat].items.$[item].is_veg"] = data["type"] == "veg"

    if not update_fields:
        return jsonify({"success": False, "message": "No valid fields to update"}), 400

    result = db.restaurants.update_one(
        {"_id": restaurant_id},
        {"$set": update_fields},
        array_filters=[{"cat.category_id": {"$exists": True}}, {"item.item_id": item_id}],
    )
    if result.matched_count == 0:
        return jsonify({"success": False, "message": "Restaurant not found"}), 404
    if result.modified_count == 0:
        return jsonify({"success": False, "message": "Item not found or no changes"}), 404

    return jsonify({"success": True, "message": "Item updated"}), 200


@restaurants_bp.route("/<restaurant_id>/menu/item/<item_id>", methods=["DELETE"])
def delete_item(restaurant_id, item_id):
    """Delete a menu item from whichever category it belongs to."""
    payload, err = _require_restaurant_auth(restaurant_id)
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    result = db.restaurants.update_one(
        {"_id": restaurant_id, "menu.items.item_id": item_id},
        {"$pull": {"menu.$.items": {"item_id": item_id}}},
    )
    if result.matched_count == 0:
        return jsonify({"success": False, "message": "Item not found"}), 404

    return jsonify({"success": True, "message": "Item deleted"}), 200


@restaurants_bp.route("/<restaurant_id>/menu/item/<item_id>/toggle", methods=["PATCH"])
def toggle_item_availability(restaurant_id, item_id):
    """Toggle is_available for a menu item."""
    payload, err = _require_restaurant_auth(restaurant_id)
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    # Fetch current value
    doc = db.restaurants.find_one(
        {"_id": restaurant_id, "menu.items.item_id": item_id},
        {"menu.$": 1},
    )
    if doc is None:
        return jsonify({"success": False, "message": "Item not found"}), 404

    current = None
    for cat in doc.get("menu", []):
        for it in cat.get("items", []):
            if it.get("item_id") == item_id:
                current = it.get("is_available", True)
                break
        if current is not None:
            break

    new_val = not current if current is not None else False

    db.restaurants.update_one(
        {"_id": restaurant_id},
        {"$set": {"menu.$[cat].items.$[item].is_available": new_val}},
        array_filters=[{"cat.category_id": {"$exists": True}}, {"item.item_id": item_id}],
    )

    return jsonify({"success": True, "data": {"is_available": new_val}}), 200


# ---------------------------------------------------------------------------
# Restaurant orders management
# ---------------------------------------------------------------------------

@restaurants_bp.route("/<restaurant_id>/orders", methods=["GET"])
def restaurant_orders(restaurant_id):
    """Get incoming orders for this restaurant."""
    payload, err = _require_restaurant_auth(restaurant_id)
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    status_filter = request.args.get("status", None)
    query = {"restaurant_id": restaurant_id}
    if status_filter:
        query["status"] = status_filter

    docs = list(db.orders.find(query).sort("created_at", -1).limit(100))
    for d in docs:
        _to_str_id(d)

    return jsonify({"success": True, "data": docs}), 200


@restaurants_bp.route("/<restaurant_id>/orders/<order_id>/accept", methods=["PATCH"])
def accept_order(restaurant_id, order_id):
    """Restaurant accepts an order."""
    payload, err = _require_restaurant_auth(restaurant_id)
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    order = db.orders.find_one({"_id": order_id, "restaurant_id": restaurant_id})
    if order is None:
        return jsonify({"success": False, "message": "Order not found"}), 404

    if order.get("status") != "pending":
        return jsonify({"success": False, "message": f"Cannot accept order with status '{order.get('status')}'"}), 400

    db.orders.update_one(
        {"_id": order_id},
        {"$set": {"status": "preparing", "accepted_at": int(time.time())}},
    )

    # Auto-assign nearest online rider (Swiggy/Zomato style)
    restaurant = db.restaurants.find_one({"_id": restaurant_id})
    if restaurant and not order.get("rider_id"):
        from api.v1.orders import _assign_rider
        restaurant_lat = float(restaurant.get("lat", 9.9252))
        restaurant_lng = float(restaurant.get("lng", 78.1198))
        _assign_rider(db, order_id, restaurant_lat, restaurant_lng)

    return jsonify({"success": True, "message": "Order accepted and preparing"}), 200


@restaurants_bp.route("/<restaurant_id>/orders/<order_id>/reject", methods=["PATCH"])
def reject_order(restaurant_id, order_id):
    """Restaurant rejects an order."""
    payload, err = _require_restaurant_auth(restaurant_id)
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    order = db.orders.find_one({"_id": order_id, "restaurant_id": restaurant_id})
    if order is None:
        return jsonify({"success": False, "message": "Order not found"}), 404

    if order.get("status") not in ("pending",):
        return jsonify({"success": False, "message": "Order cannot be rejected at this stage"}), 400

    data = request.get_json(silent=True) or {}
    db.orders.update_one(
        {"_id": order_id},
        {
            "$set": {
                "status": "rejected",
                "reject_reason": data.get("reason", ""),
                "updated_at": int(time.time()),
            }
        },
    )

    return jsonify({"success": True, "message": "Order rejected"}), 200


@restaurants_bp.route("/<restaurant_id>/orders/<order_id>/ready", methods=["PATCH"])
def mark_ready(restaurant_id, order_id):
    """Mark order as ready for pickup."""
    payload, err = _require_restaurant_auth(restaurant_id)
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    order = db.orders.find_one({"_id": order_id, "restaurant_id": restaurant_id})
    if order is None:
        return jsonify({"success": False, "message": "Order not found"}), 404

    if order.get("status") not in ("accepted", "preparing"):
        return jsonify({"success": False, "message": "Order is not in a preparable state"}), 400

    db.orders.update_one(
        {"_id": order_id},
        {"$set": {"status": "ready_for_pickup", "ready_at": int(time.time())}},
    )

    return jsonify({"success": True, "message": "Order marked as ready for pickup"}), 200
