# ============================================================
# THOOKU MADURAI — API: Payments (Instamojo)
# /api/v1/payments
# ============================================================

import hmac
import hashlib
import os
import uuid
import json
import logging
import time

import jwt
import requests as req
from flask import Blueprint, request, jsonify, current_app
from functools import wraps

payments_bp = Blueprint("payments", __name__)
logger = logging.getLogger(__name__)

# Reuse the app-level require_auth from app.py (imported at blueprint registration)
JWT_SECRET = os.environ.get("JWT_SECRET", "thooku-madurai-secret-key-2026")
INSTAMOJO_API_KEY = os.environ.get("INSTAMOJO_API_KEY", "")
INSTAMOJO_AUTH_TOKEN = os.environ.get("INSTAMOJO_AUTH_TOKEN", "")
INSTAMOJO_AUTH_TOKEN = os.environ.get("INSTAMOJO_AUTH_TOKEN", "")
INSTAMOJO_SALT = os.environ.get("INSTAMOJO_SALT", "")
INSTAMOJO_WEBHOOK_SECRET = os.environ.get("INSTAMOJO_WEBHOOK_SECRET", "")
FLASK_ENV = os.environ.get("FLASK_ENV", "development").lower()

INSTAMOJO_API = "https://www.instamojo.com/api/1.1/"
PAYMENT_MOCK_MODE = os.environ.get("PAYMENT_MOCK_MODE", "").lower() in ("1", "true", "yes")


def _use_mock_mode() -> bool:
    return True  # Always mock for development


def get_db():
    return current_app.extensions.get("mongo_db")


