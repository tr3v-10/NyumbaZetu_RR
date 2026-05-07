"""
Landlord Blueprint — portfolio overview, financials, tenant & lease management, approvals.
"""
import uuid
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask.views import MethodView
from flask_login import login_required, current_user
from app.extensions import db, cache, limiter
from app.utils import role_required, log_audit, paginate_query, generate_uuid, generate_property_reference, generate_payment_reference
from app.models.property import Property, Unit
from app.models.tenant import Lease, TenantProfile
from app.models.payment import Invoice, Payment, Expense
from app.models.maintenance import MaintenanceRequest, PurchaseRequest
from app.models.visitor import Notification, Announcement
from app.models.user import User
from app.services.sms_bank_analytics import analytics_service, sms_service, bank_service

landlord_bp = Blueprint('landlord', __name__, url_prefix='/landlord', template_folder='templates')


def _require_landlord():
    if not current_user.is_authenticated or current_user.role not in ('landlord', 'super_admin'):
        abort(403)


@landlord_bp.before_request
@login_required
def before_request():
    _require_landlord()


# ─── Dashboard ────────────────────────────────────────────────────────────────

@landlord_bp.route('/dashboard')
def dashboard():
    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', date.today().month, type=int)
    stats = analytics_service.get_landlord_dashboard(current_user.id, year, month)

    # Recent activities
    prop_ids = [p.id for p in stats['properties']]
    recent_payments = Payment.query.filter(
        Payment.property_id.in_(prop_ids), Payment.status == 'completed'
    ).order_by(Payment.created_at.desc()).limit(10).all()
    pending_maintenance = MaintenanceRequest.query.filter(
        MaintenanceRequest.property_id.in_(prop_ids),
        MaintenanceRequest.status.in_(['submitted', 'assigned', 'in_progress'])
    ).order_by(MaintenanceRequest.submitted_at.desc()).limit(5).all()
    overdue_invoices = Invoice.query.filter(
        Invoice.property_id.in_(prop_ids),
        Invoice.status == 'overdue',
    ).limit(10).all()

    return render_template(
        'landlord/dashboard.html',
        stats=stats,
        recent_payments=recent_payments,
        pending_maintenance=pending_maintenance,
        overdue_invoices=overdue_invoices,
        year=year,
        month=month,
    )


# ─── Properties ───────────────────────────────────────────────────────────────

class PropertyView(MethodView):
    decorators = [login_required]

    def get(self, property_id=None):
        if property_id:
            prop = Property.query.filter_by(id=property_id, landlord_id=current_user.id).first_or_404()
            units = prop.units.filter_by(is_active=True).all()
            return render_template('landlord/property_detail.html', prop=prop, units=units)
        else:
            props = Property.query.filter_by(landlord_id=current_user.id, is_active=True).all()
            return render_template('landlord/properties.html', properties=props)

    def post(self, property_id=None):
        if property_id:
            return self._update_property(property_id)
        return self._create_property()

    def _create_property(self):
        f = request.form
        prop = Property(
            uuid=generate_uuid(),
            landlord_id=current_user.id,
            name=f.get('name', '').strip(),
            property_reference=generate_property_reference(),
            property_type=f.get('property_type', 'residential'),
            description=f.get('description', ''),
            county=f.get('county', '').strip(),
            sub_county=f.get('sub_county', ''),
            street_address=f.get('street_address', '').strip(),
            mpesa_paybill=f.get('mpesa_paybill', ''),
            mpesa_till=f.get('mpesa_till', ''),
            bank_name=f.get('bank_name', ''),
            bank_account_number=f.get('bank_account_number', ''),
            bank_branch=f.get('bank_branch', ''),
        )
        db.session.add(prop)
        db.session.commit()
        log_audit('create_property', 'property', prop.id)
        flash(f'Property "{prop.name}" created with reference {prop.property_reference}.', 'success')
        return redirect(url_for('landlord.properties'))

    def _update_property(self, property_id):
        prop = Property.query.filter_by(id=property_id, landlord_id=current_user.id).first_or_404()
        f = request.form
        updatable = ['name', 'description', 'county', 'street_address', 'mpesa_paybill',
                     'mpesa_till', 'bank_name', 'bank_account_number', 'bank_branch']
        for field in updatable:
            if f.get(field) is not None:
                setattr(prop, field, f.get(field, '').strip())
        db.session.commit()
        log_audit('update_property', 'property', prop.id)
        flash('Property updated.', 'success')
        return redirect(url_for('landlord.property_detail', property_id=property_id))


