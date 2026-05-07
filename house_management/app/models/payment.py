"""
Invoices, payments, reconciliation — the financial engine.
No wallet held; app is a reconciliation/tracking layer only.
"""
from datetime import datetime, date
from app.extensions import db


class Invoice(db.Model):
    __tablename__ = 'invoices'

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    lease_id = db.Column(db.Integer, db.ForeignKey('leases.id'), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=False, index=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)

    invoice_number = db.Column(db.String(50), unique=True, nullable=False)  # INV-2024-001
    billing_period_start = db.Column(db.Date, nullable=False)
    billing_period_end = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    issue_date = db.Column(db.Date, nullable=False, default=date.today)

    # Line items
    rent_amount = db.Column(db.Numeric(12, 2), default=0)
    service_charge = db.Column(db.Numeric(10, 2), default=0)
    water_charge = db.Column(db.Numeric(10, 2), default=0)
    electricity_charge = db.Column(db.Numeric(10, 2), default=0)
    garbage_charge = db.Column(db.Numeric(10, 2), default=0)
    caretaker_charge = db.Column(db.Numeric(10, 2), default=0)
    late_fee = db.Column(db.Numeric(10, 2), default=0)
    other_charges = db.Column(db.Numeric(10, 2), default=0)
    other_charges_description = db.Column(db.String(255), nullable=True)
    credit_amount = db.Column(db.Numeric(10, 2), default=0)
    credit_description = db.Column(db.String(255), nullable=True)

    total_amount = db.Column(db.Numeric(12, 2), nullable=False)
    amount_paid = db.Column(db.Numeric(12, 2), default=0)
    balance_due = db.Column(db.Numeric(12, 2), nullable=False)

    status = db.Column(
        db.Enum('draft', 'sent', 'paid', 'partial', 'overdue', 'cancelled', 'waived', name='invoice_statuses'),
        default='draft',
        index=True
    )
    notes = db.Column(db.Text, nullable=True)
    reminder_count = db.Column(db.Integer, default=0)
    last_reminder_at = db.Column(db.DateTime, nullable=True)

    # Payment reference embedded in invoice
    payment_reference = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    tenant = db.relationship('User', foreign_keys=[tenant_id], backref='invoices')
    payments = db.relationship('Payment', backref='invoice', lazy='dynamic')

    @property
    def is_overdue(self):
        return self.status not in ('paid', 'cancelled', 'waived') and date.today() > self.due_date

    @property
    def days_overdue(self):
        if self.is_overdue:
            return (date.today() - self.due_date).days
        return 0

    def __repr__(self):
        return f'<Invoice {self.invoice_number}>'


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=True, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=False, index=True)
    landlord_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    payment_method = db.Column(
        db.Enum('mpesa', 'equity_bank', 'kcb_bank', 'coop_bank', 'cash', 'cheque', 'rtgs', 'pesalink', name='payment_methods'),
        nullable=False
    )
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), default='KES')
    payment_date = db.Column(db.DateTime, nullable=False)

    # M-Pesa specifics
    mpesa_receipt_number = db.Column(db.String(50), unique=True, nullable=True)
    mpesa_transaction_id = db.Column(db.String(100), unique=True, nullable=True)
    mpesa_phone = db.Column(db.String(20), nullable=True)
    mpesa_sender_name = db.Column(db.String(200), nullable=True)
    mpesa_checkout_request_id = db.Column(db.String(100), nullable=True)
    stk_push_sent = db.Column(db.Boolean, default=False)
    stk_callback_received = db.Column(db.Boolean, default=False)
    stk_callback_data = db.Column(db.JSON, nullable=True)

    # Bank specifics
    bank_reference = db.Column(db.String(100), nullable=True)
    bank_transaction_id = db.Column(db.String(100), nullable=True)
    bank_account_from = db.Column(db.String(50), nullable=True)
    bank_name_from = db.Column(db.String(100), nullable=True)
    bank_sms_raw = db.Column(db.Text, nullable=True)  # raw SMS from bank

    # Reconciliation
    payment_reference = db.Column(db.String(100), nullable=True, index=True)
    reconciliation_status = db.Column(
        db.Enum('pending', 'matched', 'unmatched', 'disputed', name='reconciliation_statuses'),
        default='pending'
    )
    reconciled_at = db.Column(db.DateTime, nullable=True)
    reconciled_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reconciliation_notes = db.Column(db.Text, nullable=True)

    # Status
    status = db.Column(
        db.Enum('pending', 'processing', 'completed', 'failed', 'reversed', name='payment_statuses'),
        default='pending',
        index=True
    )
    failure_reason = db.Column(db.Text, nullable=True)
    receipt_generated = db.Column(db.Boolean, default=False)
    receipt_path = db.Column(db.String(500), nullable=True)
    receipt_sent_at = db.Column(db.DateTime, nullable=True)

    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenant = db.relationship('User', foreign_keys=[tenant_id])
    landlord = db.relationship('User', foreign_keys=[landlord_id])
    recorded_by = db.relationship('User', foreign_keys=[recorded_by_id])
    reconciled_by = db.relationship('User', foreign_keys=[reconciled_by_id])

    def __repr__(self):
        return f'<Payment {self.uuid} {self.amount} KES via {self.payment_method}>'


