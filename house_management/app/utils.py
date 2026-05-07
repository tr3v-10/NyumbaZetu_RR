"""
Shared utility functions — visitor tracking, file handling, decorators, etc.
"""
import os
import uuid
import hashlib
import logging
from functools import wraps
from datetime import datetime
from flask import request, current_app, abort, g
from flask_login import current_user

logger = logging.getLogger(__name__)


# ─── Visitor / Forensic Tracking ─────────────────────────────────────────────

def collect_visitor_data():
    """
    Collect all available forensic information from the current HTTP request.
    Captures IP, MAC (if available via custom header), user-agent, geolocation, etc.
    """
    try:
        from user_agents import parse as ua_parse

        # IP addresses — try multiple headers (proxy-aware)
        ip = (
            request.headers.get('CF-Connecting-IP') or
            request.headers.get('X-Real-IP') or
            (request.headers.get('X-Forwarded-For', '').split(',')[0].strip()) or
            request.remote_addr or
            '0.0.0.0'
        )

        # User-agent parsing
        ua_string = request.headers.get('User-Agent', '')
        ua = ua_parse(ua_string)

        visitor_data = {
            'ip_address': ip,
            'forwarded_for': request.headers.get('X-Forwarded-For', ''),
            'real_ip': request.headers.get('X-Real-IP', ''),
            'cf_connecting_ip': request.headers.get('CF-Connecting-IP', ''),
            'x_forwarded_for': request.headers.get('X-Forwarded-For', ''),
            # MAC address — available only via custom header from native app or internal network
            'mac_address': request.headers.get('X-Device-Mac', None),
            'device_fingerprint': request.headers.get('X-Device-Fingerprint', None),
            'user_agent': ua_string,
            'browser': ua.browser.family,
            'browser_version': ua.browser.version_string,
            'os': ua.os.family,
            'os_version': ua.os.version_string,
            'device_type': 'mobile' if ua.is_mobile else ('tablet' if ua.is_tablet else ('bot' if ua.is_bot else 'desktop')),
            'device_brand': ua.device.brand,
            'device_model': ua.device.model,
            'is_mobile': ua.is_mobile or ua.is_tablet,
            'is_bot': ua.is_bot,
            'method': request.method,
            'path': request.path,
            'query_string': request.query_string.decode('utf-8', errors='replace'),
            'referrer': request.referrer,
            'origin': request.headers.get('Origin', ''),
            'host': request.host,
            'accept_language': request.headers.get('Accept-Language', ''),
            'accept_encoding': request.headers.get('Accept-Encoding', ''),
            'content_type': request.content_type,
            'session_id': request.cookies.get('session', ''),
            'all_headers': dict(request.headers),
        }

        # GeoIP lookup
        geo = _geoip_lookup(ip)
        visitor_data.update(geo)

        return visitor_data
    except Exception as e:
        logger.error(f"Visitor data collection error: {e}")
        return {'ip_address': request.remote_addr}


def _geoip_lookup(ip_address):
    """Look up geolocation data using GeoIP2."""
    try:
        import geoip2.database
        db_path = current_app.config.get('GEOIP_DATABASE_PATH', '')
        if not db_path or not os.path.exists(db_path):
            return {}

        with geoip2.database.Reader(db_path) as reader:
            response = reader.city(ip_address)
            return {
                'country': response.country.name,
                'country_code': response.country.iso_code,
                'region': response.subdivisions.most_specific.name if response.subdivisions else None,
                'city': response.city.name,
                'latitude': float(response.location.latitude) if response.location.latitude else None,
                'longitude': float(response.location.longitude) if response.location.longitude else None,
                'timezone': response.location.time_zone,
            }
    except Exception:
        return {}


def log_visitor(user_id=None):
    """Write visitor log entry to database."""
    from app.models.visitor import VisitorLog
    from app.extensions import db

    try:
        data = collect_visitor_data()
        log = VisitorLog(
            user_id=user_id or (current_user.id if current_user and current_user.is_authenticated else None),
            **{k: v for k, v in data.items() if hasattr(VisitorLog, k)}
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"Visitor log error: {e}")
        db.session.rollback()


def log_audit(action, resource_type=None, resource_id=None, details=None, status='success'):
    """Write an audit log entry."""
    from app.models.user import AuditLog
    from app.extensions import db

    try:
        log = AuditLog(
            user_id=current_user.id if current_user and current_user.is_authenticated else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent') if request else None,
            status=status,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"Audit log error: {e}")


# ─── Role Decorators ──────────────────────────────────────────────────────────

def role_required(*roles):
    """Decorator: restrict access to users with specified roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def super_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'super_admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ─── File Handling ────────────────────────────────────────────────────────────

def allowed_file(filename, file_type='all'):
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    allowed = current_app.config.get(
        f'ALLOWED_{file_type.upper()}_EXTENSIONS',
        current_app.config.get('ALLOWED_ALL_EXTENSIONS', set())
    )
    return ext in allowed


def save_file(file, subfolder='uploads', prefix=''):
    """Save an uploaded file securely, return relative path."""
    from werkzeug.utils import secure_filename
    base = current_app.config.get('UPLOAD_FOLDER', '/tmp/uploads')
    folder = os.path.join(base, subfolder)
    os.makedirs(folder, exist_ok=True)
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'bin'
    filename = f"{prefix}{uuid.uuid4().hex}.{ext}"
    safe_name = secure_filename(filename)
    path = os.path.join(folder, safe_name)
    file.save(path)
    return os.path.join(subfolder, safe_name)


# ─── ID & Reference Generators ───────────────────────────────────────────────

def generate_uuid():
    return str(uuid.uuid4())


def generate_lease_number(property_ref, unit_number):
    ts = datetime.utcnow().strftime('%Y%m%d%H%M')
    return f"LSE-{property_ref}-{unit_number.upper()}-{ts}"


def generate_invoice_number(property_ref, year, month, seq):
    return f"INV-{property_ref}-{year}{month:02d}-{seq:04d}"


def generate_ticket_number(property_ref):
    ts = datetime.utcnow().strftime('%y%m%d%H%M%S')
    return f"TKT-{property_ref}-{ts}"


def generate_payment_reference(property_id, unit_number):
    """Unique bank/M-Pesa payment reference for a unit."""
    return f"NYM{property_id:04d}{unit_number.upper().replace(' ', '')}"


def generate_property_reference():
    """e.g. NYM-001"""
    from app.models.property import Property
    from app.extensions import db
    count = db.session.query(Property).count()
    return f"NYM-{count + 1:04d}"


# ─── Format helpers ───────────────────────────────────────────────────────────

def format_kes(amount):
    """Format amount as KSh 25,000.00"""
    try:
        return f"KSh {float(amount):,.2f}"
    except Exception:
        return "KSh 0.00"


def paginate_query(query, page, per_page=20):
    """Return pagination object."""
    per_page = min(per_page, current_app.config.get('MAX_ITEMS_PER_PAGE', 100))
    return query.paginate(page=page, per_page=per_page, error_out=False)