landlord_bp.add_url_rule('/properties', view_func=PropertyView.as_view('properties'))
landlord_bp.add_url_rule('/properties/<int:property_id>', view_func=PropertyView.as_view('property_detail'))


# ─── Units ────────────────────────────────────────────────────────────────────

class UnitView(MethodView):
    decorators = [login_required]

    def get(self, property_id, unit_id=None):
        prop = Property.query.filter_by(id=property_id, landlord_id=current_user.id).first_or_404()
        if unit_id:
            unit = Unit.query.filter_by(id=unit_id, property_id=property_id).first_or_404()
            lease = unit.current_lease
            return render_template('landlord/unit_detail.html', prop=prop, unit=unit, lease=lease)
        units = prop.units.filter_by(is_active=True).all()
        return render_template('landlord/units.html', prop=prop, units=units)

    def post(self, property_id, unit_id=None):
        prop = Property.query.filter_by(id=property_id, landlord_id=current_user.id).first_or_404()
        f = request.form
        if unit_id:
            unit = Unit.query.filter_by(id=unit_id, property_id=property_id).first_or_404()
            unit.rent_amount = f.get('rent_amount', unit.rent_amount, type=float)
            unit.service_charge = f.get('service_charge', unit.service_charge, type=float)
            unit.water_charge = f.get('water_charge', unit.water_charge, type=float)
            db.session.commit()
            flash('Unit updated.', 'success')
        else:
            unit = Unit(
                uuid=generate_uuid(),
                property_id=property_id,
                unit_number=f.get('unit_number', '').strip(),
                unit_type=f.get('unit_type', 'bedsitter'),
                rent_amount=float(f.get('rent_amount', 0)),
                deposit_amount=float(f.get('deposit_amount', 0)),
                service_charge=float(f.get('service_charge', 0)),
                water_charge=float(f.get('water_charge', 0)),
                garbage_charge=float(f.get('garbage_charge', 0)),
                bedrooms=int(f.get('bedrooms', 0)),
                bathrooms=int(f.get('bathrooms', 1)),
                floor=int(f.get('floor', 0)),
                rent_due_day=int(f.get('rent_due_day', 1)),
            )
            unit.payment_reference = generate_payment_reference(property_id, unit.unit_number)
            db.session.add(unit)
            db.session.commit()
            log_audit('create_unit', 'unit', unit.id)
            flash(f'Unit {unit.unit_number} created. Payment ref: {unit.payment_reference}', 'success')
        return redirect(url_for('landlord.units', property_id=property_id))


landlord_bp.add_url_rule('/properties/<int:property_id>/units', view_func=UnitView.as_view('units'))
landlord_bp.add_url_rule('/properties/<int:property_id>/units/<int:unit_id>', view_func=UnitView.as_view('unit_detail'))


# ─── Leases ───────────────────────────────────────────────────────────────────

@landlord_bp.route('/leases')
def leases():
    prop_ids = [p.id for p in Property.query.filter_by(landlord_id=current_user.id).all()]
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', 'active')
    q = Lease.query.filter(
        Lease.unit_id.in_(
            db.session.query(Unit.id).filter(Unit.property_id.in_(prop_ids))
        )
    )
    if status:
        q = q.filter_by(status=status)
    pagination = paginate_query(q.order_by(Lease.created_at.desc()), page)
    return render_template('landlord/leases.html', pagination=pagination, status=status)


@landlord_bp.route('/leases/<int:lease_id>')
def lease_detail(lease_id):
    prop_ids = [p.id for p in Property.query.filter_by(landlord_id=current_user.id).all()]
    lease = Lease.query.get_or_404(lease_id)
    if lease.unit.property_id not in prop_ids:
        abort(403)
    invoices = Invoice.query.filter_by(lease_id=lease_id).order_by(Invoice.billing_period_start.desc()).all()
    payments = Payment.query.filter_by(unit_id=lease.unit_id).order_by(Payment.payment_date.desc()).all()
    return render_template('landlord/lease_detail.html', lease=lease, invoices=invoices, payments=payments)


