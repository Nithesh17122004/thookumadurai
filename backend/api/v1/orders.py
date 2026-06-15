# -*- coding: utf-8 -*-
"""
Orders API module for Thooku Madurai.
Handles the full order lifecycle:
  - Customer places order
  - Restaurant accepts -> auto-assign nearest available rider
  - Rider accepts/rejects -> sequential rotation through riders
  - Rider picks up -> delivers
  - Auto-refund if no rider assigned within 30 min
"""

import os
import random
import time
import logging
import math
import json

import jwt
from flask import Blueprint, current_app, jsonify, request

from services.platform_settings import get_platform_settings

orders_bp = Blueprint("orders", __name__)
logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get("JWT_SECRET", "thooku-madurai-secret-key-2026")
NO_RIDER_REFUND_TIMEOUT = 1800  # 30 min in seconds


def get_db():
    return current_app.extensions.get("mongo_db")


def _to_str_id(doc: dict) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _generate_order_id() -> str:
    return f"TM-{random.randint(100000, 999999)}"


def _decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None


def _get_token_payload():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return _decode_token(auth_header.split(" ", 1)[1].strip())


def _require_role(*roles):
    payload = _get_token_payload()
    if payload is None:
        return None, (jsonify({"success": False, "message": "Authorization token required"}), 401)
    if payload.get("role") not in roles:
        return None, (jsonify({"success": False, "message": f"Access requires role: {', '.join(roles)}"}), 403)
    return payload, None


def _haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _delivery_fee_slab(distance_km: float) -> int:
    """Return delivery fee based on distance slab."""
    if distance_km <= 2:
        return 30
    elif distance_km <= 4:
        return 40
    elif distance_km <= 6:
        return 50
    elif distance_km <= 8:
        return 60
    else:
        return 70


# ── Rider Assignment with Rotation ───────────────────────────────────────────

MAX_CONCURRENT_ORDERS = 3
MAX_ASSIGN_RADIUS_KM = 5.0


def _rider_active_count(db, rider_id):
    """Count rider's active (not delivered/cancelled) orders."""
    return db.orders.count_documents({
        "rider_id": rider_id,
        "status": {"$nin": ["delivered", "cancelled", "refunded"]}
    })


def _find_next_available_rider(db, restaurant_lat, restaurant_lng, exclude_ids=None):
    """Find the nearest available rider, excluding provided IDs."""
    exclude_ids = exclude_ids or []
    query = {"is_online": True, "is_available": True}
    if exclude_ids:
        query["_id"] = {"$nin": exclude_ids}

    available = list(db.delivery_partners.find(query))
    if not available:
        return None

    def dist(r):
        loc = r.get("current_location", {})
        return _haversine(
            restaurant_lat, restaurant_lng,
            float(loc.get("lat", 0)), float(loc.get("lng", 0))
        )

    # Filter by max radius and max orders
    filtered = [
        r for r in available
        if dist(r) <= MAX_ASSIGN_RADIUS_KM
        and _rider_active_count(db, str(r["_id"])) < MAX_CONCURRENT_ORDERS
    ]

    filtered.sort(key=dist)
    return filtered[0] if filtered else None


def _assign_rider(db, order_id: str, restaurant_lat: float, restaurant_lng: float, exclude_ids=None):
    """Assign nearest available rider to order. Returns rider or None."""
    rider = _find_next_available_rider(db, restaurant_lat, restaurant_lng, exclude_ids)
    if rider is None:
        return None

    rider_id = str(rider["_id"])

    db.orders.update_one(
        {"_id": order_id},
        {
            "$set": {
                "rider_id": rider_id,
                "rider_name": rider.get("name", ""),
                "rider_phone": rider.get("phone", ""),
                "status": "preparing",
                "rider_assigned_at": int(time.time()),
                "rejected_rider_ids": [],
            }
        },
    )
    db.delivery_partners.update_one({"_id": rider_id}, {"$set": {"is_available": False}})

    return rider


# ── Get available riders count ───────────────────────────────────────────────

