"""
Authentication blueprint — login, logout, register, password reset, email verification.
"""
import uuid
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db, bcrypt, limiter
from app.models.user import User
from app.models.visitor import Notification
from app.utils import log_visitor, log_audit, generate_uuid

auth_bp = Blueprint('auth', __name__, url_prefix='/auth', template_folder='templates')


@auth_bp.before_request
def track_visitor():
    log_visitor()


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("20 per minute;100 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(_get_dashboard_url(current_user.role))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter_by(email=email, deleted_at=None).first()

        if not user:
            log_audit('login_failed', details={'email': email, 'reason': 'user_not_found'}, status='failure')
            flash('Invalid email or password.', 'danger')
            return render_template('auth/login.html')

        if user.is_locked():
            flash(f'Account locked until {user.locked_until.strftime("%H:%M %d/%m/%Y")}. Contact support.', 'danger')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('Your account has been deactivated. Contact support.', 'danger')
            return render_template('auth/login.html')

        if not user.check_password(password):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=30)
                flash('Too many failed attempts. Account locked for 30 minutes.', 'danger')
            else:
                remaining = 5 - user.failed_login_attempts
                flash(f'Invalid password. {remaining} attempt(s) remaining.', 'danger')
            db.session.commit()
            log_audit('login_failed', details={'email': email, 'attempts': user.failed_login_attempts}, status='failure')
            return render_template('auth/login.html')

        # Successful login
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = datetime.utcnow()
        user.last_login_ip = request.remote_addr
        db.session.commit()

        login_user(user, remember=remember)
        log_audit('login', resource_type='user', resource_id=user.id)

        next_page = request.args.get('next')
        if next_page and next_page.startswith('/'):
            return redirect(next_page)
        return redirect(_get_dashboard_url(user.role))

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(_get_dashboard_url(current_user.role))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', 'tenant')
        terms = request.form.get('terms')
        privacy = request.form.get('privacy')

        errors = []
        if not all([email, first_name, last_name, password]):
            errors.append('All required fields must be filled.')
        if len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        if password != confirm_password:
            errors.append('Passwords do not match.')
        if not terms:
            errors.append('You must accept the Terms of Service.')
        if not privacy:
            errors.append('You must accept the Privacy Policy.')
        if role not in ('landlord', 'tenant', 'caretaker', 'agent'):
            errors.append('Invalid role selected.')
        if User.query.filter_by(email=email).first():
            errors.append('Email already registered.')
        if phone and User.query.filter_by(phone=phone).first():
            errors.append('Phone number already registered.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('auth/register.html')

        user = User(
            uuid=generate_uuid(),
            email=email,
            phone=phone or None,
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=True,
            terms_accepted=True,
            terms_accepted_at=datetime.utcnow(),
            privacy_accepted=True,
            privacy_accepted_at=datetime.utcnow(),
            email_verification_token=uuid.uuid4().hex,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        log_audit('register', resource_type='user', resource_id=user.id)
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    log_audit('logout', resource_type='user', resource_id=current_user.id)
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email, deleted_at=None).first()
        if user:
            token = uuid.uuid4().hex
            user.password_reset_token = token
            user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            # In production: send email with reset link
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            current_app.logger.info(f"Password reset URL for {email}: {reset_url}")
        flash('If that email exists, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(password_reset_token=token).first()
    if not user or not user.password_reset_expires or user.password_reset_expires < datetime.utcnow():
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
        elif password != confirm:
            flash('Passwords do not match.', 'danger')
        else:
            user.set_password(password)
            user.password_reset_token = None
            user.password_reset_expires = None
            user.failed_login_attempts = 0
            user.locked_until = None
            db.session.commit()
            log_audit('password_reset', resource_type='user', resource_id=user.id)
            flash('Password reset successfully. Please log in.', 'success')
            return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', token=token)


def _get_dashboard_url(role):
    urls = {
        'super_admin': 'super_admin.dashboard',
        'landlord': 'landlord.dashboard',
        'tenant': 'tenant.dashboard',
        'caretaker': 'caretaker.dashboard',
        'agent': 'agent.dashboard',
    }
    return url_for(urls.get(role, 'auth.login'))