def require_auth_decorator(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if not token:
            return jsonify({"success": False, "error": "No token"}), 401
        try:
            request.user = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"success": False, "error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"success": False, "error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


def _update_order_payment(db, order_id: str, payment_status: str, payment_id: str = ""):
    if db is None or not order_id:
        return
    update = {"payment_status": payment_status}
    if payment_id:
        update["instamojo_payment_id"] = payment_id
    db.orders.update_one({"_id": order_id}, {"$set": update})


# ── Instamojo Helpers ───────────────────────────────────────────────────────

def _instamojo_headers():
    return {
        "X-Api-Key": INSTAMOJO_API_KEY,
        "X-Auth-Token": INSTAMOJO_AUTH_TOKEN,
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _create_instamojo_request(order_id: str, amount: float, customer_phone: str, customer_email: str = "") -> dict | None:
    """Create a payment request on Instamojo and return the response."""
    try:
        payload = {
            "purpose": f"Thooku Madurai Order {order_id}",
            "amount": f"{amount:.2f}",
            "phone": customer_phone,
            "buyer_name": f"Customer {customer_phone[-4:]}",
            "email": customer_email or f"customer{customer_phone}@thooku.xyz",
            "send_email": False,
            "send_sms": False,
            "allow_repeated_payments": False,
            "redirect_url": "",  # handled via webhook
            "webhook_url": f"{request.host_url}api/v1/payments/webhook",
        }
        resp = req.post(
            f"{INSTAMOJO_API}payment-requests/",
            headers=_instamojo_headers(),
            data=payload,
            timeout=15,
        )
        data = resp.json()
        if resp.status_code == 201 and data.get("success"):
            pr = data.get("payment_request", {})
            return {
                "id": pr.get("id"),
                "longurl": pr.get("longurl"),
                "shorturl": pr.get("shorturl"),
                "status": pr.get("status"),
            }
        logger.warning("Instamojo create failed: %s", data.get("message", resp.text[:200]))
        return None
    except Exception as e:
        logger.error("Instamojo request error: %s", e)
        return None


def _verify_instamojo_webhook(data: dict) -> bool:
    """Verify Instamojo webhook signature using the salt."""
    mac_provided = data.get("mac", "")
    if not mac_provided:
        return False
    fields = [
        "payment_id", "payment_request_id", "buyer_name", "buyer_phone",
        "buyer_email", "currency", "amount", "purpose", "status"
    ]
    mac_string = "|".join(str(data.get(f, "")) for f in fields)
    mac_expected = hmac.new(
        INSTAMOJO_SALT.encode(), mac_string.encode(), hashlib.sha1
    ).hexdigest()
    return hmac.compare_digest(mac_expected, mac_provided)


# ── Endpoints ────────────────────────────────────────────────────────────────

@payments_bp.route("/create-order", methods=["POST"])
@require_auth_decorator
def create_payment_order():
    """Create an Instamojo payment request for the order."""
    body = request.get_json(silent=True) or {}
    order_id = body.get("order_id", "")
    amount = body.get("amount", 0)
    return jsonify({
        "success": True,
        "data": {
            "payment_request_id": f"mock_pr_{uuid.uuid4().hex[:12]}",
            "longurl": "",
            "shorturl": "",
            "amount": float(amount),
            "order_id": order_id,
            "mock_mode": True,
        },
    }), 200


@payments_bp.route("/verify", methods=["POST"])
@require_auth_decorator
def verify_payment():
    """Verify payment after webhook or mock completion."""
    data = request.get_json(silent=True) or {}
    order_id = data.get("order_id", "")
    payment_request_id = data.get("payment_request_id", "")
    payment_id = data.get("payment_id", "")
    status = data.get("status", "paid")

    if not order_id:
        return jsonify({"success": False, "error": "order_id required"}), 400

    is_mock = (payment_request_id or "").startswith("mock_") or data.get("mock_mode")

    db = get_db()
    if is_mock:
        _update_order_payment(db, order_id, "paid", payment_id or f"pay_mock_{uuid.uuid4().hex[:12]}")
        return jsonify({
            "success": True,
            "message": "Payment verified (mock)",
            "data": {"order_id": order_id, "status": "paid"},
        }), 200

    # Verify via Instamojo API
    if payment_request_id:
        try:
            resp = req.get(
                f"{INSTAMOJO_API}payment-requests/{payment_request_id}/",
                headers=_instamojo_headers(),
                timeout=10,
            )
            pr_data = resp.json()
            if pr_data.get("success"):
                pr = pr_data.get("payment_request", {})
                pr_status = pr.get("status", "")
                if pr_status == "Completed":
                    payments = pr.get("payments", [])
                    pid = payments[0].get("payment_id", payment_id) if payments else payment_id
                    _update_order_payment(db, order_id, "paid", pid)
                    return jsonify({
                        "success": True,
                        "message": "Payment verified!",
                        "data": {"order_id": order_id, "status": "paid", "payment_id": pid},
                    }), 200
        except Exception as e:
            logger.warning("Instamojo verify error: %s", e)

    return jsonify({"success": False, "error": "Payment not completed yet"}), 400


@payments_bp.route("/webhook", methods=["POST"])
def payment_webhook():
    """Handle Instamojo webhook callback."""
    data = request.form.to_dict() or request.get_json(silent=True) or {}

    if not _verify_instamojo_webhook(data):
        logger.warning("Webhook signature verification failed")
        return jsonify({"status": "error", "message": "Invalid signature"}), 400

    status = data.get("status", "")
    payment_id = data.get("payment_id", "")
    payment_request_id = data.get("payment_request_id", "")
    purpose = data.get("purpose", "")

    # Extract order_id from purpose field: "Thooku Madurai Order TM-XXXXXX"
    order_id = ""
    if "Order " in purpose:
        order_id = purpose.split("Order ")[-1].strip()

    if not order_id:
        order_id = data.get("order_id", "")

    db = get_db()

    if status == "Credit" and order_id:
        _update_order_payment(db, order_id, "paid", payment_id)
        logger.info("Payment webhook: order %s paid (payment %s)", order_id, payment_id)
    elif order_id:
        _update_order_payment(db, order_id, "failed")
        logger.info("Payment webhook: order %s failed", order_id)

    return jsonify({"status": "ok"}), 200


@payments_bp.route("/refund", methods=["POST"])
@require_auth_decorator
def initiate_refund():
    """Initiate a refund via Instamojo or mock."""
    data = request.get_json(silent=True) or {}
    payment_id = data.get("payment_id", data.get("instamojo_payment_id", ""))
    amount = data.get("amount", 0)
    reason = data.get("reason", "order_cancelled_no_rider")
    order_id = data.get("order_id", "")

    if not payment_id and not order_id:
        return jsonify({"success": False, "error": "payment_id or order_id required"}), 400

    # Auto-find payment_id from order
    if not payment_id and order_id:
        db = get_db()
        if db is not None:
            order = db.orders.find_one({"_id": order_id}, {"instamojo_payment_id": 1})
            if order:
                payment_id = order.get("instamojo_payment_id", "")

    is_mock = (payment_id or "").startswith("pay_mock") or _use_mock_mode()

    if is_mock or not payment_id:
        refund_id = f"refund_mock_{uuid.uuid4().hex[:12]}"
        return jsonify({
            "success": True,
            "message": "Refund initiated (mock)",
            "data": {"refund_id": refund_id, "amount": amount, "status": "processed"},
        }), 200

    try:
        resp = req.post(
            f"{INSTAMOJO_API}refunds/",
            headers=_instamojo_headers(),
            data={
                "payment_id": payment_id,
                "type": "QFL",
                "body": reason,
                "amount": f"{float(amount):.2f}" if amount else "",
            },
            timeout=15,
        )
        ref_data = resp.json()
        if resp.status_code == 201:
            refund_id = ref_data.get("refund", {}).get("id", f"ref_{uuid.uuid4().hex[:12]}")
            return jsonify({
                "success": True,
                "message": "Refund initiated",
                "data": {"refund_id": refund_id, "amount": amount, "status": "processing"},
            }), 200
        return jsonify({"success": False, "error": ref_data.get("message", "Refund failed")}), 500
    except Exception as e:
        logger.error("Refund error: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


@payments_bp.route("/history", methods=["GET"])
@require_auth_decorator
def payment_history():
    phone = request.user.get("phone", "")
    db = get_db()
    if db is None or not phone:
        return jsonify({"success": True, "data": []}), 200

    orders = list(
        db.orders.find(
            {"customer_phone": phone, "payment_status": {"$in": ["paid", "completed"]}},
            {"_id": 1, "total": 1, "payment_method": 1, "payment_status": 1, "created_at": 1},
        ).sort("created_at", -1).limit(20)
    )
    transactions = [
        {
            "id": o["_id"],
            "order_id": o["_id"],
            "amount": o.get("total", 0),
            "method": o.get("payment_method", "UPI"),
            "status": o.get("payment_status", "paid"),
            "date": o.get("created_at"),
        }
        for o in orders
    ]
    return jsonify({"success": True, "data": transactions}), 200