@orders_bp.route("/available-riders-count", methods=["GET"])
def available_riders_count():
    db = get_db()
    if db is None:
        return jsonify({"success": False, "data": {"count": 0}}), 200
    count = db.delivery_partners.count_documents({"is_online": True, "is_available": True})
    return jsonify({"success": True, "data": {"count": count}}), 200


# ── Place order ──────────────────────────────────────────────────────────────

@orders_bp.route("", methods=["POST"])
def place_order():
    payload = _get_token_payload()
    if payload is None:
        return jsonify({"success": False, "message": "Authorization token required"}), 401
    if payload.get("role") != "customer":
        return jsonify({"success": False, "message": "Customer login required to place orders"}), 403

    data = request.get_json(silent=True) or {}

    if not data.get("customer_phone"):
        data["customer_phone"] = payload.get("phone", "")

    required = ["restaurant_id", "items", "delivery_address", "payment_method", "customer_phone"]
    for field in required:
        if not data.get(field):
            return jsonify({"success": False, "message": f"'{field}' is required"}), 400

    if not isinstance(data["items"], list) or len(data["items"]) == 0:
        return jsonify({"success": False, "message": "Order must have at least one item"}), 400

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    restaurant = db.restaurants.find_one({"_id": data["restaurant_id"]})
    if restaurant is None:
        return jsonify({"success": False, "message": "Restaurant not found"}), 404

    if not restaurant.get("is_open", False):
        return jsonify({"success": False, "message": "Restaurant is currently closed"}), 400

    # Get restaurant location
    rest_lat = restaurant.get("lat")
    rest_lng = restaurant.get("lng")
    if not rest_lat or not rest_lng:
        return jsonify({"success": False, "message": "Restaurant location is not set. Cannot calculate delivery distance."}), 400

    # Get customer location from delivery_address or delivery_location
    da = data.get("delivery_address", {})
    cust_lat = None
    cust_lng = None
    if isinstance(da, dict):
        cust_lat = da.get("lat")
        cust_lng = da.get("lng")
    if not cust_lat or not cust_lng:
        dl = data.get("delivery_location", {})
        cust_lat = dl.get("lat")
        cust_lng = dl.get("lng")
    if not cust_lat or not cust_lng:
        return jsonify({"success": False, "message": "Customer delivery location coordinates are required"}), 400

    rest_lat = float(rest_lat)
    rest_lng = float(rest_lng)
    cust_lat = float(cust_lat)
    cust_lng = float(cust_lng)

    # Calculate distance from restaurant → customer
    distance_km = round(_haversine(rest_lat, rest_lng, cust_lat, cust_lng), 2)

    # Determine delivery fee by slab
    delivery_fee = _delivery_fee_slab(distance_km)
    platform_fee = 20

    items = []
    item_total = 0.0
    for item in data["items"]:
        qty = int(item.get("qty") or item.get("quantity") or 1)
        price = float(item.get("price", 0))
        item_total += price * qty
        items.append({
            "item_id": str(item.get("item_id", "")),
            "name": str(item.get("name", "")),
            "price": price,
            "qty": qty,
        })

    total = item_total + delivery_fee + platform_fee

    order_id = _generate_order_id()
    for _ in range(5):
        if db.orders.find_one({"_id": order_id}) is None:
            break
        order_id = _generate_order_id()

    delivery_address = data["delivery_address"]
    if isinstance(delivery_address, dict) and not delivery_address.get("city"):
        delivery_address["city"] = "Madurai"

    now = int(time.time())
    order_doc = {
        "_id": order_id,
        "restaurant_id": data["restaurant_id"],
        "restaurant_name": restaurant.get("name", ""),
        "customer_phone": str(data["customer_phone"]),
        "items": items,
        "item_total": item_total,
        "delivery_fee": delivery_fee,
        "platform_fee": platform_fee,
        "total": total,
        "distance_km": distance_km,
        "payment_method": str(data["payment_method"]),
        "payment_status": "pending",
        "delivery_address": delivery_address,
        "rider_id": None,
        "rider_name": None,
        "rider_phone": None,
        "status": "pending",
        "created_at": now,
        "accepted_at": None,
        "picked_at": None,
        "delivered_at": None,
        "rider_assigned_at": None,
        "rejected_rider_ids": [],
        "no_rider_refund_processed": False,
        "no_rider_notified_at": None,
    }
    db.orders.insert_one(order_doc)

    # Emit new order event via Socket.IO for rider apps
    try:
        from app import socketio
        socketio.emit("new_order", {
            "order_id": order_id,
            "restaurant_name": restaurant.get("name", ""),
            "item_total": item_total,
            "total": total,
        }, room="riders")
    except Exception:
        pass

    return jsonify({
        "success": True,
        "message": "Order placed successfully",
        "data": {
            "order_id": order_id,
            "total": total,
            "item_total": item_total,
            "delivery_fee": delivery_fee,
            "delivery_fee_slab": f"{distance_km} km",
            "platform_fee": platform_fee,
            "distance_km": distance_km,
            "status": "pending",
            "restaurant_name": restaurant.get("name", ""),
        },
    }), 201


