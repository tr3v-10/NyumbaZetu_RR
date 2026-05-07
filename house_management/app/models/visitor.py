"""
Visitor tracking, notifications, announcements, messages — forensic and comms layer.
"""
from datetime import datetime
from app.extensions import db


class VisitorLog(db.Model):
    """
    Forensic log of every site visitor — IP, MAC (if available via headers),
    user-agent, geolocation, referrer, etc.
    Available to super admin only.
    """
    __tablename__ = 'visitor_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    session_id = db.Column(db.String(100), nullable=True, index=True)

    # Network identifiers
    ip_address = db.Column(db.String(45), nullable=True, index=True)
    forwarded_for = db.Column(db.String(200), nullable=True)
    real_ip = db.Column(db.String(45), nullable=True)
    cf_connecting_ip = db.Column(db.String(45), nullable=True)
    x_forwarded_for = db.Column(db.String(200), nullable=True)

    # MAC address — available only when X-Device-Mac or similar header is sent
    # (note: browsers can't expose MAC; this captures it only when app is used
    #  via native mobile app that injects the header, or via internal networks)
    mac_address = db.Column(db.String(20), nullable=True)
    device_fingerprint = db.Column(db.String(255), nullable=True)

    # Browser/Device
    user_agent = db.Column(db.Text, nullable=True)
    browser = db.Column(db.String(100), nullable=True)
    browser_version = db.Column(db.String(50), nullable=True)
    os = db.Column(db.String(100), nullable=True)
    os_version = db.Column(db.String(50), nullable=True)
    device_type = db.Column(db.String(20), nullable=True)  # mobile, desktop, tablet, bot
    device_brand = db.Column(db.String(100), nullable=True)
    device_model = db.Column(db.String(100), nullable=True)
    is_mobile = db.Column(db.Boolean, default=False)
    is_bot = db.Column(db.Boolean, default=False)

    # Geolocation (from GeoIP)
    country = db.Column(db.String(100), nullable=True)
    country_code = db.Column(db.String(5), nullable=True)
    region = db.Column(db.String(100), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    latitude = db.Column(db.Numeric(10, 8), nullable=True)
    longitude = db.Column(db.Numeric(11, 8), nullable=True)
    timezone = db.Column(db.String(50), nullable=True)
    isp = db.Column(db.String(200), nullable=True)
    organization = db.Column(db.String(200), nullable=True)

    # Request details
    method = db.Column(db.String(10), nullable=True)
    path = db.Column(db.Text, nullable=True)
    query_string = db.Column(db.Text, nullable=True)
    referrer = db.Column(db.Text, nullable=True)
    origin = db.Column(db.String(255), nullable=True)
    host = db.Column(db.String(255), nullable=True)
    accept_language = db.Column(db.String(255), nullable=True)
    accept_encoding = db.Column(db.String(255), nullable=True)
    content_type = db.Column(db.String(100), nullable=True)
    response_status = db.Column(db.Integer, nullable=True)
    response_time_ms = db.Column(db.Integer, nullable=True)

    # Screen (injected via JS in the frontend)
    screen_width = db.Column(db.Integer, nullable=True)
    screen_height = db.Column(db.Integer, nullable=True)
    color_depth = db.Column(db.Integer, nullable=True)
    pixel_ratio = db.Column(db.Numeric(5, 2), nullable=True)
    timezone_offset = db.Column(db.Integer, nullable=True)
    language = db.Column(db.String(20), nullable=True)
    platform = db.Column(db.String(100), nullable=True)
    do_not_track = db.Column(db.String(5), nullable=True)
    cookie_enabled = db.Column(db.Boolean, nullable=True)
    java_enabled = db.Column(db.Boolean, nullable=True)

    # Additional headers captured
    all_headers = db.Column(db.JSON, nullable=True)

    # Flags
    is_suspicious = db.Column(db.Boolean, default=False)
    suspicious_reason = db.Column(db.String(255), nullable=True)

    visited_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f'<VisitorLog {self.ip_address} {self.visited_at}>'


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)  # payment, maintenance, lease, system, announcement
    resource_type = db.Column(db.String(50), nullable=True)
    resource_id = db.Column(db.Integer, nullable=True)
    action_url = db.Column(db.String(500), nullable=True)
    is_read = db.Column(db.Boolean, default=False, index=True)
    read_at = db.Column(db.DateTime, nullable=True)
    is_sms_sent = db.Column(db.Boolean, default=False)
    sms_sent_at = db.Column(db.DateTime, nullable=True)
    is_email_sent = db.Column(db.Boolean, default=False)
    email_sent_at = db.Column(db.DateTime, nullable=True)
    priority = db.Column(db.String(10), default='normal')  # low, normal, high, critical
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f'<Notification {self.notification_type} for user {self.user_id}>'


class Announcement(db.Model):
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    announcement_type = db.Column(db.String(50), nullable=False)  # maintenance, utility, general, emergency
    target_audience = db.Column(db.String(20), default='all')  # all, tenants, caretakers
    send_sms = db.Column(db.Boolean, default=False)
    send_email = db.Column(db.Boolean, default=False)
    send_in_app = db.Column(db.Boolean, default=True)
    sms_sent = db.Column(db.Boolean, default=False)
    sms_sent_count = db.Column(db.Integer, default=0)
    is_pinned = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    created_by = db.relationship('User', foreign_keys=[created_by_id])


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=True)
    subject = db.Column(db.String(255), nullable=True)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime, nullable=True)
    parent_message_id = db.Column(db.Integer, db.ForeignKey('messages.id'), nullable=True)
    attachment_path = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='received_messages')
    replies = db.relationship('Message', backref=db.backref('parent', remote_side=[id]))


class SMSLog(db.Model):
    __tablename__ = 'sms_logs'

    id = db.Column(db.Integer, primary_key=True)
    recipient_phone = db.Column(db.String(20), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    message = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(50), nullable=False)  # rent_reminder, payment_receipt, maintenance, announcement
    gateway_response = db.Column(db.JSON, nullable=True)
    message_id = db.Column(db.String(100), nullable=True)  # Africa's Talking message ID
    status = db.Column(db.String(20), default='pending')  # pending, sent, delivered, failed
    cost = db.Column(db.Numeric(8, 4), nullable=True)  # Cost in USD
    sent_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
