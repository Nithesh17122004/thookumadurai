# ============================================================
# THOOKU MADURAI — API: Riders
# /api/v1/riders
# ============================================================
import os
import time
import math

import jwt
from flask import Blueprint, current_app, jsonify, request

riders_bp = Blueprint("riders", __name__)

JWT_SECRET = os.environ.get("JWT_SECRET", "thooku-madurai-secret-key-2026")
MAX_CONCURRENT_ORDERS = 3
MAX_ASSIGN_RADIUS_KM = 5.0  # only show/assign orders within 5 km of rider


def get_db():
    return current_app.extensions.get("mongo_db")


def _haversine(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _rider_active_order_count(db, rider_id):
    """Count active orders for a rider (not yet delivered/cancelled)."""
    return db.orders.count_documents({
        "rider_id": rider_id,
        "status": {"$nin": ["delivered", "cancelled", "refunded"]}
    })


def _decode_token():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        return jwt.decode(auth.split(" ", 1)[1], JWT_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None


def require_auth(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        payload = _decode_token()
        if payload is None:
            return jsonify({"success": False, "message": "Unauthorized"}), 401
        request.rider_user = payload
        return f(*args, **kwargs)

    return decorated


def _rider_id(payload):
    return payload.get("rider_id") or payload.get("user_id")


@riders_bp.route("/status", methods=["PATCH"])
@require_auth
def update_rider_status():
    """Toggle rider online/offline."""
    data = request.get_json(silent=True) or {}
    is_online = bool(data.get("is_online", False))
    rider_id = _rider_id(request.rider_user)

    db = get_db()
    if db is not None and rider_id:
        update = {
            "is_online": is_online,
            "is_available": is_online,
            "updated_at": int(time.time()),
        }
        db.delivery_partners.update_one({"_id": rider_id}, {"$set": update})

    return jsonify(
        {
            "success": True,
            "message": f"You are now {'online' if is_online else 'offline'}",
            "data": {"is_online": is_online},
        }
    ), 200


def _update_location(data):
    lat = data.get("lat")
    lng = data.get("lng")
    if lat is None or lng is None:
        return jsonify({"success": False, "message": "lat/lng required"}), 400

    rider_id = _rider_id(request.rider_user)
    db = get_db()
    if db is not None and rider_id:
        db.delivery_partners.update_one(
            {"_id": rider_id},
            {
                "$set": {
                    "current_location": {"lat": float(lat), "lng": float(lng)},
                    "updated_at": int(time.time()),
                }
            },
        )
    return jsonify({"success": True}), 200


@riders_bp.route("/location", methods=["POST", "PATCH"])
@require_auth
def update_rider_location():
    """Update rider GPS location."""
    return _update_location(request.get_json(silent=True) or {})


@riders_bp.route("/orders", methods=["GET"])
@require_auth
def get_rider_orders():
    """Orders assigned to this rider, plus nearby available orders for claiming."""
    rider_id = _rider_id(request.rider_user)
    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    # Orders already assigned to this rider (active)
    assigned = list(db.orders.find(
        {"rider_id": rider_id, "status": {"$nin": ["delivered", "cancelled", "refunded"]}}
    ).sort("created_at", -1).limit(20))

    # Get rider's current location for proximity filtering
    rider = db.delivery_partners.find_one({"_id": rider_id}) or {}
    rider_loc = rider.get("current_location", {})
    rider_lat = float(rider_loc.get("lat", 0))
    rider_lng = float(rider_loc.get("lng", 0))

    # Available orders (accepted, no rider assigned)
    # Enrich with restaurant location and compute distance from rider
    available_raw = list(db.orders.find(
        {"status": "accepted", "rider_id": None}
    ).sort("created_at", -1).limit(10))

    available = []
    for o in available_raw:
        # Get restaurant location to compute distance
        rest = db.restaurants.find_one({"_id": o.get("restaurant_id")}, {"lat": 1, "lng": 1, "name": 1})
        rest_lat = float(rest["lat"]) if rest and rest.get("lat") else 0
        rest_lng = float(rest["lng"]) if rest and rest.get("lng") else 0
        dist_km = _haversine(rider_lat, rider_lng, rest_lat, rest_lng) if rider_lat and rider_lng else 0
        # Only include orders within max radius
        if dist_km <= MAX_ASSIGN_RADIUS_KM:
            o["distance_km"] = round(dist_km, 1)
            o["restaurant_lat"] = rest_lat
            o["restaurant_lng"] = rest_lng
            o["restaurant_name_display"] = rest["name"] if rest else ""
            available.append(o)

    # Sort available by distance (nearest first)
    available.sort(key=lambda o: o.get("distance_km", 999))

    docs = assigned + available
    for d in docs:
        if "_id" in d:
            d["_id"] = str(d["_id"])
    return jsonify({"success": True, "data": docs}), 200


@riders_bp.route("/delivery/accept/<order_id>", methods=["POST"])
@require_auth
def accept_delivery(order_id):
    rider_id = _rider_id(request.rider_user)
    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    rider = db.delivery_partners.find_one({"_id": rider_id}) or {}

    # Check max concurrent orders limit
    active_count = _rider_active_order_count(db, rider_id)
    if active_count >= MAX_CONCURRENT_ORDERS:
        return jsonify({
            "success": False,
            "message": f"You already have {active_count} active orders. Max {MAX_CONCURRENT_ORDERS} allowed."
        }), 400

    # Check if this rider was offered the order (sequential flow)
    order = db.orders.find_one({"_id": order_id})
    if order is None:
        return jsonify({"success": False, "message": "Order not found"}), 404

    offered_rider_id = order.get("offered_rider_id")
    if offered_rider_id and offered_rider_id != rider_id:
        return jsonify({"success": False, "message": "This order was offered to another rider"}), 403

    if order.get("rider_id") and order.get("rider_id") != rider_id:
        return jsonify({"success": False, "message": "Another rider already accepted this order"}), 409

    # Atomic claim: only succeeds if no rider assigned yet
    result = db.orders.find_one_and_update(
        {"_id": order_id, "rider_id": None, "status": "accepted"},
        {"$set": {
            "rider_id": rider_id,
            "rider_name": rider.get("name", ""),
            "rider_phone": rider.get("phone", request.rider_user.get("phone", "")),
            "status": "preparing",
            "rider_assigned_at": int(time.time()),
            "offered_rider_id": None,
            "no_riders_left": False,
        }}
    )
    if result is None:
        return jsonify({"success": False, "message": "Order already taken by another rider"}), 409

    # Set is_available=False only if at max capacity
    new_active_count = _rider_active_order_count(db, rider_id)
    if new_active_count >= MAX_CONCURRENT_ORDERS:
        db.delivery_partners.update_one({"_id": rider_id}, {"$set": {"is_available": False}})

    # Notify other riders that this order was taken
    try:
        from app import socketio
        socketio.emit("order_taken", {"order_id": order_id}, room="riders")
    except Exception:
        pass

    addr = result.get("delivery_address") or ""
    if isinstance(addr, dict):
        addr_str = ", ".join(filter(None, [addr.get("street"), addr.get("area"), addr.get("city")]))
    else:
        addr_str = str(addr)
    return jsonify(
        {
            "success": True,
            "message": "Delivery accepted",
            "data": {
                "order_id": order_id,
                "pickup_address": result.get("restaurant_name", "Restaurant"),
                "delivery_address": addr_str,
            },
        }
    ), 200


@riders_bp.route("/delivery/reject/<order_id>", methods=["POST"])
@require_auth
def reject_delivery(order_id):
    rider_id = _rider_id(request.rider_user)
    db = get_db()
    if db is not None:
        db.delivery_partners.update_one({"_id": rider_id}, {"$set": {"is_available": True}})
        order = db.orders.find_one({"_id": order_id})
        if order and (order.get("rider_id") == rider_id or order.get("offered_rider_id") == rider_id):
            rejected_ids = order.get("rejected_rider_ids", []) or []
            if rider_id not in rejected_ids:
                rejected_ids.append(rider_id)
            db.orders.update_one(
                {"_id": order_id},
                {
                    "$set": {
                        "rider_id": None,
                        "rider_name": None,
                        "rider_phone": None,
                        "status": "accepted",
                        "rejected_rider_ids": rejected_ids,
                        "offered_rider_id": None,
                    }
                },
            )
            from api.v1.orders import _offer_to_next_rider
            _offer_to_next_rider(db, order_id)
    return jsonify({"success": True, "message": "Delivery rejected."}), 200


@riders_bp.route("/delivery/<order_id>/pickup", methods=["POST"])
@require_auth
def confirm_pickup(order_id):
    db = get_db()
    if db is not None:
        db.orders.update_one(
            {"_id": order_id},
            {"$set": {"status": "out_for_delivery", "picked_at": int(time.time())}},
        )
    return jsonify({"success": True, "message": "Pickup confirmed!", "data": {"order_id": order_id}}), 200


@riders_bp.route("/delivery/<order_id>/deliver", methods=["POST"])
@require_auth
def confirm_delivery(order_id):
    rider_id = _rider_id(request.rider_user)
    db = get_db()
    if db is not None:
        order = db.orders.find_one({"_id": order_id}, {"delivery_fee": 1})
        actual_fee = int(order.get("delivery_fee", 70)) if order else 70
        db.orders.update_one(
            {"_id": order_id},
            {
                "$set": {
                    "status": "delivered",
                    "delivered_at": int(time.time()),
                    "payment_status": "completed",
                }
            },
        )
        db.delivery_partners.update_one(
            {"_id": rider_id},
            {"$set": {"is_available": True}, "$inc": {"total_deliveries": 1, "earnings_today": actual_fee}},
        )
    return jsonify(
        {"success": True, "message": "Delivery confirmed! Earnings credited.", "data": {"order_id": order_id, "earnings": actual_fee if 'actual_fee' in dir() else 70}}
    ), 200


@riders_bp.route("/earnings", methods=["GET"])
@require_auth
def get_earnings():
    period = request.args.get("period", "today")
    rider_id = _rider_id(request.rider_user)
    db = get_db()

    if db is not None and rider_id:
        rider = db.delivery_partners.find_one({"_id": rider_id}) or {}
        now = int(time.time())
        day_start = now - (now % 86400)
        week_start = day_start - 6 * 86400
        month_start = now - 30 * 86400

        # Get all delivered orders for this rider
        orders_cursor = db.orders.find(
            {"rider_id": rider_id, "status": "delivered"},
            {"delivery_fee": 1, "delivered_at": 1}
        )

        today_amt = 0.0
        today_del = 0
        week_amt = 0.0
        week_del = 0
        month_amt = 0.0
        month_del = 0

        for o in orders_cursor:
            fee = float(o.get("delivery_fee", 0))
            delivered_at = o.get("delivered_at", 0)
            if delivered_at >= day_start:
                today_amt += fee
                today_del += 1
            if delivered_at >= week_start:
                week_amt += fee
                week_del += 1
            if delivered_at >= month_start:
                month_amt += fee
                month_del += 1

        data = {
            "today": {"amount": round(today_amt), "deliveries": today_del},
            "week": {"amount": round(week_amt), "deliveries": week_del},
            "month": {"amount": round(month_amt), "deliveries": month_del},
        }
        return jsonify({"success": True, "data": data.get(period, data["today"])}), 200

    fallback = {
        "today": {"amount": 0, "deliveries": 0},
        "week": {"amount": 0, "deliveries": 0},
        "month": {"amount": 0, "deliveries": 0},
    }
    return jsonify({"success": True, "data": fallback.get(period, fallback["today"])}), 200


@riders_bp.route("/profile", methods=["GET"])
@require_auth
def get_rider_profile():
    rider_id = _rider_id(request.rider_user)
    db = get_db()
    if db is not None:
        rider = db.delivery_partners.find_one({"_id": rider_id})
        if rider:
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "name": rider.get("name", ""),
                        "phone": rider.get("phone", ""),
                        "rating": rider.get("rating", 4.8),
                        "total_deliveries": rider.get("total_deliveries", 0),
                        "vehicle": rider.get("vehicle_type", "Bike"),
                        "vehicle_no": rider.get("vehicle_no", ""),
                        "acceptance_rate": rider.get("acceptance_rate", 90),
                        "on_time_rate": rider.get("on_time_rate", 95),
                    },
                }
            ), 200

    return jsonify(
        {
            "success": True,
            "data": {
                "name": request.rider_user.get("name", "Rider"),
                "phone": request.rider_user.get("phone", ""),
                "rating": 4.8,
                "total_deliveries": 0,
                "vehicle": "Bike",
                "vehicle_no": "",
                "acceptance_rate": 90,
                "on_time_rate": 95,
            },
        }
    ), 200


@riders_bp.route("/profile", methods=["PUT"])
@require_auth
def update_rider_profile():
    data = request.get_json(silent=True) or {}
    rider_id = _rider_id(request.rider_user)
    db = get_db()
    if db is not None and rider_id:
        allowed = ["name", "email", "vehicle_type", "vehicle_no", "phone"]
        update = {k: data[k] for k in allowed if k in data}
        if update:
            db.delivery_partners.update_one({"_id": rider_id}, {"$set": update})
    return jsonify({"success": True, "message": "Profile updated"}), 200