# ── Get order ────────────────────────────────────────────────────────────────

@orders_bp.route("/<order_id>/stream", methods=["GET"])
def stream_order(order_id):
    from flask import Response
    import json

    def generate():
        db = get_db()
        for _ in range(120):
            if db is None:
                yield f"data: {json.dumps({'error': 'db_unavailable'})}\n\n"
                break
            order = db.orders.find_one({"_id": order_id})
            if order is None:
                yield "data: " + json.dumps({'error': 'not_found'}) + "\n\n"
                break
            payload = {
                'status': order.get('status'),
                'rider_name': order.get('rider_name'),
                'payment_status': order.get('payment_status'),
                'no_rider_refund_processed': order.get('no_rider_refund_processed', False),
            }
            yield "data: " + json.dumps(payload) + "\n\n"
            if order.get("status") in ("delivered", "cancelled"):
                break
            time.sleep(5)

    return Response(generate(), mimetype="text/event-stream")


# ── Customer: my orders ──────────────────────────────────────────────────────

@orders_bp.route("/my-orders", methods=["GET"])
def my_orders():
    phone = request.args.get("phone", "").strip()
    if not phone:
        return jsonify({"success": False, "message": "Phone number is required"}), 400

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    docs = list(db.orders.find({"customer_phone": phone}).sort("created_at", -1).limit(50))
    for d in docs:
        _to_str_id(d)

    return jsonify({"success": True, "data": docs}), 200


# ── Get order status ─────────────────────────────────────────────────────────

@orders_bp.route("/<order_id>", methods=["GET"])
def get_order(order_id):
    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    order = db.orders.find_one({"_id": order_id})
    if order is None:
        return jsonify({"success": False, "message": "Order not found"}), 404

    _to_str_id(order)
    return jsonify({"success": True, "data": order}), 200


# ── Restaurant: accept order ─────────────────────────────────────────────────

@orders_bp.route("/<order_id>/accept", methods=["PATCH"])
def accept_order(order_id):
    payload, err = _require_role("restaurant")
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    order = db.orders.find_one({"_id": order_id})
    if order is None:
        return jsonify({"success": False, "message": "Order not found"}), 404

    restaurant_id_from_token = payload.get("restaurant_id", "")
    if order.get("restaurant_id") != restaurant_id_from_token:
        return jsonify({"success": False, "message": "Access denied: wrong restaurant"}), 403

    if order.get("status") != "pending":
        return jsonify({"success": False, "message": f"Order status is '{order.get('status')}', cannot accept"}), 400

    db.orders.update_one(
        {"_id": order_id},
        {"$set": {"status": "accepted", "accepted_at": int(time.time())}},
    )

    restaurant = db.restaurants.find_one({"_id": order["restaurant_id"]})
    restaurant_lat = float((restaurant or {}).get("lat", 0))
    restaurant_lng = float((restaurant or {}).get("lng", 0))

    available_riders = list(db.delivery_partners.find({"is_online": True, "is_available": True}))

    if available_riders:
        try:
            from app import socketio
            socketio.emit("new_order", {
                "order_id": order_id,
                "restaurant_name": order.get("restaurant_name", ""),
                "restaurant_lat": restaurant_lat,
                "restaurant_lng": restaurant_lng,
                "delivery_address": order.get("delivery_address", {}),
                "items": order.get("items", []),
                "total": order.get("total", 0),
            }, room="riders")
        except Exception:
            pass

    return jsonify({"success": True, "data": {
        "order_id": order_id,
        "status": "accepted",
        "riders_available": len(available_riders),
        "message": "Order accepted. Notifying available riders."
    }}), 200


