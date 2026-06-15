# -*- coding: utf-8 -*-
"""
Authentication module for Thooku Madurai.
Supports:
  1. Customer  - Google OAuth
  2. Restaurant - Username + Password
  3. Rider      - Username + Password
  4. SuperAdmin - Email + Password
"""

import os
import time
import logging

import bcrypt
import jwt
from flask import Blueprint, current_app, jsonify, request

# ---------------------------------------------------------------------------
# Blueprint & constants
# ---------------------------------------------------------------------------
auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get("JWT_SECRET", "thooku-madurai-secret-key-2026")
JWT_EXPIRY = 86400 * 7  # 7 days


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_db():
    return current_app.extensions.get("mongo_db")

def _make_token(payload: dict) -> str:
    payload["exp"] = int(time.time()) + JWT_EXPIRY
    payload["iat"] = int(time.time())
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


# ---------------------------------------------------------------------------
# Restaurant login
# ---------------------------------------------------------------------------

@auth_bp.route("/restaurant-login", methods=["POST"])
def restaurant_login():
    """
    Body: { "username": "...", "password": "..." }
    Finds restaurant by username in 'restaurants' collection.
    Verifies password with bcrypt.
    Returns JWT with role='restaurant'.
    """
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password are required"}), 400

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    restaurant = db.restaurants.find_one({"username": username})
    if restaurant is None:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    password_hash = restaurant.get("password_hash", "")
    try:
        valid = bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        valid = False

    if not valid:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    restaurant_id = str(restaurant["_id"])
    token = _make_token(
        {
            "user_id": restaurant_id,
            "role": "restaurant",
            "name": restaurant.get("name", username),
            "restaurant_id": restaurant_id,
        }
    )

    return jsonify(
        {
            "success": True,
            "message": "Login successful",
            "token": token,
            "user": {
                "id": restaurant_id,
                "name": restaurant.get("name", username),
                "username": username,
                "role": "restaurant",
                "restaurant_id": restaurant_id,
            },
        }
    ), 200


# ---------------------------------------------------------------------------
# Rider login
# ---------------------------------------------------------------------------

@auth_bp.route("/rider-login", methods=["POST"])
def rider_login():
    """
    Body: { "username": "...", "password": "..." }
    Finds rider by username in 'delivery_partners' collection.
    Verifies password with bcrypt.
    Returns JWT with role='rider'.
    """
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password are required"}), 400

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    rider = db.delivery_partners.find_one({"username": username})
    if rider is None:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    password_hash = rider.get("password_hash", "")
    try:
        valid = bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        valid = False

    if not valid:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    rider_id = str(rider["_id"])
    rider_phone = str(rider.get("phone", "")).strip()
    token = _make_token(
        {
            "user_id": rider_id,
            "role": "rider",
            "name": rider.get("name", username),
            "rider_id": rider_id,
            "phone": rider_phone,
        }
    )

    return jsonify(
        {
            "success": True,
            "message": "Login successful",
            "token": token,
            "user": {
                "id": rider_id,
                "name": rider.get("name", username),
                "username": username,
                "role": "rider",
                "rider_id": rider_id,
                "phone": rider_phone,
            },
        }
    ), 200


# ---------------------------------------------------------------------------
# SuperAdmin login
# ---------------------------------------------------------------------------

@auth_bp.route("/admin-login", methods=["POST"])
def admin_login():
    """
    Body: { "email": "...", "password": "..." }
    Finds admin by email in 'admins' collection.
    Verifies password with bcrypt.
    Returns JWT with role='superadmin'.
    """
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", "")).strip()

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required"}), 400

    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503

    admin = db.admins.find_one({"email": email})
    if admin is None:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    password_hash = admin.get("password_hash", "")
    try:
        valid = bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        valid = False

    if not valid:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    admin_id = str(admin["_id"])
    token = _make_token(
        {
            "user_id": admin_id,
            "role": "superadmin",
            "name": admin.get("name", email),
            "email": email,
        }
    )

    return jsonify(
        {
            "success": True,
            "message": "Login successful",
            "token": token,
            "user": {
                "id": admin_id,
                "name": admin.get("name", email),
                "email": email,
                "role": "superadmin",
            },
        }
    ), 200


# ── Google Login ──────────────────────────────────────────────────────────────

@auth_bp.route("/google", methods=["POST"])
def google_login():
    data = request.get_json(silent=True) or {}
    id_token = data.get("credential", "")

    if not id_token:
        return jsonify({"success": False, "message": "Missing credential"}), 400

    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        GOOGLE_CLIENT_ID = data.get("client_id", "849711418902-7reguj59f9au1c48ko8boh3eaprp0rng.apps.googleusercontent.com")
        info = google_id_token.verify_oauth2_token(id_token, google_requests.Request(), GOOGLE_CLIENT_ID)

        email = info.get("email", "")
        name = info.get("name", email.split("@")[0] if email else "User")
        google_id = info.get("sub", "")

        if not email:
            return jsonify({"success": False, "message": "Email not available from Google"}), 400

        db = get_db()
        user = None
        if db is not None:
            user = db.customers.find_one({"google_id": google_id}) or db.customers.find_one({"email": email})

        if not user:
            user_doc = {
                "google_id": google_id,
                "email": email,
                "name": name,
                "phone": data.get("phone", ""),
                "role": "customer",
                "created_at": int(time.time()),
            }
            if db is not None:
                db.customers.insert_one(user_doc)
            user = user_doc

        token = _make_token({
            "id": str(user.get("_id", "")),
            "google_id": google_id,
            "email": email,
            "phone": user.get("phone", ""),
            "name": name,
            "role": "customer",
        })

        return jsonify({
            "success": True,
            "message": "Google login successful",
            "data": {
                "token": token,
                "user": {
                    "name": name,
                    "email": email,
                    "phone": user.get("phone", ""),
                    "role": "customer",
                },
            },
        }), 200

    except ValueError as e:
        return jsonify({"success": False, "message": f"Invalid Google token: {str(e)}"}), 401
    except Exception as e:
        logger.error("Google login error: %s", str(e))
        return jsonify({"success": False, "message": "Google login failed"}), 500


@auth_bp.route("/save-phone", methods=["POST"])
def save_phone():
    auth_hdr = request.headers.get("Authorization", "")
    if not auth_hdr.startswith("Bearer "):
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    try:
        payload = jwt.decode(auth_hdr.split(" ", 1)[1], JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return jsonify({"success": False, "message": "Invalid token"}), 401
    data = request.get_json(silent=True) or {}
    phone = str(data.get("phone", "")).strip()
    if not phone or not phone.isdigit() or len(phone) != 10:
        return jsonify({"success": False, "message": "Valid 10-digit phone number required"}), 400
    db = get_db()
    if db is None:
        return jsonify({"success": False, "message": "Database unavailable"}), 503
    email = payload.get("email", "")
    google_id = payload.get("google_id", "")
    if email:
        db.customers.update_one({"email": email}, {"$set": {"phone": phone}})
    elif google_id:
        db.customers.update_one({"google_id": google_id}, {"$set": {"phone": phone}})
    return jsonify({"success": True, "message": "Phone saved", "data": {"phone": phone}}), 200
