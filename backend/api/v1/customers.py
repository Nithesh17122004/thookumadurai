from flask import Blueprint, request, jsonify

customers_bp = Blueprint("customers", __name__)

def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not request.headers.get("Authorization","").startswith("Bearer "):
            return jsonify({"success":False,"error":"Unauthorized"}),401
        return f(*args, **kwargs)
    return decorated

@customers_bp.route("/profile", methods=["GET"])
@require_auth
def get_profile():
    return jsonify({"success":True,"data":{}}),200

@customers_bp.route("/profile", methods=["PUT"])
@require_auth
def update_profile():
    data = request.get_json(silent=True) or {}
    return jsonify({"success":True,"message":"Profile updated"}),200

@customers_bp.route("/addresses", methods=["GET"])
@require_auth
def get_addresses():
    return jsonify({"success":True,"data":[]}),200

@customers_bp.route("/addresses", methods=["POST"])
@require_auth
def add_address():
    data = request.get_json(silent=True) or {}
    return jsonify({"success":True,"message":"Address added","data":{"id":"addr_new","...":data}}),201

@customers_bp.route("/favourites", methods=["GET"])
@require_auth
def get_favourites():
    return jsonify({"success":True,"data":{"restaurants":[],"items":[]}}),200

@customers_bp.route("/favourites/restaurant/<restaurant_id>", methods=["POST"])
@require_auth
def toggle_favourite_restaurant(restaurant_id):
    return jsonify({"success":True,"message":"Favourite toggled"}),200

@customers_bp.route("/referral", methods=["GET"])
@require_auth
def get_referral():
    return jsonify({"success":True,"data":{}}),200

@customers_bp.route("/support", methods=["POST"])
@require_auth
def raise_support_ticket():
    data = request.get_json(silent=True) or {}
    return jsonify({"success":True,"message":"Support ticket raised. We will respond within 2 hours.","data":{}}),201
