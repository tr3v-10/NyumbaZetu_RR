"""
Super Admin Blueprint — full system access, forensic data, all stats.
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, abort
from flask.views import MethodView
from flask_login import login_required, current_user
from app.extensions import db, cache, limiter
from app.utils import super_admin_required, log_audit, paginate_query
from app.models.user import User, AuditLog
from app.models.property import Property, Unit
from app.models.payment import Invoice, Payment, Expense
from app.models.maintenance import MaintenanceRequest
from app.models.visitor import VisitorLog, Notification, Announcement, SMSLog
from app.models.tenant import Lease
from app.services.sms_bank_analytics import analytics_service
from datetime import datetime, date

super_admin_bp = Blueprint('super_admin', __name__, url_prefix='/admin', template_folder='templates')


def _require_super_admin():
    if not current_user.is_authenticated or current_user.role != 'super_admin':
        abort(403)


@super_admin_bp.before_request
@login_required
def before_request():
    _require_super_admin()


# ─── Dashboard ────────────────────────────────────────────────────────────────

@super_admin_bp.route('/dashboard')
@cache.cached(timeout=60, key_prefix='super_admin_dashboard')
def dashboard():
    stats = analytics_service.get_super_admin_dashboard()
    recent_users = User.query.filter_by(deleted_at=None).order_by(User.created_at.desc()).limit(10).all()
    recent_payments = Payment.query.filter_by(status='completed').order_by(Payment.created_at.desc()).limit(10).all()
    recent_visitors = VisitorLog.query.order_by(VisitorLog.visited_at.desc()).limit(20).all()
    return render_template(
        'super_admin/dashboard.html',
        stats=stats,
        recent_users=recent_users,
        recent_payments=recent_payments,
        recent_visitors=recent_visitors,
    )


# ─── User Management ─────────────────────────────────────────────────────────

class UserListView(MethodView):
    decorators = [login_required]

    def get(self):
        page = request.args.get('page', 1, type=int)
        role = request.args.get('role', '')
        search = request.args.get('search', '')
        status = request.args.get('status', '')

        q = User.query.filter_by(deleted_at=None)
        if role:
            q = q.filter_by(role=role)
        if search:
            q = q.filter(
                (User.email.ilike(f'%{search}%')) |
                (User.first_name.ilike(f'%{search}%')) |
                (User.last_name.ilike(f'%{search}%')) |
                (User.phone.ilike(f'%{search}%'))
            )
        if status == 'active':
            q = q.filter_by(is_active=True)
        elif status == 'inactive':
            q = q.filter_by(is_active=False)

        pagination = paginate_query(q.order_by(User.created_at.desc()), page)
        return render_template('super_admin/users/list.html', pagination=pagination, role=role, search=search)

    def post(self):
        """Toggle user active status or delete."""
        user_id = request.form.get('user_id', type=int)
        action = request.form.get('action')
        user = User.query.get_or_404(user_id)

        if action == 'toggle_active':
            user.is_active = not user.is_active
            db.session.commit()
            log_audit('toggle_user_active', 'user', user.id, {'active': user.is_active})
            flash(f'User {"activated" if user.is_active else "deactivated"}.', 'success')
        elif action == 'delete':
            if user.role == 'super_admin':
                flash('Cannot delete super admin.', 'danger')
            else:
                user.deleted_at = datetime.utcnow()
                db.session.commit()
                log_audit('delete_user', 'user', user.id)
                flash('User deleted.', 'success')
        return redirect(url_for('super_admin.users'))


class UserDetailView(MethodView):
    decorators = [login_required]

    def get(self, user_id):
        user = User.query.get_or_404(user_id)
        visitor_logs = VisitorLog.query.filter_by(user_id=user_id).order_by(VisitorLog.visited_at.desc()).limit(50).all()
        audit_logs = AuditLog.query.filter_by(user_id=user_id).order_by(AuditLog.created_at.desc()).limit(50).all()
        return render_template('super_admin/users/detail.html', user=user, visitor_logs=visitor_logs, audit_logs=audit_logs)

    def post(self, user_id):
        user = User.query.get_or_404(user_id)
        field = request.form.get('field')
        value = request.form.get('value')
        if field in ('is_active', 'is_verified', 'role'):
            setattr(user, field, value if field == 'role' else value == 'true')
            db.session.commit()
            log_audit('update_user', 'user', user_id, {field: value})
            flash('User updated.', 'success')
        return redirect(url_for('super_admin.user_detail', user_id=user_id))


super_admin_bp.add_url_rule('/users', view_func=UserListView.as_view('users'))
super_admin_bp.add_url_rule('/users/<int:user_id>', view_func=UserDetailView.as_view('user_detail'))


# ─── Visitor Logs (Forensic) ──────────────────────────────────────────────────

@super_admin_bp.route('/visitors')
def visitors():
    page = request.args.get('page', 1, type=int)
    ip_filter = request.args.get('ip', '')
    country_filter = request.args.get('country', '')

    q = VisitorLog.query
    if ip_filter:
        q = q.filter(VisitorLog.ip_address.ilike(f'%{ip_filter}%'))
    if country_filter:
        q = q.filter(VisitorLog.country.ilike(f'%{country_filter}%'))
    pagination = paginate_query(q.order_by(VisitorLog.visited_at.desc()), page)

    # Stats
    unique_ips = db.session.query(VisitorLog.ip_address).distinct().count()
    unique_countries = db.session.query(VisitorLog.country).distinct().count()
    bot_count = VisitorLog.query.filter_by(is_bot=True).count()

    return render_template(
        'super_admin/visitors.html',
        pagination=pagination,
        unique_ips=unique_ips,
        unique_countries=unique_countries,
        bot_count=bot_count,
        ip_filter=ip_filter,
        country_filter=country_filter,
    )


@super_admin_bp.route('/visitors/<int:log_id>')
def visitor_detail(log_id):
    log = VisitorLog.query.get_or_404(log_id)
    same_ip = VisitorLog.query.filter_by(ip_address=log.ip_address).order_by(
        VisitorLog.visited_at.desc()
    ).limit(20).all()
    return render_template('super_admin/visitor_detail.html', log=log, same_ip=same_ip)


# ─── Audit Logs ───────────────────────────────────────────────────────────────

@super_admin_bp.route('/audit-logs')
def audit_logs():
    page = request.args.get('page', 1, type=int)
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action', '')

    q = AuditLog.query
    if user_id:
        q = q.filter_by(user_id=user_id)
    if action:
        q = q.filter(AuditLog.action.ilike(f'%{action}%'))
    pagination = paginate_query(q.order_by(AuditLog.created_at.desc()), page)
    return render_template('super_admin/audit_logs.html', pagination=pagination)


# ─── Properties Overview ──────────────────────────────────────────────────────

@super_admin_bp.route('/properties')
def properties():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    q = Property.query.filter_by(is_active=True)
    if search:
        q = q.filter(
            (Property.name.ilike(f'%{search}%')) |
            (Property.property_reference.ilike(f'%{search}%')) |
            (Property.county.ilike(f'%{search}%'))
        )
    pagination = paginate_query(q.order_by(Property.created_at.desc()), page)
    return render_template('super_admin/properties.html', pagination=pagination, search=search)


# ─── Financial Overview ───────────────────────────────────────────────────────

@super_admin_bp.route('/financials')
def financials():
    year = request.args.get('year', date.today().year, type=int)
    from sqlalchemy import func, extract
    monthly_revenue = []
    for m in range(1, 13):
        rev = db.session.query(func.sum(Payment.amount)).filter(
            Payment.status == 'completed',
            extract('year', Payment.payment_date) == year,
            extract('month', Payment.payment_date) == m,
        ).scalar() or 0
        monthly_revenue.append({'month': m, 'revenue': float(rev)})

    total_year = sum(m['revenue'] for m in monthly_revenue)
    payment_methods = db.session.query(
        Payment.payment_method, func.sum(Payment.amount), func.count(Payment.id)
    ).filter(
        Payment.status == 'completed',
        extract('year', Payment.payment_date) == year,
    ).group_by(Payment.payment_method).all()

    recent_payments = Payment.query.filter_by(status='completed').order_by(Payment.created_at.desc()).limit(20).all()
    return render_template(
        'super_admin/financials.html',
        monthly_revenue=monthly_revenue,
        total_year=total_year,
        payment_methods=payment_methods,
        recent_payments=recent_payments,
        year=year,
    )


# ─── Announcements / Broadcast ────────────────────────────────────────────────

@super_admin_bp.route('/announcements', methods=['GET', 'POST'])
def announcements():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        message = request.form.get('message', '').strip()
        send_sms = request.form.get('send_sms') == 'on'
        if title and message:
            ann = Announcement(
                created_by_id=current_user.id,
                title=title,
                message=message,
                announcement_type='general',
                send_sms=send_sms,
                send_in_app=True,
            )
            db.session.add(ann)

            # Notify all active users
            users = User.query.filter_by(is_active=True, deleted_at=None).all()
            for u in users:
                notif = Notification(
                    user_id=u.id,
                    title=title,
                    message=message,
                    notification_type='announcement',
                    priority='normal',
                )
                db.session.add(notif)

                if send_sms and u.phone:
                    from app.services.sms_bank_analytics import sms_service
                    sms_service.send_broadcast([u.phone], title, message)

            db.session.commit()
            log_audit('broadcast_announcement', 'announcement', ann.id)
            flash('Announcement sent to all users.', 'success')

    page = request.args.get('page', 1, type=int)
    pagination = paginate_query(Announcement.query.order_by(Announcement.created_at.desc()), page)
    return render_template('super_admin/announcements.html', pagination=pagination)


# ─── Settings ─────────────────────────────────────────────────────────────────

@super_admin_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        flash('Settings updated.', 'success')
        log_audit('update_settings')
    return render_template('super_admin/settings.html')


# ─── SMS Logs ─────────────────────────────────────────────────────────────────

@super_admin_bp.route('/sms-logs')
def sms_logs():
    page = request.args.get('page', 1, type=int)
    pagination = paginate_query(SMSLog.query.order_by(SMSLog.created_at.desc()), page)
    return render_template('super_admin/sms_logs.html', pagination=pagination)


# ─── Create Super Admin ───────────────────────────────────────────────────────

@super_admin_bp.route('/create-admin', methods=['POST'])
def create_admin():
    """Allow super admin to create another super admin or promote a user."""
    user_id = request.form.get('user_id', type=int)
    if user_id:
        user = User.query.get_or_404(user_id)
        user.role = 'super_admin'
        db.session.commit()
        log_audit('promote_to_super_admin', 'user', user_id)
        flash(f'{user.full_name} promoted to Super Admin.', 'success')
    return redirect(url_for('super_admin.users'))
