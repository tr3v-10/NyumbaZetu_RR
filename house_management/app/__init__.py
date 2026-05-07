"""
NyumbaManager Application Factory
Kenya-focused House Management System
"""
import logging
from flask import Flask, render_template, request, g
from flask_login import current_user
from app.config import config
from app.extensions import db, migrate, login_manager, bcrypt, cache, mail, csrf, socketio, limiter


def create_app(config_name='default'):
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.config.from_object(config[config_name])

    # ─── Extensions ───────────────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    cache.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    socketio.init_app(app, async_mode='eventlet', cors_allowed_origins='*')

    try:
        limiter.init_app(app)
        limiter.storage_uri = app.config.get('RATELIMIT_STORAGE_URL', 'memory://')
    except Exception:
        pass

    # ─── Services ─────────────────────────────────────────────────────────────
    from app.services.mpesa import mpesa_service
    from app.services.sms_bank_analytics import sms_service, bank_service, analytics_service
    mpesa_service.init_app(app)
    sms_service.init_app(app)
    bank_service.init_app(app)

    # ─── User loader ──────────────────────────────────────────────────────────
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ─── Blueprints ───────────────────────────────────────────────────────────
    from app.blueprints.auth.routes import auth_bp
    from app.blueprints.super_admin.routes import super_admin_bp
    from app.blueprints.landlord.routes import landlord_bp
    from app.blueprints.tenant.routes import tenant_bp, caretaker_bp, agent_bp
    from app.blueprints.api.routes import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(super_admin_bp)
    app.register_blueprint(landlord_bp)
    app.register_blueprint(tenant_bp)
    app.register_blueprint(caretaker_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(api_bp)

    # ─── Policies Blueprint ───────────────────────────────────────────────────
    from app.blueprints.auth.routes import auth_bp  # reuse for policies prefix
    register_policy_routes(app)

    # ─── Security headers ─────────────────────────────────────────────────────
    @app.after_request
    def add_security_headers(response):
        for header, value in app.config.get('SECURITY_HEADERS', {}).items():
            response.headers[header] = value
        return response

    # ─── Visitor tracking on every request ───────────────────────────────────
    @app.before_request
    def track_all_visitors():
        from app.utils import log_visitor
        # Skip static files and health check
        if (request.path.startswith('/static') or
                request.path.startswith('/api/health') or
                request.path.startswith('/api/fingerprint') or
                request.method == 'OPTIONS'):
            return
        try:
            uid = current_user.id if current_user and current_user.is_authenticated else None
            log_visitor(uid)
        except Exception:
            pass

    # ─── Context processors ───────────────────────────────────────────────────
    @app.context_processor
    def inject_globals():
        from app.models.visitor import Notification
        unread_count = 0
        if current_user and current_user.is_authenticated:
            try:
                unread_count = Notification.query.filter_by(
                    user_id=current_user.id, is_read=False
                ).count()
            except Exception:
                pass
        return {
            'app_name': app.config.get('APP_NAME', 'NyumbaManager'),
            'currency_symbol': app.config.get('CURRENCY_SYMBOL', 'KSh'),
            'unread_notifications': unread_count,
        }

    # ─── Template filters ─────────────────────────────────────────────────────
    @app.template_filter('kes')
    def kes_format(value):
        try:
            return f"KSh {float(value):,.2f}"
        except Exception:
            return "KSh 0.00"

    @app.template_filter('month_name')
    def month_name_filter(month_num):
        from calendar import month_name as mn
        try:
            return mn[int(month_num)]
        except Exception:
            return str(month_num)

    # ─── Error handlers ───────────────────────────────────────────────────────
    @app.errorhandler(400)
    def bad_request(e):
        return render_template('errors/400.html'), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return render_template('errors/401.html'), 401

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return render_template('errors/429.html'), 429

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    # ─── Root redirect ────────────────────────────────────────────────────────
    @app.route('/')
    def index():
        from flask import redirect, url_for
        if current_user and current_user.is_authenticated:
            role_map = {
                'super_admin': 'super_admin.dashboard',
                'landlord': 'landlord.dashboard',
                'tenant': 'tenant.dashboard',
                'caretaker': 'caretaker.dashboard',
                'agent': 'agent.dashboard',
            }
            return redirect(url_for(role_map.get(current_user.role, 'auth.login')))
        return redirect(url_for('auth.login'))

    # ─── Logging ──────────────────────────────────────────────────────────────
    if not app.debug:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(levelname)s %(name)s: %(message)s'
        )

    return app


def register_policy_routes(app):
    """Register policy pages (privacy, terms, usage, etc.)."""
    from flask import Blueprint, render_template as rt
    policy_bp = Blueprint('policies', __name__, url_prefix='/policies')

    @policy_bp.route('/privacy')
    def privacy():
        return rt('policies/privacy.html')

    @policy_bp.route('/terms')
    def terms():
        return rt('policies/terms.html')

    @policy_bp.route('/usage')
    def usage():
        return rt('policies/usage.html')

    @policy_bp.route('/data-protection')
    def data_protection():
        return rt('policies/data_protection.html')

    @policy_bp.route('/cookie-policy')
    def cookie_policy():
        return rt('policies/cookie_policy.html')

    @policy_bp.route('/acceptable-use')
    def acceptable_use():
        return rt('policies/acceptable_use.html')

    @policy_bp.route('/refund-policy')
    def refund_policy():
        return rt('policies/refund_policy.html')

    @policy_bp.route('/sla')
    def sla():
        return rt('policies/sla.html')

    app.register_blueprint(policy_bp)