@landlord_bp.route('/leases/create', methods=['GET', 'POST'])
def create_lease():
    prop_ids = [p.id for p in Property.query.filter_by(landlord_id=current_user.id).all()]
    if request.method == 'POST':
        f = request.form
        unit_id = int(f.get('unit_id', 0))
        unit = Unit.query.filter(Unit.id == unit_id, Unit.property_id.in_(prop_ids)).first_or_404()
        tenant_email = f.get('tenant_email', '').strip().lower()
        tenant = User.query.filter_by(email=tenant_email, role='tenant').first()
        if not tenant:
            flash(f'Tenant with email {tenant_email} not found. Ask them to register first.', 'danger')
            return redirect(url_for('landlord.create_lease'))

        from app.utils import generate_lease_number
        lease = Lease(
            uuid=generate_uuid(),
            unit_id=unit_id,
            tenant_id=tenant.id,
            landlord_id=current_user.id,
            lease_number=generate_lease_number(unit.property.property_reference, unit.unit_number),
            start_date=datetime.strptime(f.get('start_date'), '%Y-%m-%d').date(),
            end_date=datetime.strptime(f.get('end_date'), '%Y-%m-%d').date(),
            rent_amount=float(f.get('rent_amount', unit.rent_amount)),
            deposit_amount=float(f.get('deposit_amount', unit.deposit_amount or 0)),
            service_charge=float(f.get('service_charge', unit.service_charge or 0)),
            water_charge=float(f.get('water_charge', unit.water_charge or 0)),
            garbage_charge=float(f.get('garbage_charge', unit.garbage_charge or 0)),
            notice_period_days=int(f.get('notice_period_days', 30)),
            pets_allowed=f.get('pets_allowed') == 'on',
            number_of_occupants=int(f.get('number_of_occupants', 1)),
            special_conditions=f.get('special_conditions', ''),
            status='active',
        )
        unit.status = 'occupied'
        db.session.add(lease)
        db.session.commit()

        # Notify tenant
        notif = Notification(
            user_id=tenant.id,
            title='New Lease Agreement',
            message=f'A lease for Unit {unit.unit_number} has been created. Start: {lease.start_date}.',
            notification_type='lease',
            resource_type='lease',
            resource_id=lease.id,
        )
        db.session.add(notif)
        db.session.commit()

        log_audit('create_lease', 'lease', lease.id)
        flash(f'Lease {lease.lease_number} created.', 'success')
        return redirect(url_for('landlord.leases'))

    vacant_units = Unit.query.filter(
        Unit.property_id.in_(prop_ids), Unit.status == 'vacant', Unit.is_active == True
    ).all()
    return render_template('landlord/create_lease.html', vacant_units=vacant_units)


# ─── Invoices ─────────────────────────────────────────────────────────────────

@landlord_bp.route('/invoices', methods=['GET'])
def invoices():
    prop_ids = [p.id for p in Property.query.filter_by(landlord_id=current_user.id).all()]
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    q = Invoice.query.filter(Invoice.property_id.in_(prop_ids))
    if status:
        q = q.filter_by(status=status)
    pagination = paginate_query(q.order_by(Invoice.due_date.desc()), page)
    return render_template('landlord/invoices.html', pagination=pagination, status=status)


@landlord_bp.route('/invoices/generate', methods=['POST'])
def generate_invoices():
    """Bulk generate monthly rent invoices for all active leases."""
    from app.utils import generate_invoice_number
    prop_ids = [p.id for p in Property.query.filter_by(landlord_id=current_user.id).all()]
    month = request.form.get('month', date.today().month, type=int)
    year = request.form.get('year', date.today().year, type=int)

    leases = Lease.query.filter(
        Lease.landlord_id == current_user.id,
        Lease.status == 'active',
    ).all()

    generated = 0
    skipped = 0
    for lease in leases:
        # Check if already generated
        existing = Invoice.query.filter_by(
            lease_id=lease.id,
            billing_period_start=date(year, month, 1),
        ).first()
        if existing:
            skipped += 1
            continue

        from calendar import monthrange
        days_in_month = monthrange(year, month)[1]
        due_date = date(year, month, lease.unit.rent_due_day)
        seq = Invoice.query.filter(Invoice.property_id == lease.unit.property_id).count() + 1
        inv = Invoice(
            uuid=generate_uuid(),
            lease_id=lease.id,
            tenant_id=lease.tenant_id,
            unit_id=lease.unit_id,
            property_id=lease.unit.property_id,
            invoice_number=generate_invoice_number(
                lease.unit.property.property_reference, year, month, seq
            ),
            billing_period_start=date(year, month, 1),
            billing_period_end=date(year, month, days_in_month),
            due_date=due_date,
            issue_date=date.today(),
            rent_amount=lease.rent_amount,
            service_charge=lease.service_charge,
            water_charge=lease.water_charge,
            garbage_charge=lease.garbage_charge,
            total_amount=lease.total_monthly_rent,
            balance_due=lease.total_monthly_rent,
            status='sent',
            payment_reference=lease.unit.payment_reference,
        )
        db.session.add(inv)

        # Notify tenant
        notif = Notification(
            user_id=lease.tenant_id,
            title=f'Rent Invoice for {date(year, month, 1).strftime("%B %Y")}',
            message=f'Invoice {inv.invoice_number} of KSh {inv.total_amount:,.0f} due {due_date}.',
            notification_type='payment',
            resource_type='invoice',
            resource_id=inv.id,
        )
        db.session.add(notif)

        # SMS reminder
        if lease.tenant.phone and lease.tenant.notification_sms:
            sms_service.send_rent_reminder(
                lease.tenant.phone,
                lease.tenant.first_name,
                lease.unit.unit_number,
                float(inv.total_amount),
                str(due_date),
                current_user.full_name,
            )

        generated += 1

    db.session.commit()
    log_audit('generate_invoices', details={'month': month, 'year': year, 'generated': generated})
    flash(f'{generated} invoice(s) generated. {skipped} already existed.', 'success')
    return redirect(url_for('landlord.invoices'))