# ── Rider: pickup ────────────────────────────────────────────────────────────

@orders_bp.route("/<order_id>/pickup", methods=["PATCH"])
def pickup_order(order_id):
    payload, err = _require_role("rider")
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    rider_id = payload.get("rider_id", "")
    order = db.orders.find_one({"_id": order_id})
    if order is None:
        return jsonify({"success": False, "message": "Order not found"}), 404

    if order.get("rider_id") != rider_id:
        return jsonify({"success": False, "message": "This order is not assigned to you"}), 403

    if order.get("status") not in ("preparing", "ready_for_pickup", "accepted"):
        return jsonify({"success": False, "message": f"Cannot pick up order with status '{order.get('status')}'"}), 400

    db.orders.update_one(
        {"_id": order_id},
        {"$set": {"status": "out_for_delivery", "picked_at": int(time.time())}},
    )

    # Notify customer via Socket.IO
    try:
        from app import socketio
        order_data = db.orders.find_one({"_id": order_id})
        socketio.emit("order_status_update", {
            "order_id": order_id,
            "status": "out_for_delivery",
            "message": "Your rider has picked up the order!",
        }, room=f"order_{order_id}")
    except Exception:
        pass

    return jsonify({"success": True, "message": "Order picked up", "data": {"status": "out_for_delivery"}}), 200


# ── Rider: deliver ───────────────────────────────────────────────────────────

@orders_bp.route("/<order_id>/deliver", methods=["PATCH"])
def deliver_order(order_id):
    payload, err = _require_role("rider")
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    rider_id = payload.get("rider_id", "")
    order = db.orders.find_one({"_id": order_id})
    if order is None:
        return jsonify({"success": False, "message": "Order not found"}), 404

    if order.get("rider_id") != rider_id:
        return jsonify({"success": False, "message": "This order is not assigned to you"}), 403

    if order.get("status") != "out_for_delivery":
        return jsonify({"success": False, "message": f"Cannot deliver order with status '{order.get('status')}'"}), 400

    now = int(time.time())
    db.orders.update_one(
        {"_id": order_id},
        {
            "$set": {
                "status": "delivered",
                "delivered_at": now,
                "payment_status": "completed",
            }
        },
    )

    rider_earnings = float(order.get("delivery_fee", get_platform_settings(db)["delivery_base_fee"]))
    db.delivery_partners.update_one(
        {"_id": rider_id},
        {
            "$set": {"is_available": True},
            "$inc": {"total_deliveries": 1, "earnings_today": rider_earnings},
        },
    )

    db.restaurants.update_one(
        {"_id": order.get("restaurant_id", "")},
        {"$inc": {"total_orders": 1}},
    )

    # Notify customer
    try:
        from app import socketio
        socketio.emit("order_status_update", {
            "order_id": order_id,
            "status": "delivered",
            "message": "Your order has been delivered! Enjoy!",
        }, room=f"order_{order_id}")
    except Exception:
        pass

    return jsonify({
        "success": True, "message": "Order delivered successfully", "data": {"status": "delivered"}
    }), 200


# ── Rider: reject delivery (rotate to next rider) ────────────────────────────

