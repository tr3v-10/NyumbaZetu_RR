"""
Maintenance requests, work orders, inspections, and purchase requests.
"""
from datetime import datetime
from app.extensions import db


class MaintenanceRequest(db.Model):
    __tablename__ = 'maintenance_requests'

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    ticket_number = db.Column(db.String(20), unique=True, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(
        db.Enum('plumbing', 'electrical', 'carpentry', 'painting', 'hvac',
                'appliance', 'pest_control', 'cleaning', 'structural', 'security', 'other',
                name='maintenance_categories'),
        nullable=False
    )
    urgency = db.Column(
        db.Enum('emergency', 'urgent', 'routine', name='urgency_levels'),
        default='routine',
        nullable=False,
        index=True
    )
    status = db.Column(
        db.Enum('submitted', 'acknowledged', 'assigned', 'in_progress',
                'awaiting_parts', 'awaiting_approval', 'completed', 'closed', 'cancelled',
                name='maintenance_statuses'),
        default='submitted',
        index=True
    )

    # Cost tracking
    estimated_cost = db.Column(db.Numeric(12, 2), nullable=True)
    actual_cost = db.Column(db.Numeric(12, 2), nullable=True)
    cost_approved = db.Column(db.Boolean, default=False)
    cost_approval_threshold = db.Column(db.Numeric(12, 2), default=3000)
    requires_approval = db.Column(db.Boolean, default=False)

    # Timeline
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    assigned_at = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    target_resolution_date = db.Column(db.DateTime, nullable=True)

    # Resolution
    resolution_notes = db.Column(db.Text, nullable=True)
    tenant_rating = db.Column(db.Integer, nullable=True)  # 1-5
    tenant_feedback = db.Column(db.Text, nullable=True)
    rated_at = db.Column(db.DateTime, nullable=True)

    # Flags
    is_warranty_issue = db.Column(db.Boolean, default=False)
    affects_multiple_units = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenant = db.relationship('User', foreign_keys=[tenant_id], backref='maintenance_requests')
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])
    photos = db.relationship('MaintenancePhoto', backref='request', lazy='dynamic', cascade='all, delete-orphan')
    status_history = db.relationship('MaintenanceStatusHistory', backref='request', lazy='dynamic')
    purchase_requests = db.relationship('PurchaseRequest', backref='maintenance_request', lazy='dynamic')
    messages = db.relationship('MaintenanceMessage', backref='request', lazy='dynamic')

    def __repr__(self):
        return f'<MaintenanceRequest {self.ticket_number}>'


class MaintenancePhoto(db.Model):
    __tablename__ = 'maintenance_photos'

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('maintenance_requests.id'), nullable=False, index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(10), default='image')  # image, video
    caption = db.Column(db.String(255), nullable=True)
    phase = db.Column(db.String(20), default='before')  # before, during, after
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])


class MaintenanceStatusHistory(db.Model):
    __tablename__ = 'maintenance_status_history'

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('maintenance_requests.id'), nullable=False, index=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    old_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    changed_by = db.relationship('User', foreign_keys=[changed_by_id])


class MaintenanceMessage(db.Model):
    __tablename__ = 'maintenance_messages'

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('maintenance_requests.id'), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime, nullable=True)
    attachment_path = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id])


class PurchaseRequest(db.Model):
    __tablename__ = 'purchase_requests'

    id = db.Column(db.Integer, primary_key=True)
    maintenance_request_id = db.Column(db.Integer, db.ForeignKey('maintenance_requests.id'), nullable=False, index=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    item_description = db.Column(db.Text, nullable=False)
    estimated_cost = db.Column(db.Numeric(12, 2), nullable=False)
    actual_cost = db.Column(db.Numeric(12, 2), nullable=True)
    vendor_name = db.Column(db.String(200), nullable=True)
    vendor_phone = db.Column(db.String(20), nullable=True)
    purchase_method = db.Column(db.String(30), nullable=True)  # mpesa, cash, cheque
    receipt_path = db.Column(db.String(500), nullable=True)
    mpesa_receipt = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, purchased
    approval_notes = db.Column(db.Text, nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    purchased_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    requested_by = db.relationship('User', foreign_keys=[requested_by_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])


class Inspection(db.Model):
    __tablename__ = 'inspections'

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=True)
    conducted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    inspection_type = db.Column(db.String(50), nullable=False)  # routine, move_in, move_out, emergency
    scheduled_date = db.Column(db.Date, nullable=False)
    actual_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default='scheduled')  # scheduled, completed, cancelled
    notes = db.Column(db.Text, nullable=True)
    report_path = db.Column(db.String(500), nullable=True)

    # Checklist items
    boiler_pressure_ok = db.Column(db.Boolean, nullable=True)
    fire_extinguisher_ok = db.Column(db.Boolean, nullable=True)
    common_area_clean = db.Column(db.Boolean, nullable=True)
    security_lights_ok = db.Column(db.Boolean, nullable=True)
    water_pressure_ok = db.Column(db.Boolean, nullable=True)
    drainage_ok = db.Column(db.Boolean, nullable=True)
    general_condition = db.Column(db.String(20), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conducted_by = db.relationship('User', foreign_keys=[conducted_by_id])
