# -*- coding: utf-8 -*-
"""Public platform settings (fees, support contact)."""

from flask import Blueprint, jsonify, current_app

from services.platform_settings import get_platform_settings

settings_bp = Blueprint("settings", __name__)


def get_db():
    return current_app.extensions.get("mongo_db")


@settings_bp.route("/platform", methods=["GET"])
def get_public_platform_settings():
    """Return fee settings for checkout — no auth required."""
    settings = get_platform_settings(get_db())
    return jsonify({"success": True, "data": settings}), 200