class AutoPaySchedule(db.Model):
    __tablename__ = 'auto_pay_schedules'

    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey('leases.id'), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)  # mpesa, bank
    mpesa_phone = db.Column(db.String(20), nullable=True)
    day_of_month = db.Column(db.Integer, nullable=False, default=1)
    is_active = db.Column(db.Boolean, default=True)
    last_run_at = db.Column(db.DateTime, nullable=True)
    next_run_at = db.Column(db.DateTime, nullable=True)
    failure_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tenant = db.relationship('User', foreign_keys=[tenant_id])


class BankStatement(db.Model):
    __tablename__ = 'bank_statements'

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)
    bank_name = db.Column(db.String(50), nullable=False)  # equity, kcb, coop
    account_number = db.Column(db.String(50), nullable=False)
    transaction_id = db.Column(db.String(100), unique=True, nullable=False)
    transaction_date = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text, nullable=True)
    credit_amount = db.Column(db.Numeric(12, 2), default=0)
    debit_amount = db.Column(db.Numeric(12, 2), default=0)
    balance = db.Column(db.Numeric(14, 2), nullable=True)
    reference = db.Column(db.String(100), nullable=True, index=True)
    raw_data = db.Column(db.JSON, nullable=True)

    # Reconciliation
    is_reconciled = db.Column(db.Boolean, default=False)
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'), nullable=True)
    reconciled_at = db.Column(db.DateTime, nullable=True)

    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MpesaTransaction(db.Model):
    __tablename__ = 'mpesa_transactions'

    id = db.Column(db.Integer, primary_key=True)
    checkout_request_id = db.Column(db.String(100), unique=True, nullable=False)
    merchant_request_id = db.Column(db.String(100), nullable=True)
    transaction_id = db.Column(db.String(100), unique=True, nullable=True)
    receipt_number = db.Column(db.String(50), unique=True, nullable=True)
    phone_number = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    account_reference = db.Column(db.String(100), nullable=True)
    transaction_desc = db.Column(db.String(255), nullable=True)
    transaction_date = db.Column(db.DateTime, nullable=True)
    result_code = db.Column(db.Integer, nullable=True)
    result_desc = db.Column(db.String(255), nullable=True)
    callback_raw = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, success, failed
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Expense(db.Model):
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=True)
    maintenance_request_id = db.Column(db.Integer, db.ForeignKey('maintenance_requests.id'), nullable=True)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    category = db.Column(db.String(50), nullable=False)  # maintenance, utilities, management, agent_commission
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    expense_date = db.Column(db.Date, nullable=False)
    payment_method = db.Column(db.String(30), nullable=True)
    receipt_path = db.Column(db.String(500), nullable=True)
    receipt_reference = db.Column(db.String(100), nullable=True)  # M-Pesa ref, etc.
    vendor_name = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, paid
    approval_notes = db.Column(db.Text, nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    is_recurring = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    recorded_by = db.relationship('User', foreign_keys=[recorded_by_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])
