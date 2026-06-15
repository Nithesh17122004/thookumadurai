# -*- coding: utf-8 -*-
"""
Thooku Madurai — Tracking API
Live rider GPS via Redis + Socket.IO emit.
"""
import json, time, logging
from flask import Blueprint, current_app, jsonify, request

tracking_bp = Blueprint('tracking', __name__)
analytics_bp = Blueprint('analytics', __name__)
logger = logging.getLogger(__name__)


def _redis():   return current_app.extensions.get('redis_client')
def _db():      return current_app.extensions.get('mongo_db')


def _require_auth(f):
    import functools, os, jwt as _jwt
    SECRET = os.environ.get('JWT_SECRET', 'thooku-madurai-secret-key-2026')
    @functools.wraps(f)
    def inner(*a, **kw):
        hdr = request.headers.get('Authorization', '')
        if not hdr.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        try:
            request.user = _jwt.decode(hdr.split(' ', 1)[1], SECRET, algorithms=['HS256'])
        except _jwt.InvalidTokenError:
            return jsonify({'success': False, 'error': 'Invalid token'}), 401
        return f(*a, **kw)
    return inner


# ── Redis helpers ──────────────────────────────────────────────────────────

def store_rider_loc(rider_id, lat, lng, heading=0, order_id=None):
    payload = {'lat': lat, 'lng': lng, 'heading': heading,
               'ts': int(time.time()), 'rider_id': rider_id}
    db = _db()
    # Always store in MongoDB (works even without Redis)
    if db is not None:
        try:
            db.delivery_partners.update_one(
                {'_id': rider_id},
                {'$set': {'current_location': {'lat': lat, 'lng': lng},
                          'updated_at': int(time.time())}}
            )
        except Exception as e:
            logger.warning(f'MongoDB rider location write: {e}')
            # Try with string _id
            try:
                from bson.objectid import ObjectId
                db.delivery_partners.update_one(
                    {'_id': ObjectId(rider_id)},
                    {'$set': {'current_location': {'lat': lat, 'lng': lng},
                              'updated_at': int(time.time())}}
                )
            except Exception:
                pass
    rc = _redis()
    if rc:
        try:
            rc.setex(f'rider:{rider_id}:loc', 60, json.dumps(payload))
            if order_id:
                rc.setex(f'order:{order_id}:rider', 3600, rider_id)
        except Exception as e:
            logger.warning(f'Redis write: {e}')
    # Push via Socket.IO
    try:
        from app import socketio
        room = f'order_{order_id}' if order_id else f'rider_{rider_id}'
        socketio.emit('location_update', payload, room=room)
    except Exception as e:
        logger.debug(f'SocketIO emit: {e}')
    return payload


def get_rider_loc(rider_id):
    rc = _redis()
    if rc:
        try:
            raw = rc.get(f'rider:{rider_id}:loc')
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    # Fallback: read from MongoDB
    db = _db()
    if db is not None:
        try:
            rider = db.delivery_partners.find_one({'_id': rider_id}, {'current_location': 1})
            if rider and rider.get('current_location'):
                loc = rider['current_location']
                return {'lat': loc.get('lat', 9.9252), 'lng': loc.get('lng', 78.1198),
                        'heading': 0, 'ts': int(time.time()), 'rider_id': rider_id}
        except Exception:
            try:
                from bson.objectid import ObjectId
                rider = db.delivery_partners.find_one({'_id': ObjectId(rider_id)}, {'current_location': 1})
                if rider and rider.get('current_location'):
                    loc = rider['current_location']
                    return {'lat': loc.get('lat', 9.9252), 'lng': loc.get('lng', 78.1198),
                            'heading': 0, 'ts': int(time.time()), 'rider_id': rider_id}
            except Exception:
                pass
    return None
    return None


# ── Tracking endpoints ─────────────────────────────────────────────────────