@orders_bp.route("/<order_id>/reject-delivery", methods=["PATCH"])
def reject_delivery(order_id):
    payload, err = _require_role("rider")
    if err:
        return err

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    rider_id = payload.get("rider_id", "")
    order = db.orders.find_one({"_id": order_id})
    if order is None:
        return jsonify({"success": False, "message": "Order not found"}), 404

    if order.get("rider_id") != rider_id:
        return jsonify({"success": False, "message": "This order is not assigned to you"}), 403

    # Free the rejecting rider
    db.delivery_partners.update_one({"_id": rider_id}, {"$set": {"is_available": True}})

    # Track rejected riders
    rejected_ids = order.get("rejected_rider_ids", []) or []
    if rider_id not in rejected_ids:
        rejected_ids.append(rider_id)

    # Clear current rider from order
    db.orders.update_one(
        {"_id": order_id},
        {
            "$set": {
                "rider_id": None,
                "rider_name": None,
                "rider_phone": None,
                "status": "accepted",
                "rejected_rider_ids": rejected_ids,
            }
        },
    )

    # Try to find next available rider (excluding all rejected ones)
    restaurant = db.restaurants.find_one({"_id": order.get("restaurant_id", "")})
    restaurant_lat = float((restaurant or {}).get("lat", 0))
    restaurant_lng = float((restaurant or {}).get("lng", 0))

    next_rider = _find_next_available_rider(db, restaurant_lat, restaurant_lng, exclude_ids=rejected_ids)

    response_data = {"order_id": order_id, "rejected_by": rider_id, "rejected_count": len(rejected_ids)}

    if next_rider:
        next_rider_id = str(next_rider["_id"])

        db.orders.update_one(
            {"_id": order_id},
            {
                "$set": {
                    "rider_id": next_rider_id,
                    "rider_name": next_rider.get("name", ""),
                    "rider_phone": next_rider.get("phone", ""),
                    "status": "preparing",
                    "rider_assigned_at": int(time.time()),
                }
            },
        )
        db.delivery_partners.update_one({"_id": next_rider_id}, {"$set": {"is_available": False}})

        response_data["new_rider"] = {
            "rider_id": next_rider_id,
            "rider_name": next_rider.get("name", ""),
        }
        response_data["status"] = "preparing"
        response_data["message"] = f"Re-assigned to next rider ({len(rejected_ids)} rejected so far)"

        # Notify next rider
        try:
            from app import socketio
            socketio.emit("delivery_assigned", {
                "order_id": order_id,
                "restaurant_name": order.get("restaurant_name", ""),
                "delivery_address": order.get("delivery_address", {}),
                "items": order.get("items", []),
                "total": order.get("total", 0),
            }, room=f"rider_{next_rider_id}")
        except Exception:
            pass
    else:
        response_data["message"] = "No more riders available. Order will be auto-refunded if no rider takes it within 30 min."
        response_data["status"] = "accepted"
        response_data["no_riders_left"] = True

    return jsonify({"success": True, "data": response_data}), 200


# ── Auto-refund check (called by scheduler) ──────────────────────────────────

