from flask import Blueprint, request, jsonify
analytics_bp = Blueprint("analytics", __name__)

def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not request.headers.get("Authorization","").startswith("Bearer "):
            return jsonify({"success":False,"error":"Unauthorized"}),401
        return f(*args, **kwargs)
    return decorated

@analytics_bp.route("/platform", methods=["GET"])
@require_auth
def platform_analytics():
    return jsonify({"success":True,"data":{"total_orders":1847,"total_revenue":324000,"platform_earnings":36940}}),200

@analytics_bp.route("/restaurant/<restaurant_id>", methods=["GET"])
@require_auth
def restaurant_analytics(restaurant_id):
    return jsonify({"success":True,"data":{"orders_last_7_days":[38,45,52,47,61,74,47],"avg_rating":4.8}}),200

@analytics_bp.route("/ai-insights", methods=["GET"])
@require_auth
def ai_insights():
    return jsonify({"success":True,"data":{"demand_prediction":"High demand tonight 7-9PM","revenue_forecast":1020000}}),200