@tracking_bp.route('/order/<order_id>', methods=['GET'])
@_require_auth
def track_order(order_id):
    db = _db()
    order = db.orders.find_one({'_id': order_id}) if db is not None else None

    rider_loc = None
    if order and order.get('rider_id'):
        rider_loc = get_rider_loc(order['rider_id'])

    if not rider_loc:
        rider_loc = {'lat': 9.9252, 'lng': 78.1198, 'heading': 45, 'ts': int(time.time())}

    rest_loc = {'lat': 9.9310, 'lng': 78.1200}
    if order and order.get('restaurant_id') and db is not None:
        r = db.restaurants.find_one({'_id': order['restaurant_id']}, {'lat': 1, 'lng': 1})
        r = db.restaurants.find_one({'_id': order['restaurant_id']}, {'lat': 1, 'lng': 1})
        if r and r.get('lat'):
            rest_loc = {'lat': r['lat'], 'lng': r['lng']}

    status = (order or {}).get('status', 'preparing')

    cust_loc = {'lat': 9.9252, 'lng': 78.1198}
    if order:
        # Try delivery_address first
        da = order.get('delivery_address') or {}
        if da.get('lat') and da.get('lng'):
            cust_loc = {'lat': float(da['lat']), 'lng': float(da['lng'])}
        else:
            # Fallback to delivery_location
            dl = order.get('delivery_location') or {}
            if dl.get('lat') and dl.get('lng'):
                cust_loc = {'lat': float(dl['lat']), 'lng': float(dl['lng'])}

    dones = {
        'confirmed': True,
        'preparing': status in ('preparing','ready_for_pickup','out_for_delivery','delivered'),
        'rider_assigned': status in ('ready_for_pickup','out_for_delivery','delivered'),
        'picked_up': status in ('out_for_delivery','delivered'),
        'delivered': status == 'delivered',
    }
    return jsonify({'success': True, 'data': {
        'order_id': order_id, 'status': status,
        'rider': {'name': (order or {}).get('rider_name', 'Your Rider'),
                  'lat': rider_loc['lat'], 'lng': rider_loc['lng'],
                  'heading': rider_loc.get('heading', 0)},
        'restaurant': rest_loc,
        'customer': cust_loc,
        'eta': '18 minutes',
        'steps': [{'step': k, 'done': v} for k, v in dones.items()],
    }}), 200


@tracking_bp.route('/rider/<rider_id>/location', methods=['GET'])
@_require_auth
def get_rider_location(rider_id):
    loc = get_rider_loc(rider_id)
    if not loc:
        loc = {'lat': 9.9252, 'lng': 78.1198, 'heading': 0, 'ts': int(time.time())}
    return jsonify({'success': True, 'data': loc}), 200


@tracking_bp.route('/rider/<rider_id>/location', methods=['POST', 'PATCH'])
@_require_auth
def push_rider_location(rider_id):
    """Called every 4 s from rider app — stores in Redis + emits Socket.IO."""
    data = request.get_json(silent=True) or {}
    lat, lng = data.get('lat'), data.get('lng')
    if lat is None or lng is None:
        return jsonify({'success': False, 'error': 'lat and lng required'}), 400

    heading  = float(data.get('heading', 0))
    order_id = data.get('order_id')

    payload = store_rider_loc(rider_id, float(lat), float(lng), heading, order_id)
    return jsonify({'success': True, 'data': payload}), 200


@tracking_bp.route('/area/serviceability', methods=['POST'])
def check_serviceability():
    data = request.get_json(silent=True) or {}
    if not data.get('lat') or not data.get('lng'):
        return jsonify({'success': False, 'error': 'lat/lng required'}), 400
    return jsonify({'success': True, 'data': {
        'serviceable': True, 'area': 'Madurai',
        'estimated_delivery': '25-40 min', 'distance_km': 3.2
    }}), 200


@tracking_bp.route('/geocode', methods=['POST'])
def reverse_geocode():
    """Convert lat/lng → address via Nominatim (free, no API key)."""
    import requests as req
    data = request.get_json(silent=True) or {}
    lat = float(data.get('lat', 9.9252))
    lng = float(data.get('lng', 78.1198))
    try:
        r = req.get(
            'https://nominatim.openstreetmap.org/reverse',
            params={'lat': lat, 'lon': lng, 'format': 'json', 'addressdetails': 1},
            headers={'User-Agent': 'ThookuMadurai/1.0'},
            timeout=6
        )
        nom  = r.json()
        addr = nom.get('address', {})
        return jsonify({'success': True, 'data': {
            'house':        addr.get('house_number', ''),
            'street':       addr.get('road', addr.get('pedestrian', '')),
            'area':         addr.get('suburb', addr.get('neighbourhood',
                            addr.get('village', addr.get('county', 'Madurai')))),
            'city':         addr.get('city', addr.get('town', 'Madurai')),
            'state':        addr.get('state', 'Tamil Nadu'),
            'pincode':      addr.get('postcode', ''),
            'full_address': nom.get('display_name', ''),
            'lat': lat, 'lng': lng,
        }}), 200
    except Exception as e:
        logger.warning(f'Nominatim error: {e}')
        return jsonify({'success': True, 'data': {
            'house': '', 'street': '', 'area': 'Madurai',
            'city': 'Madurai', 'state': 'Tamil Nadu', 'pincode': '625020',
            'full_address': f'{lat},{lng}', 'lat': lat, 'lng': lng,
        }}), 200


# ── Socket.IO handlers (registered from app.py) ────────────────────────────

