"""
User model — all roles share this base.
Roles: super_admin, landlord, tenant, caretaker, agent
"""
from datetime import datetime
from flask_login import UserMixin
from app.extensions import db, bcrypt


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # Personal info
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    national_id = db.Column(db.String(20), unique=True, nullable=True)
    national_id_expiry = db.Column(db.Date, nullable=True)
    passport_number = db.Column(db.String(20), unique=True, nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(10), nullable=True)
    profile_photo = db.Column(db.String(500), nullable=True)

    # Role
    role = db.Column(
        db.Enum('super_admin', 'landlord', 'tenant', 'caretaker', 'agent', name='user_roles'),
        nullable=False,
        default='tenant'
    )
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    phone_verified = db.Column(db.Boolean, default=False, nullable=False)
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_secret = db.Column(db.String(32), nullable=True)

    # Account security
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    last_login_ip = db.Column(db.String(45), nullable=True)
    password_reset_token = db.Column(db.String(100), nullable=True)
    password_reset_expires = db.Column(db.DateTime, nullable=True)
    email_verification_token = db.Column(db.String(100), nullable=True)

    # Preferences
    theme_preference = db.Column(db.String(10), default='light')  # light or dark
    language = db.Column(db.String(5), default='en')
    timezone = db.Column(db.String(50), default='Africa/Nairobi')
    notification_sms = db.Column(db.Boolean, default=True)
    notification_email = db.Column(db.Boolean, default=True)
    notification_in_app = db.Column(db.Boolean, default=True)

    # Address
    county = db.Column(db.String(100), nullable=True)
    sub_county = db.Column(db.String(100), nullable=True)
    ward = db.Column(db.String(100), nullable=True)
    physical_address = db.Column(db.Text, nullable=True)

    # Diaspora flag
    is_diaspora = db.Column(db.Boolean, default=False)
    country_of_residence = db.Column(db.String(100), nullable=True)

    # Terms
    terms_accepted = db.Column(db.Boolean, default=False)
    terms_accepted_at = db.Column(db.DateTime, nullable=True)
    privacy_accepted = db.Column(db.Boolean, default=False)
    privacy_accepted_at = db.Column(db.DateTime, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    visitor_logs = db.relationship('VisitorLog', backref='user', lazy='dynamic')
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic', foreign_keys='AuditLog.user_id')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic')
    sent_messages = db.relationship('Message', backref='sender', lazy='dynamic', foreign_keys='Message.sender_id')

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def is_locked(self):
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def display_role(self):
        roles = {
            'super_admin': 'Super Administrator',
            'landlord': 'Property Owner',
            'tenant': 'Tenant',
            'caretaker': 'Caretaker',
            'agent': 'Property Agent',
        }
        return roles.get(self.role, self.role.title())

    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'email': self.email,
            'phone': self.phone,
            'full_name': self.full_name,
            'role': self.role,
            'is_active': self.is_active,
            'is_verified': self.is_verified,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<User {self.email} [{self.role}]>'


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50), nullable=True)
    resource_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='success')  # success, failure, error
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f'<AuditLog {self.action} by user {self.user_id}>'
