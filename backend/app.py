import eventlet
eventlet.monkey_patch()

# ============================================================
# THOOKU MADURAI — FLASK BACKEND
# REST API + WebSocket (Socket.IO) + Redis live tracking
# + Auto-refund scheduler
# ============================================================
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO
import jwt, bcrypt, os, logging
from datetime import datetime
from functools import wraps

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── App setup ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'tm-ws-secret-2026')
app.config['CORS_ORIGINS'] = '*'
app.config['CORS_SUPPORTS_CREDENTIALS'] = True
app.config['CORS_ALLOW_HEADERS'] = ['Content-Type', 'Authorization', 'X-Requested-With']
app.config['CORS_METHODS'] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
CORS(app, resources={r"/api/*": {"origins": "*"}})

socketio = SocketIO(
    app,
    cors_allowed_origins='*',
    async_mode='eventlet',
    logger=False,
    engineio_logger=False,
)

limiter = Limiter(get_remote_address, app=app,
                  default_limits=['300 per minute'], storage_uri='memory://')

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

JWT_SECRET    = os.environ.get('JWT_SECRET', 'thooku-madurai-secret-key-2026')
JWT_ALGORITHM = 'HS256'

# ── Database ───────────────────────────────────────────────────────────────
from pymongo import MongoClient
import redis as _redis_mod

MONGO_URI = os.environ.get('MONGO_URI', '')
REDIS_URL  = os.environ.get('REDIS_URL', 'redis://localhost:6379')

db = None
if MONGO_URI:
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = mongo_client['thooku_madurai']
        logger.info('MongoDB connected')
    except Exception as e:
        logger.warning(f'MongoDB failed: {e}')
else:
    logger.warning('MONGO_URI not set — mock/demo mode')

try:
    redis_client = _redis_mod.from_url(REDIS_URL, decode_responses=False)
    redis_client.ping()
    logger.info('Redis connected')
except Exception as e:
    logger.warning(f'Redis failed: {e}')
    redis_client = None

app.extensions['mongo_db']     = db
app.extensions['redis_client'] = redis_client

# ── Background Scheduler (auto-refund for orders with no rider) ──────────
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler(daemon=True)
    # Import the auto-refund function from orders blueprint
    from api.v1.orders import process_auto_refunds

    def scheduled_refund_check():
        """Wrapper to run inside app context."""
        with app.app_context():
            try:
                process_auto_refunds()
                logger.debug("Auto-refund check complete")
            except Exception as e:
                logger.error(f"Auto-refund check error: {e}")

    scheduler.add_job(
        func=scheduled_refund_check,
        trigger='interval',
        seconds=60,  # check every 60 seconds
        id='auto_refund_job',
        name='Check orders with no rider and process refunds',
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Auto-refund scheduler started (checking every 60s)")
except ImportError:
    logger.warning("APScheduler not installed — auto-refund disabled")
except Exception as e:
    logger.warning(f"Scheduler init failed: {e}")

# ── Middleware ─────────────────────────────────────────────────────────────
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authentication required', 'code': 'UNAUTHORIZED'}), 401
        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            request.user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired', 'code': 'TOKEN_EXPIRED'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token', 'code': 'INVALID_TOKEN'}), 401
        return f(*args, **kwargs)
    return decorated

def require_role(*roles):
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated(*args, **kwargs):
            if request.user.get('role') not in roles:
                return jsonify({'error': 'Access denied', 'code': 'FORBIDDEN'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def api_response(data=None, message='Success', status=200, error=None):
    if error:
        return jsonify({'success': False, 'error': error}), status
    return jsonify({'success': True, 'message': message, 'data': data,
                    'timestamp': datetime.utcnow().isoformat()}), status


# ── Security headers ───────────────────────────────────────────────────────
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options']  = 'nosniff'
    response.headers['X-Frame-Options']          = 'DENY'
    response.headers['X-XSS-Protection']         = '1; mode=block'
    response.headers['Referrer-Policy']           = 'strict-origin-when-cross-origin'
    return response

# ── Health ─────────────────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health_check():
    return api_response({
        'service':   'Thooku Madurai API',
        'version':   '4.0.0',
        'database':  'connected' if db is not None else 'disconnected',
        'cache':     'connected' if redis_client is not None else 'disconnected',
        'websocket': 'enabled (Socket.IO)',
        'scheduler': 'running',
        'payment':   'Instamojo',
        'timestamp': datetime.utcnow().isoformat(),
    })


# ── Blueprints ─────────────────────────────────────────────────────────────
from api.v1.auth        import auth_bp
from api.v1.customers   import customers_bp
from api.v1.restaurants import restaurants_bp
from api.v1.riders      import riders_bp
from api.v1.orders      import orders_bp
from api.v1.payments    import payments_bp
from api.v1.admin       import admin_bp
from api.v1.tracking    import tracking_bp, analytics_bp, register_socketio_handlers
from api.v1.coupons     import coupons_bp
from api.v1.settings    import settings_bp
from api.v1.push_notifications import push_bp, init_push_indexes

app.register_blueprint(auth_bp,        url_prefix='/api/v1/auth')
app.register_blueprint(customers_bp,   url_prefix='/api/v1/customers')
app.register_blueprint(restaurants_bp, url_prefix='/api/v1/restaurants')
app.register_blueprint(riders_bp,      url_prefix='/api/v1/riders')
app.register_blueprint(orders_bp,      url_prefix='/api/v1/orders')
app.register_blueprint(payments_bp,    url_prefix='/api/v1/payments')
app.register_blueprint(admin_bp,       url_prefix='/api/v1/admin')
app.register_blueprint(tracking_bp,    url_prefix='/api/v1/tracking')
app.register_blueprint(analytics_bp,   url_prefix='/api/v1/analytics')
app.register_blueprint(coupons_bp,     url_prefix='/api/v1/coupons')
app.register_blueprint(settings_bp,    url_prefix='/api/v1/settings')
app.register_blueprint(push_bp)

register_socketio_handlers(socketio)

with app.app_context():
    init_push_indexes()

from flask import send_from_directory
import os.path as osp

FRONTEND_DIR = osp.join(osp.dirname(osp.abspath(__file__)), '..', 'frontend')

@app.route('/')
def serve_login():
    return send_from_directory(FRONTEND_DIR, 'login.html')

@app.route('/<path:filename>')
def serve_frontend(filename):
    full = osp.join(FRONTEND_DIR, filename)
    if osp.exists(full):
        return send_from_directory(FRONTEND_DIR, filename)
    if osp.exists(full + '.html'):
        return send_from_directory(FRONTEND_DIR, filename + '.html')
    # Not found — let error handler deal with it
    from flask import abort
    abort(404)

# ── Error handlers ─────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):      return api_response(error='Endpoint not found', status=404)
@app.errorhandler(405)
def method_not_allowed(e): return api_response(error='Method not allowed', status=405)
@app.errorhandler(429)
def too_many_requests(e):  return api_response(error='Too many requests.', status=429)
@app.errorhandler(500)
def internal_error(e):
    logger.error(f'Internal server error: {e}')
    return api_response(error='Internal server error', status=500)

# ── Main ───────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f'Starting Thooku Madurai API on :{port} with SocketIO (threading)')
    socketio.run(app, host='0.0.0.0', port=port, debug=False,
                 allow_unsafe_werkzeug=True)
