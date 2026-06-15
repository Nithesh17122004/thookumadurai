# -*- coding: utf-8 -*-
"""Platform-wide fee and contact settings stored in MongoDB."""

DEFAULT_PLATFORM_FEE = 20.0
DEFAULT_DELIVERY_BASE_FEE = 30.0


def get_platform_settings(db=None):
    """Return platform fee config from MongoDB, with sensible defaults."""
    if db is None:
        try:
            from flask import current_app
            db = current_app.extensions.get("mongo_db")
        except RuntimeError:
            db = None

    defaults = {
        "platform_fee": DEFAULT_PLATFORM_FEE,
        "delivery_base_fee": DEFAULT_DELIVERY_BASE_FEE,
        "support_phone": "",
    }
    if db is None:
        return defaults

    doc = db.settings.find_one({"_id": "platform"}) or {}
    return {
        "platform_fee": float(doc.get("platform_fee", DEFAULT_PLATFORM_FEE)),
        "delivery_base_fee": float(doc.get("delivery_base_fee", DEFAULT_DELIVERY_BASE_FEE)),
        "support_phone": str(doc.get("support_phone", "")),
    }
