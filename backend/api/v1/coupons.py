# -*- coding: utf-8 -*-
"""Public coupon validation for checkout."""

import time
from flask import Blueprint, current_app, jsonify, request

coupons_bp = Blueprint("coupons", __name__)


def get_db():
    return current_app.extensions.get("mongo_db")


@coupons_bp.route("/validate", methods=["POST"])
def validate_coupon():
    """
    Body: { "code": "SAVE50", "order_amount": 500 }
    Returns discount amount for checkout.
    """
    data = request.get_json(silent=True) or {}
    code = str(data.get("code", "")).strip().upper()
    order_amount = float(data.get("order_amount", 0))

    if not code:
        return jsonify({"success": False, "message": "Coupon code is required"}), 400
    if order_amount <= 0:
        return jsonify({"success": False, "message": "Invalid order amount"}), 400

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    coupon = db.coupons.find_one({"code": code, "is_active": True})
    if coupon is None:
        return jsonify({"success": False, "message": "Invalid or expired coupon"}), 404

    expires_at = coupon.get("expires_at")
    if expires_at and int(expires_at) < int(time.time()):
        return jsonify({"success": False, "message": "Coupon has expired"}), 400

    min_order = float(coupon.get("min_order", 0))
    if order_amount < min_order:
        return jsonify(
            {
                "success": False,
                "message": f"Minimum order amount is ₹{int(min_order)}",
            }
        ), 400

    max_uses = int(coupon.get("max_uses", 0))
    uses = int(coupon.get("uses", 0))
    if max_uses > 0 and uses >= max_uses:
        return jsonify({"success": False, "message": "Coupon usage limit reached"}), 400

    discount_type = coupon.get("discount_type", "flat")
    discount_value = float(coupon.get("discount_value", 0))
    if discount_type == "percent":
        discount_amount = round(order_amount * discount_value / 100)
    else:
        discount_amount = int(discount_value)

    discount_amount = min(discount_amount, int(order_amount))

    return jsonify(
        {
            "success": True,
            "message": "Coupon applied",
            "data": {
                "code": code,
                "discount_amount": discount_amount,
                "discount_type": discount_type,
                "value": discount_value,
            },
        }
    ), 200