def register_socketio_handlers(socketio):
    @socketio.on('join_order')
    def on_join(data):
        from flask_socketio import join_room
        oid = data.get('order_id', '')
        if oid:
            join_room(f'order_{oid}')
            socketio.emit('joined', {'room': f'order_{oid}'}, room=f'order_{oid}')

    @socketio.on('leave_order')
    def on_leave(data):
        from flask_socketio import leave_room
        oid = data.get('order_id', '')
        if oid:
            leave_room(f'order_{oid}')

    @socketio.on('join_rider')
    def on_rider_join(data):
        from flask_socketio import join_room
        rid = data.get('rider_id', '')
        if rid:
            join_room(f'rider_{rid}')
        # Also join the global riders room for new_order broadcasts
        join_room('riders')

    @socketio.on('leave_rider')
    def on_rider_leave(data):
        from flask_socketio import leave_room
        rid = data.get('rider_id', '')
        if rid:
            leave_room(f'rider_{rid}')
        leave_room('riders')

    @socketio.on('connect')
    def on_connect():
        pass

    # ── WebRTC Call Signaling (relay only) ──────────────────────────────

    @socketio.on('call_offer')
    def on_call_offer(data):
        oid = data.get('order_id', '')
        if oid:
            socketio.emit('call_offer', data, room=f'order_{oid}', include_self=False)
        # Store SDP for push-replay
        try:
            from api.v1.push_notifications import store_sdp_offer
            call_id = data.get('callId') or (oid + '_' + str(int(time.time())))
            caller_name = data.get('caller_name', 'Caller')
            role = data.get('caller_role', 'customer')
            # Determine caller_id/callee_id from order data if available
            db = current_app.extensions.get("mongo_db")
            caller_id = ''
            callee_id = ''
            if db is not None:
                order_doc = db.orders.find_one({'_id': oid})
                if order_doc:
                    if role == 'customer':
                        caller_id = order_doc.get('customer_phone', '')
                        callee_id = order_doc.get('rider_id', '')
                    elif role == 'rider':
                        caller_id = order_doc.get('rider_id', '')
                        callee_id = order_doc.get('customer_phone', '')
            store_sdp_offer(call_id, data.get('sdp'), caller_id, callee_id, oid)
        except Exception:
            pass

    @socketio.on('call_answer')
    def on_call_answer(data):
        oid = data.get('order_id', '')
        if oid:
            socketio.emit('call_answer', data, room=f'order_{oid}', include_self=False)

    @socketio.on('ice_candidate')
    def on_ice_candidate(data):
        oid = data.get('order_id', '')
        if oid:
            socketio.emit('ice_candidate', data, room=f'order_{oid}', include_self=False)

    @socketio.on('call_end')
    def on_call_end(data):
        oid = data.get('order_id', '')
        if oid:
            socketio.emit('call_end', data, room=f'order_{oid}')

    @socketio.on('call_decline')
    def on_call_decline(data):
        oid = data.get('order_id', '')
        if oid:
            socketio.emit('call_decline', data, room=f'order_{oid}', include_self=False)

    @socketio.on('agora_fallback')
    def on_agora_fallback(data):
        oid = data.get('order_id', '')
        if oid:
            socketio.emit('agora_fallback', data, room=f'order_{oid}', include_self=False)


# ── Analytics ─────────────────────────────────────────────────────────────

@analytics_bp.route('/platform', methods=['GET'])
def platform_analytics():
    return jsonify({'success': True, 'data': {
        'total_orders': 1847, 'total_revenue': 324000,
        'platform_earnings': 36940, 'avg_order_value': 175,
        'top_restaurant': 'Thalapakattu Biryani',
        'top_area': 'Anna Nagar', 'peak_hour': '7PM-9PM',
    }}), 200

@analytics_bp.route('/restaurant/<restaurant_id>', methods=['GET'])
def restaurant_analytics(restaurant_id):
    return jsonify({'success': True, 'data': {
        'orders_last_7_days': [38,45,52,47,61,74,47],
        'revenue_last_7_days': [6840,8100,9360,8460,10980,13320,8460],
        'top_items': [{'name':'Chicken Biryani','orders':245},
                      {'name':'Mutton Biryani','orders':132}],
        'avg_rating': 4.8, 'cancellation_rate': 2.1,
    }}), 200

@analytics_bp.route('/ai-insights', methods=['GET'])
def ai_insights():
    return jsonify({'success': True, 'data': {
        'demand_prediction': {'tonight_7to9pm': 'High demand expected.'},
        'fraud_alerts': [],
        'revenue_forecast': {'this_month': 1020000, 'confidence': 87},
        'top_performing_areas': ['Anna Nagar','KK Nagar','Tallakulam'],
    }}), 200