# ─── Payments / Reconciliation ────────────────────────────────────────────────

@landlord_bp.route('/payments')
def payments():
    prop_ids = [p.id for p in Property.query.filter_by(landlord_id=current_user.id).all()]
    page = request.args.get('page', 1, type=int)
    method = request.args.get('method', '')
    q = Payment.query.filter(Payment.property_id.in_(prop_ids), Payment.status == 'completed')
    if method:
        q = q.filter_by(payment_method=method)
    pagination = paginate_query(q.order_by(Payment.payment_date.desc()), page)
    return render_template('landlord/payments.html', pagination=pagination, method=method)


@landlord_bp.route('/payments/record', methods=['POST'])
def record_payment():
    """Manually record a cash or cheque payment."""
    from app.utils import generate_uuid
    invoice_id = request.form.get('invoice_id', type=int)
    invoice = Invoice.query.get_or_404(invoice_id)
    prop = Property.query.filter_by(id=invoice.property_id, landlord_id=current_user.id).first_or_404()

    amount = float(request.form.get('amount', 0))
    method = request.form.get('payment_method', 'cash')
    notes = request.form.get('notes', '')

    payment = Payment(
        uuid=generate_uuid(),
        invoice_id=invoice_id,
        tenant_id=invoice.tenant_id,
        property_id=invoice.property_id,
        unit_id=invoice.unit_id,
        landlord_id=current_user.id,
        recorded_by_id=current_user.id,
        payment_method=method,
        amount=amount,
        payment_date=datetime.utcnow(),
        status='completed',
        reconciliation_status='matched',
        reconciled_at=datetime.utcnow(),
        notes=notes,
    )
    db.session.add(payment)

    invoice.amount_paid = float(invoice.amount_paid or 0) + amount
    invoice.balance_due = float(invoice.total_amount) - float(invoice.amount_paid)
    invoice.status = 'paid' if invoice.balance_due <= 0 else 'partial'
    if invoice.status == 'paid':
        invoice.paid_at = datetime.utcnow()

    db.session.commit()
    log_audit('record_payment', 'payment', payment.id, {'amount': amount, 'method': method})
    flash(f'Payment of KSh {amount:,.0f} recorded.', 'success')
    return redirect(url_for('landlord.invoices'))


# ─── Maintenance Approvals ────────────────────────────────────────────────────

@landlord_bp.route('/maintenance')
def maintenance():
    prop_ids = [p.id for p in Property.query.filter_by(landlord_id=current_user.id).all()]
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    q = MaintenanceRequest.query.filter(MaintenanceRequest.property_id.in_(prop_ids))
    if status:
        q = q.filter_by(status=status)
    pagination = paginate_query(q.order_by(MaintenanceRequest.submitted_at.desc()), page)
    return render_template('landlord/maintenance.html', pagination=pagination, status=status)