def process_auto_refunds():
    """
    Called periodically by APScheduler.
    Finds orders that:
    - Have no rider assigned AND created more than 30 min ago
    - OR all riders rejected AND no rider assigned for 30 min
    Processes full refund to customer.
    """
    db = get_db()
    if db is None:
        return

    cutoff = int(time.time()) - NO_RIDER_REFUND_TIMEOUT

    # Find orders stuck in pending/accepted without rider for >30 min
    stuck_orders = list(db.orders.find({
        "status": {"$in": ["pending", "accepted"]},
        "created_at": {"$lt": cutoff},
        "no_rider_refund_processed": {"$ne": True},
        "payment_status": {"$in": ["paid", "pending"]},
    }))

    for order in stuck_orders:
        order_id = order["_id"]
        has_rider = bool(order.get("rider_id"))

        if has_rider:
            continue

        logger.info("Auto-refunding order %s — no rider assigned for >30 min", order_id)

        # Process refund
        payment_status = order.get("payment_status", "pending")
        amount = float(order.get("total", 0))

        if payment_status in ("paid", "completed"):
            # Initiate refund via Instamojo
            payment_id = order.get("instamojo_payment_id", "")
            try:
                from api.v1.payments import _use_mock_mode
                is_mock = _use_mock_mode() or (payment_id or "").startswith("pay_mock")
                if not is_mock and payment_id:
                    import requests as _req
                    resp = _req.post(
                        "https://www.instamojo.com/api/1.1/refunds/",
                        headers={
                            "X-Api-Key": os.environ.get("INSTAMOJO_API_KEY", ""),
                            "X-Auth-Token": os.environ.get("INSTAMOJO_AUTH_TOKEN", ""),
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                        data={
                            "payment_id": payment_id,
                            "type": "QFL",
                            "body": "Auto-refund: No rider assigned within 30 minutes",
                        },
                        timeout=15,
                    )
                    refund_data = resp.json()
                    refund_id = refund_data.get("refund", {}).get("id", f"auto_ref_{order_id}")
                else:
                    refund_id = f"auto_refund_mock_{order_id}"

                db.orders.update_one(
                    {"_id": order_id},
                    {
                        "$set": {
                            "status": "cancelled",
                            "payment_status": "refunded",
                            "no_rider_refund_processed": True,
                            "no_rider_refund_at": int(time.time()),
                            "refund_id": refund_id,
                            "cancellation_reason": "Auto-refund: No rider assigned within 30 minutes",
                        }
                    },
                )
                logger.info("Refund processed for order %s (refund: %s)", order_id, refund_id)
            except Exception as e:
                logger.error("Refund failed for order %s: %s", order_id, e)
                # Still mark as processed to avoid repeated attempts
                db.orders.update_one(
                    {"_id": order_id},
                    {
                        "$set": {
                            "status": "cancelled",
                            "payment_status": "refunded",
                            "no_rider_refund_processed": True,
                            "no_rider_refund_at": int(time.time()),
                            "cancellation_reason": "Auto-refund: No rider (refund api failed, manual needed)",
                        }
                    },
                )
        else:
            # Payment not yet made — just cancel
            db.orders.update_one(
                {"_id": order_id},
                {
                    "$set": {
                        "status": "cancelled",
                        "no_rider_refund_processed": True,
                        "no_rider_refund_at": int(time.time()),
                        "cancellation_reason": "Cancelled: No rider assigned within 30 minutes",
                    }
                },
            )

        # Notify customer via Socket.IO
        try:
            from app import socketio
            socketio.emit("order_refunded", {
                "order_id": order_id,
                "message": "No rider was available for your order. A full refund has been processed.",
                "amount": amount,
            }, room=f"order_{order_id}")
        except Exception:
            pass

    # Re-notify available riders for pending/accepted orders that still have no rider
    # (only for recent orders, <30 min, to try getting a rider)
    recent_no_rider = list(db.orders.find({
        "status": {"$in": ["pending", "accepted"]},
        "rider_id": None,
        "no_rider_refund_processed": {"$ne": True},
        "created_at": {"$gt": cutoff},
    }))

    available_riders = list(db.delivery_partners.find({"is_online": True, "is_available": True}))

    for order in recent_no_rider[:5]:  # limit to avoid spam
        if available_riders:
            restaurant = db.restaurants.find_one({"_id": order.get("restaurant_id", "")})
            rest_lat = float((restaurant or {}).get("lat", 0))
            rest_lng = float((restaurant or {}).get("lng", 0))

            rejected = order.get("rejected_rider_ids", []) or []
            next_rider = _find_next_available_rider(db, rest_lat, rest_lng, exclude_ids=rejected)

            if next_rider:
                nid = str(next_rider["_id"])
                db.orders.update_one(
                    {"_id": order["_id"]},
                    {
                        "$set": {
                            "rider_id": nid,
                            "rider_name": next_rider.get("name", ""),
                            "rider_phone": next_rider.get("phone", ""),
                            "status": "preparing",
                            "rider_assigned_at": int(time.time()),
                        }
                    },
                )
                db.delivery_partners.update_one({"_id": nid}, {"$set": {"is_available": False}})
                try:
                    from app import socketio
                    socketio.emit("delivery_assigned", {
                        "order_id": order["_id"],
                        "restaurant_name": order.get("restaurant_name", ""),
                        "delivery_address": order.get("delivery_address", {}),
                        "items": order.get("items", []),
                        "total": order.get("total", 0),
                    }, room=f"rider_{nid}")
                except Exception:
                    pass
                logger.info("Re-assigned order %s to rider %s via scheduler retry", order["_id"], nid)


# ── Customer: cancel order (before rider assigned) ───────────────────────────

@orders_bp.route("/<order_id>/cancel", methods=["PATCH"])
def cancel_order(order_id):
    payload = _get_token_payload()
    if payload is None:
        return jsonify({"success": False, "message": "Authentication required"}), 401

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    order = db.orders.find_one({"_id": order_id})
    if order is None:
        return jsonify({"success": False, "message": "Order not found"}), 404

    if order.get("customer_phone") != payload.get("phone"):
        return jsonify({"success": False, "message": "Access denied"}), 403

    if order.get("status") not in ("pending", "accepted"):
        return jsonify({"success": False, "message": f"Cannot cancel order with status '{order.get('status')}'"}), 400

    db.orders.update_one(
        {"_id": order_id},
        {
            "$set": {
                "status": "cancelled",
                "cancellation_reason": "Cancelled by customer",
                "cancelled_at": int(time.time()),
            }
        },
    )

    # Refund if payment was made
    if order.get("payment_status") in ("paid", "completed"):
        db.orders.update_one({"_id": order_id}, {"$set": {"payment_status": "refunded"}})

    return jsonify({"success": True, "message": "Order cancelled"}), 200


# ── Request rider reassignment (customer asks "find another rider") ──────────

@orders_bp.route("/<order_id>/request-rider", methods=["POST"])
def request_rider_reassignment(order_id):
    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    order = db.orders.find_one({"_id": order_id})
    if order is None:
        return jsonify({"success": False, "message": "Order not found"}), 404

    if order.get("rider_id") is not None:
        return jsonify({"success": False, "message": "Order already has a rider"}), 400

    restaurant = db.restaurants.find_one({"_id": order.get("restaurant_id", "")})
    restaurant_lat = float((restaurant or {}).get("lat", 0))
    restaurant_lng = float((restaurant or {}).get("lng", 0))

    rejected = order.get("rejected_rider_ids", []) or []
    rider = _find_next_available_rider(db, restaurant_lat, restaurant_lng, exclude_ids=rejected)

    if rider is None:
        return jsonify({"success": False, "message": "No riders available at the moment"}), 404

    rider_id = str(rider["_id"])
    db.orders.update_one(
        {"_id": order_id},
        {
            "$set": {
                "rider_id": rider_id,
                "rider_name": rider.get("name", ""),
                "rider_phone": rider.get("phone", ""),
                "status": "preparing",
                "rider_assigned_at": int(time.time()),
            }
        },
    )
    db.delivery_partners.update_one({"_id": rider_id}, {"$set": {"is_available": False}})

    return jsonify({
        "success": True,
        "data": {
            "rider_name": rider.get("name", ""),
            "rider_phone": rider.get("phone", ""),
        }
    }), 200


# ── Rate order ────────────────────────────────────────────────────────────────

@orders_bp.route("/<order_id>/rate", methods=["POST"])
def rate_order(order_id):
    # Resolve caller phone from token
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    phone = ""
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            phone = payload.get("phone", "")
        except Exception:
            pass
    if not phone:
        return jsonify({"success": False, "message": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    rating = data.get("rating")
    review = data.get("review", "").strip()

    if not rating or not isinstance(rating, (int, float)) or rating < 1 or rating > 5:
        return jsonify({"success": False, "message": "Rating must be between 1 and 5"}), 400

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    order = db.orders.find_one({"_id": order_id})
    if not order:
        return jsonify({"success": False, "message": "Order not found"}), 404

    if order.get("customer_phone") != phone:
        return jsonify({"success": False, "message": "You can only rate your own orders"}), 403

    db.orders.update_one(
        {"_id": order_id},
        {"$set": {"rating": float(rating), "review": review, "rated_at": int(time.time())}},
    )

    # Update restaurant average rating
    rest_id = order.get("restaurant_id")
    if rest_id:
        all_ratings = list(db.orders.find(
            {"restaurant_id": rest_id, "rating": {"$exists": True}},
            {"rating": 1}
        ))
        if all_ratings:
            avg = sum(r["rating"] for r in all_ratings) / len(all_ratings)
            db.restaurants.update_one({"_id": rest_id}, {"$set": {"rating": round(avg, 1)}})

    return jsonify({"success": True, "message": "Rating submitted"}), 200
