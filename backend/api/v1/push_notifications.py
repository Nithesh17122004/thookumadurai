from flask import Blueprint, request, jsonify, current_app
from pywebpush import webpush, WebPushException
from datetime import datetime, timedelta
from functools import wraps
import jwt, json, os

push_bp = Blueprint('push', __name__)

_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'private_key.pem')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY') or _KEY_FILE
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY', '')
VAPID_CLAIMS = {"sub": "mailto:admin@thooku.com"}

def _get_db():
    return current_app.extensions.get("mongo_db")

def _get_socketio():
    from app import socketio
    return socketio

def init_push_indexes():
    db = _get_db()
    if db is not None:
        try:
            db.call_offers.create_index("expires_at", expireAfterSeconds=0)
        except Exception:
            pass

def _auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        try:
            data = jwt.decode(token, os.getenv('JWT_SECRET'), algorithms=['HS256'])
            request.user = data
        except Exception:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

@push_bp.route('/api/v1/push/subscribe', methods=['POST'])
@_auth
def subscribe():
    sub = request.json.get('subscription')
    user_id = request.user.get('id') or request.user.get('user_id') or request.user.get('google_id')
    role = request.user.get('role', 'customer')
    db = _get_db()
    if db is None:
        return jsonify({'error': 'Database unavailable'}), 503
    db.push_subscriptions.update_one(
        {'user_id': user_id},
        {'$addToSet': {'subscriptions': sub}, '$set': {'role': role, 'user_id': user_id}},
        upsert=True
    )
    return jsonify({'status': 'subscribed'})

def store_sdp_offer(call_id, sdp, caller_id, callee_id, order_id):
    db = _get_db()
    if db is None:
        return
    db.call_offers.replace_one(
        {'call_id': call_id},
        {
            'call_id': call_id,
            'sdp': sdp,
            'caller_id': caller_id,
            'callee_id': callee_id,
            'order_id': order_id,
            'expires_at': datetime.utcnow() + timedelta(seconds=60)
        },
        upsert=True
    )

@push_bp.route('/api/v1/push/page-ready', methods=['POST'])
@_auth
def page_ready():
    call_id = request.json.get('callId')
    order_id = request.json.get('orderId')
    db = _get_db()
    sio = _get_socketio()
    if db is None:
        return jsonify({'error': 'Database unavailable'}), 503
    doc = db.call_offers.find_one({'call_id': call_id})
    if not doc:
        return jsonify({'error': 'offer expired or not found'}), 404
    sio.emit('call_offer', {
        'order_id': doc['order_id'],
        'sdp': doc['sdp'],
        'caller_name': 'Incoming Call',
        'callId': call_id,
        'orderId': doc['order_id'],
        'callerId': doc['caller_id'],
        'calleeId': doc['callee_id'],
        'replay': True
    }, room=doc['order_id'])
    # Also emit to rider room if callee_id looks like a rider
    if doc.get('callee_id'):
        sio.emit('call_offer', {
            'order_id': doc['order_id'],
            'sdp': doc['sdp'],
            'caller_name': 'Incoming Call',
            'callId': call_id,
            'orderId': doc['order_id'],
            'callerId': doc['caller_id'],
            'calleeId': doc['callee_id'],
            'replay': True
        }, room='rider_' + doc['callee_id'])
    return jsonify({'status': 'replayed'})

@push_bp.route('/api/v1/push/pending-offer/<call_id>', methods=['GET'])
@_auth
def get_pending_offer(call_id):
    db = _get_db()
    if db is None:
        return jsonify({'error': 'Database unavailable'}), 503
    doc = db.call_offers.find_one({'call_id': call_id})
    if not doc:
        return jsonify({'error': 'offer expired or not found'}), 404
    return jsonify({
        'sdp': doc['sdp'],
        'callId': doc['call_id'],
        'orderId': doc['order_id'],
        'callerId': doc['caller_id']
    })

@push_bp.route('/api/v1/push/call-rider', methods=['POST'])
@_auth
def call_rider():
    data = request.json
    rider_id = data['riderId']
    call_id = data['callId']
    order_id = data['orderId']
    caller_name = data.get('callerName', 'Customer')
    db = _get_db()
    if db is None:
        return jsonify({'error': 'Database unavailable'}), 503
    doc = db.push_subscriptions.find_one({'user_id': rider_id})
    if not doc or not doc.get('subscriptions'):
        return jsonify({'error': 'Rider has no push subscription'}), 404
    _send_push_to_all(doc['subscriptions'], {
        'callId': call_id,
        'callerName': caller_name,
        'callerRole': 'customer',
        'orderId': order_id
    })
    return jsonify({'status': 'push sent'})

@push_bp.route('/api/v1/push/call-customer', methods=['POST'])
@_auth
def call_customer():
    data = request.json
    customer_phone = data.get('customerPhone') or data.get('customerId', '')
    call_id = data['callId']
    order_id = data['orderId']
    caller_name = data.get('callerName', 'Your Rider')
    db = _get_db()
    if db is None:
        return jsonify({'error': 'Database unavailable'}), 503
    # Try to find the customer's push subscription by email or google_id
    # First look up the customer by phone
    user_id_filter = customer_phone
    if db is not None and customer_phone:
        cust_doc = db.customers.find_one({'phone': customer_phone})
        if cust_doc:
            user_id_filter = cust_doc.get('email') or cust_doc.get('google_id') or customer_phone
    doc = db.push_subscriptions.find_one({'user_id': user_id_filter})
    if not doc or not doc.get('subscriptions'):
        # Also try direct phone lookup
        doc = db.push_subscriptions.find_one({'user_id': customer_phone})
    if not doc or not doc.get('subscriptions'):
        return jsonify({'error': 'Customer has no push subscription'}), 404
    _send_push_to_all(doc['subscriptions'], {
        'callId': call_id,
        'callerName': caller_name,
        'callerRole': 'rider',
        'orderId': order_id,
        'customerPhone': customer_phone
    })
    return jsonify({'status': 'push sent'})

@push_bp.route('/api/v1/push/call-declined', methods=['POST'])
def call_declined():
    data = request.json
    sio = _get_socketio()
    if data.get('orderId'):
        sio.emit('call_decline', {
            'callId': data.get('callId'),
            'orderId': data.get('orderId')
        }, room=data.get('orderId'))
    return jsonify({'status': 'declined'})

def _send_push_to_all(subscriptions, payload):
    db = _get_db()
    dead = []
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub,
                data=json.dumps(payload),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS
            )
        except WebPushException as e:
            if '410' in str(e) or '404' in str(e):
                dead.append(sub)
            else:
                print('Push error:', e)
    if dead and db is not None:
        for sub in dead:
            db.push_subscriptions.update_many({}, {'$pull': {'subscriptions': sub}})