@landlord_bp.route('/maintenance/<int:request_id>/approve-purchase', methods=['POST'])
def approve_purchase(request_id):
    maint = MaintenanceRequest.query.get_or_404(request_id)
    prop = Property.query.filter_by(id=maint.property_id, landlord_id=current_user.id).first_or_404()
    purchase_id = request.form.get('purchase_id', type=int)
    action = request.form.get('action')  # approve or reject

    pr = PurchaseRequest.query.filter_by(id=purchase_id, maintenance_request_id=request_id).first_or_404()
    pr.status = 'approved' if action == 'approve' else 'rejected'
    pr.approved_by_id = current_user.id
    pr.approved_at = datetime.utcnow()
    pr.approval_notes = request.form.get('notes', '')
    db.session.commit()

    notif = Notification(
        user_id=maint.assigned_to_id or maint.tenant_id,
        title=f'Purchase Request {pr.status.title()}',
        message=f'Your purchase request for {pr.item_description} has been {pr.status}.',
        notification_type='maintenance',
    )
    db.session.add(notif)
    db.session.commit()

    log_audit(f'purchase_request_{pr.status}', 'purchase_request', purchase_id)
    flash(f'Purchase request {pr.status}.', 'success')
    return redirect(url_for('landlord.maintenance'))


# ─── Expenses ─────────────────────────────────────────────────────────────────

@landlord_bp.route('/expenses', methods=['GET', 'POST'])
def expenses():
    prop_ids = [p.id for p in Property.query.filter_by(landlord_id=current_user.id).all()]
    if request.method == 'POST':
        f = request.form
        exp = Expense(
            uuid=generate_uuid(),
            property_id=int(f.get('property_id', 0)),
            recorded_by_id=current_user.id,
            approved_by_id=current_user.id,
            category=f.get('category', ''),
            description=f.get('description', ''),
            amount=float(f.get('amount', 0)),
            expense_date=datetime.strptime(f.get('expense_date', date.today().isoformat()), '%Y-%m-%d').date(),
            payment_method=f.get('payment_method', ''),
            vendor_name=f.get('vendor_name', ''),
            status='approved',
            approved_at=datetime.utcnow(),
        )
        db.session.add(exp)
        db.session.commit()
        log_audit('record_expense', 'expense', exp.id)
        flash('Expense recorded.', 'success')

    page = request.args.get('page', 1, type=int)
    q = Expense.query.filter(Expense.property_id.in_(prop_ids))
    pagination = paginate_query(q.order_by(Expense.expense_date.desc()), page)
    properties = Property.query.filter(Property.id.in_(prop_ids)).all()
    return render_template('landlord/expenses.html', pagination=pagination, properties=properties)


# ─── Reports ──────────────────────────────────────────────────────────────────

@landlord_bp.route('/reports')
def reports():
    prop_ids = [p.id for p in Property.query.filter_by(landlord_id=current_user.id).all()]
    year = request.args.get('year', date.today().year, type=int)
    stats = analytics_service.get_landlord_dashboard(current_user.id, year)
    return render_template('landlord/reports.html', stats=stats, year=year, prop_ids=prop_ids)


# ─── Announcements ────────────────────────────────────────────────────────────

@landlord_bp.route('/announcements', methods=['GET', 'POST'])
def announcements():
    prop_ids = [p.id for p in Property.query.filter_by(landlord_id=current_user.id).all()]
    if request.method == 'POST':
        f = request.form
        property_id = int(f.get('property_id', 0))
        if property_id not in prop_ids:
            abort(403)
        ann = Announcement(
            property_id=property_id,
            created_by_id=current_user.id,
            title=f.get('title', ''),
            message=f.get('message', ''),
            announcement_type=f.get('type', 'general'),
            send_sms=f.get('send_sms') == 'on',
            send_in_app=True,
        )
        db.session.add(ann)

        # Notify tenants of the property
        active_leases = Lease.query.filter(
            Lease.landlord_id == current_user.id,
            Lease.status == 'active',
            Lease.unit_id.in_(
                db.session.query(Unit.id).filter(Unit.property_id == property_id)
            )
        ).all()

        sms_phones = []
        for lease in active_leases:
            notif = Notification(
                user_id=lease.tenant_id,
                title=ann.title,
                message=ann.message,
                notification_type='announcement',
            )
            db.session.add(notif)
            if ann.send_sms and lease.tenant.phone:
                sms_phones.append(lease.tenant.phone)

        if sms_phones:
            sms_service.send_broadcast(sms_phones, ann.title, ann.message)

        db.session.commit()
        log_audit('send_announcement', 'announcement', ann.id)
        flash('Announcement sent.', 'success')

    page = request.args.get('page', 1, type=int)
    q = Announcement.query.filter(Announcement.property_id.in_(prop_ids))
    pagination = paginate_query(q.order_by(Announcement.created_at.desc()), page)
    properties = Property.query.filter(Property.id.in_(prop_ids)).all()
    return render_template('landlord/announcements.html', pagination=pagination, properties=properties)
