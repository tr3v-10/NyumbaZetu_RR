"""
Tenant profiles, leases, deposits, and documents.
"""
from datetime import datetime, date
from app.extensions import db


class TenantProfile(db.Model):
    __tablename__ = 'tenant_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    emergency_contact_name = db.Column(db.String(200), nullable=True)
    emergency_contact_phone = db.Column(db.String(20), nullable=True)
    emergency_contact_relationship = db.Column(db.String(50), nullable=True)
    employer_name = db.Column(db.String(200), nullable=True)
    employer_address = db.Column(db.Text, nullable=True)
    employer_phone = db.Column(db.String(20), nullable=True)
    monthly_income = db.Column(db.Numeric(14, 2), nullable=True)
    next_of_kin_name = db.Column(db.String(200), nullable=True)
    next_of_kin_phone = db.Column(db.String(20), nullable=True)
    next_of_kin_relationship = db.Column(db.String(50), nullable=True)
    crb_score = db.Column(db.Integer, nullable=True)
    crb_checked_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('tenant_profile', uselist=False))


class Lease(db.Model):
    __tablename__ = 'leases'

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    landlord_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    lease_number = db.Column(db.String(50), unique=True, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    actual_end_date = db.Column(db.Date, nullable=True)
    notice_period_days = db.Column(db.Integer, default=30)
    rent_amount = db.Column(db.Numeric(12, 2), nullable=False)
    deposit_amount = db.Column(db.Numeric(12, 2), nullable=False)
    deposit_paid = db.Column(db.Numeric(12, 2), default=0)
    deposit_returned = db.Column(db.Numeric(12, 2), default=0)
    deposit_deductions = db.Column(db.Numeric(12, 2), default=0)
    deposit_deduction_reason = db.Column(db.Text, nullable=True)

    # Charges at time of signing
    service_charge = db.Column(db.Numeric(10, 2), default=0)
    water_charge = db.Column(db.Numeric(10, 2), default=0)
    garbage_charge = db.Column(db.Numeric(10, 2), default=0)

    status = db.Column(
        db.Enum('draft', 'active', 'expired', 'terminated', 'renewed', name='lease_statuses'),
        default='draft',
        nullable=False,
        index=True
    )
    termination_reason = db.Column(db.Text, nullable=True)
    terminated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Lease document
    lease_document_path = db.Column(db.String(500), nullable=True)
    tenant_signed = db.Column(db.Boolean, default=False)
    tenant_signed_at = db.Column(db.DateTime, nullable=True)
    landlord_signed = db.Column(db.Boolean, default=False)
    landlord_signed_at = db.Column(db.DateTime, nullable=True)
    digital_signature_tenant = db.Column(db.Text, nullable=True)
    digital_signature_landlord = db.Column(db.Text, nullable=True)

    # Renewal
    renewal_offered = db.Column(db.Boolean, default=False)
    renewal_offered_at = db.Column(db.DateTime, nullable=True)
    renewal_accepted = db.Column(db.Boolean, nullable=True)
    renewal_response_at = db.Column(db.DateTime, nullable=True)
    parent_lease_id = db.Column(db.Integer, db.ForeignKey('leases.id'), nullable=True)

    # Special conditions
    special_conditions = db.Column(db.Text, nullable=True)
    pets_allowed = db.Column(db.Boolean, default=False)
    subletting_allowed = db.Column(db.Boolean, default=False)
    number_of_occupants = db.Column(db.Integer, default=1)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenant = db.relationship('User', foreign_keys=[tenant_id], backref='leases')
    landlord = db.relationship('User', foreign_keys=[landlord_id])
    agent = db.relationship('User', foreign_keys=[agent_id])
    terminated_by = db.relationship('User', foreign_keys=[terminated_by_id])
    invoices = db.relationship('Invoice', backref='lease', lazy='dynamic')
    tenant_documents = db.relationship('TenantDocument', backref='lease', lazy='dynamic')
    inventory_items = db.relationship('InventoryItem', backref='lease', lazy='dynamic')

    @property
    def is_expired(self):
        return date.today() > self.end_date

    @property
    def days_remaining(self):
        if self.status == 'active':
            delta = self.end_date - date.today()
            return delta.days
        return 0

    @property
    def total_monthly_rent(self):
        return float(
            (self.rent_amount or 0) +
            (self.service_charge or 0) +
            (self.water_charge or 0) +
            (self.garbage_charge or 0)
        )

    def __repr__(self):
        return f'<Lease {self.lease_number}>'


class TenantDocument(db.Model):
    __tablename__ = 'tenant_documents'

    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey('leases.id'), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    doc_type = db.Column(db.String(50), nullable=False)  # national_id, passport, kra_pin, payslip
    title = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    verified_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tenant = db.relationship('User', foreign_keys=[tenant_id])
    verified_by = db.relationship('User', foreign_keys=[verified_by_id])


class InventoryItem(db.Model):
    __tablename__ = 'inventory_items'

    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey('leases.id'), nullable=False, index=True)
    item_name = db.Column(db.String(255), nullable=False)
    condition_checkin = db.Column(db.String(50), nullable=False)  # excellent, good, fair, poor
    condition_checkout = db.Column(db.String(50), nullable=True)
    notes_checkin = db.Column(db.Text, nullable=True)
    notes_checkout = db.Column(db.Text, nullable=True)
    photo_checkin = db.Column(db.String(500), nullable=True)
    photo_checkout = db.Column(db.String(500), nullable=True)
    deduction_amount = db.Column(db.Numeric(10, 2), default=0)
    checkin_date = db.Column(db.Date, nullable=False)
    checkout_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
