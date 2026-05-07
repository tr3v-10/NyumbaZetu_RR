"""
Tenant Blueprint — rent, maintenance, docs, messaging.
"""
import uuid
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask.views import MethodView
from flask_login import login_required, current_user
from app.extensions import db, limiter
from app.utils import role_required, log_audit, paginate_query, generate_uuid, save_file, allowed_file
from app.models.property import Property, Unit
from app.models.tenant import Lease
from app.models.payment import Invoice, Payment, AutoPaySchedule, MpesaTransaction
from app.models.maintenance import MaintenanceRequest, MaintenanceMessage, MaintenanceStatusHistory, MaintenancePhoto
from app.models.visitor import Notification, Announcement, Message
from app.models.user import User
from app.services.mpesa import mpesa_service
from app.services.sms_bank_analytics import sms_service

tenant_bp = Blueprint('tenant', __name__, url_prefix='/tenant', template_folder='templates')


def _require_tenant():
    if not current_user.is_authenticated or current_user.role not in ('tenant', 'super_admin'):
        abort(403)


@tenant_bp.before_request
@login_required
def before_request():
    _require_tenant()


@tenant_bp.route('/dashboard')
def dashboard():
    lease = Lease.query.filter_by(tenant_id=current_user.id, status='active').first()
    outstanding_invoices = Invoice.query.filter_by(
        tenant_id=current_user.id
    ).filter(Invoice.status.in_(['sent', 'partial', 'overdue'])).order_by(Invoice.due_date).all()
    recent_payments = Payment.query.filter_by(
        tenant_id=current_user.id, status='completed'
    ).order_by(Payment.payment_date.desc()).limit(5).all()
    open_maintenance = MaintenanceRequest.query.filter_by(
        tenant_id=current_user.id
    ).filter(
        MaintenanceRequest.status.not_in(['completed', 'closed', 'cancelled'])
    ).order_by(MaintenanceRequest.submitted_at.desc()).limit(5).all()
    announcements = []
    if lease:
        announcements = Announcement.query.filter_by(
            property_id=lease.unit.property_id, is_active=True
        ).order_by(Announcement.created_at.desc()).limit(5).all()

    return render_template(
        'tenant/dashboard.html',
        lease=lease,
        outstanding_invoices=outstanding_invoices,
        recent_payments=recent_payments,
        open_maintenance=open_maintenance,
        announcements=announcements,
    )


@tenant_bp.route('/invoices')
def invoices():
    page = request.args.get('page', 1, type=int)
    q = Invoice.query.filter_by(tenant_id=current_user.id).order_by(Invoice.due_date.desc())
    pagination = paginate_query(q, page)
    return render_template('tenant/invoices.html', pagination=pagination)


@tenant_bp.route('/pay/<int:invoice_id>', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def pay_invoice(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id, tenant_id=current_user.id).first_or_404()
    if invoice.status == 'paid':
        flash('This invoice has already been paid.', 'info')
        return redirect(url_for('tenant.invoices'))

    if request.method == 'POST':
        method = request.form.get('method', 'mpesa')
        if method == 'mpesa':
            phone = request.form.get('phone', current_user.phone or '')
            amount = float(invoice.balance_due)
            success, data = mpesa_service.stk_push(
                phone_number=phone,
                amount=amount,
                account_reference=invoice.payment_reference or invoice.invoice_number,
                transaction_desc=f"Rent {invoice.invoice_number}",
                invoice_id=invoice.id,
            )
            if success:
                flash(
                    f'M-Pesa payment request sent to {phone}. '
                    f'Enter your PIN to complete. Ref: {data.get("checkout_request_id", "")}',
                    'success'
                )
            else:
                flash(f'M-Pesa request failed: {data.get("error", "Unknown error")}', 'danger')
        elif method == 'bank':
            flash(
                f'Transfer KSh {float(invoice.balance_due):,.0f} to the landlord\'s bank account '
                f'using reference: {invoice.payment_reference}. '
                f'Your payment will be automatically reconciled within 24 hours.',
                'info'
            )
        return redirect(url_for('tenant.invoices'))

    lease = Lease.query.filter_by(id=invoice.lease_id).first()
    return render_template('tenant/pay_invoice.html', invoice=invoice, lease=lease)


@tenant_bp.route('/check-payment-status/<checkout_request_id>')
def check_payment_status(checkout_request_id):
    result = mpesa_service.query_transaction(checkout_request_id)
    txn = MpesaTransaction.query.filter_by(checkout_request_id=checkout_request_id).first()
    status = txn.status if txn else 'pending'
    return jsonify({'status': status, 'result': result})


@tenant_bp.route('/payments')
def payments():
    page = request.args.get('page', 1, type=int)
    q = Payment.query.filter_by(tenant_id=current_user.id, status='completed').order_by(Payment.payment_date.desc())
    pagination = paginate_query(q, page)
    return render_template('tenant/payments.html', pagination=pagination)


@tenant_bp.route('/maintenance', methods=['GET', 'POST'])
def maintenance():
    if request.method == 'POST':
        lease = Lease.query.filter_by(tenant_id=current_user.id, status='active').first()
        if not lease:
            flash('No active lease found.', 'danger')
            return redirect(url_for('tenant.maintenance'))

        from app.utils import generate_ticket_number
        f = request.form
        mr = MaintenanceRequest(
            uuid=generate_uuid(),
            property_id=lease.unit.property_id,
            unit_id=lease.unit_id,
            tenant_id=current_user.id,
            ticket_number=generate_ticket_number(lease.unit.property.property_reference),
            title=f.get('title', '').strip(),
            description=f.get('description', '').strip(),
            category=f.get('category', 'other'),
            urgency=f.get('urgency', 'routine'),
            status='submitted',
        )
        db.session.add(mr)
        db.session.flush()

        # Handle photo/video uploads
        photos = request.files.getlist('photos')
        for photo in photos:
            if photo and photo.filename and allowed_file(photo.filename, 'all'):
                path = save_file(photo, 'maintenance', f'{mr.uuid}_')
                mp = MaintenancePhoto(
                    request_id=mr.id,
                    uploaded_by_id=current_user.id,
                    file_path=path,
                    file_type='image' if photo.content_type.startswith('image') else 'video',
                    phase='before',
                )
                db.session.add(mp)

        db.session.commit()

        # Notify caretaker/landlord
        prop = Property.query.get(lease.unit.property_id)
        if prop.caretaker_id:
            notif = Notification(
                user_id=prop.caretaker_id,
                title=f'New Maintenance Request: {mr.title}',
                message=f'Tenant {current_user.full_name}, Unit {lease.unit.unit_number}: {mr.description[:100]}',
                notification_type='maintenance',
                resource_type='maintenance_request',
                resource_id=mr.id,
                priority='high' if mr.urgency == 'emergency' else 'normal',
            )
            db.session.add(notif)

        landlord_notif = Notification(
            user_id=prop.landlord_id,
            title=f'New Maintenance [{mr.urgency.upper()}]: {mr.title}',
            message=f'Unit {lease.unit.unit_number}: {mr.description[:100]}',
            notification_type='maintenance',
            resource_type='maintenance_request',
            resource_id=mr.id,
            priority='high' if mr.urgency == 'emergency' else 'normal',
        )
        db.session.add(landlord_notif)
        db.session.commit()

        log_audit('submit_maintenance', 'maintenance_request', mr.id)
        flash(f'Maintenance request submitted. Ticket: {mr.ticket_number}', 'success')
        return redirect(url_for('tenant.maintenance'))

    page = request.args.get('page', 1, type=int)
    q = MaintenanceRequest.query.filter_by(tenant_id=current_user.id).order_by(
        MaintenanceRequest.submitted_at.desc()
    )
    pagination = paginate_query(q, page)
    return render_template('tenant/maintenance.html', pagination=pagination)


@tenant_bp.route('/maintenance/<int:request_id>')
def maintenance_detail(request_id):
    mr = MaintenanceRequest.query.filter_by(id=request_id, tenant_id=current_user.id).first_or_404()
    messages = MaintenanceMessage.query.filter_by(request_id=request_id).order_by(
        MaintenanceMessage.created_at
    ).all()
    return render_template('tenant/maintenance_detail.html', mr=mr, messages=messages)


@tenant_bp.route('/maintenance/<int:request_id>/message', methods=['POST'])
def maintenance_message(request_id):
    mr = MaintenanceRequest.query.filter_by(id=request_id, tenant_id=current_user.id).first_or_404()
    msg_text = request.form.get('message', '').strip()
    if msg_text:
        msg = MaintenanceMessage(
            request_id=request_id,
            sender_id=current_user.id,
            message=msg_text,
        )
        db.session.add(msg)
        db.session.commit()
        flash('Message sent.', 'success')
    return redirect(url_for('tenant.maintenance_detail', request_id=request_id))


@tenant_bp.route('/maintenance/<int:request_id>/rate', methods=['POST'])
def rate_maintenance(request_id):
    mr = MaintenanceRequest.query.filter_by(id=request_id, tenant_id=current_user.id, status='completed').first_or_404()
    rating = request.form.get('rating', type=int)
    feedback = request.form.get('feedback', '')
    if 1 <= rating <= 5:
        mr.tenant_rating = rating
        mr.tenant_feedback = feedback
        mr.rated_at = datetime.utcnow()
        mr.status = 'closed'
        db.session.commit()
        flash('Thank you for your feedback!', 'success')
    return redirect(url_for('tenant.maintenance'))


@tenant_bp.route('/auto-pay', methods=['GET', 'POST'])
def auto_pay():
    lease = Lease.query.filter_by(tenant_id=current_user.id, status='active').first()
    if not lease:
        flash('No active lease.', 'warning')
        return redirect(url_for('tenant.dashboard'))

    if request.method == 'POST':
        f = request.form
        existing = AutoPaySchedule.query.filter_by(lease_id=lease.id, tenant_id=current_user.id).first()
        if existing:
            existing.payment_method = f.get('payment_method', 'mpesa')
            existing.mpesa_phone = f.get('mpesa_phone', current_user.phone)
            existing.day_of_month = int(f.get('day_of_month', 1))
            existing.is_active = True
        else:
            aps = AutoPaySchedule(
                lease_id=lease.id,
                tenant_id=current_user.id,
                payment_method=f.get('payment_method', 'mpesa'),
                mpesa_phone=f.get('mpesa_phone', current_user.phone),
                day_of_month=int(f.get('day_of_month', 1)),
            )
            db.session.add(aps)
        db.session.commit()
        flash('Auto-pay configured.', 'success')

    schedule = AutoPaySchedule.query.filter_by(lease_id=lease.id, tenant_id=current_user.id).first()
    return render_template('tenant/auto_pay.html', lease=lease, schedule=schedule)


@tenant_bp.route('/notifications')
def notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(50).all()
    # Mark all as read
    for n in notifs:
        if not n.is_read:
            n.is_read = True
            n.read_at = datetime.utcnow()
    db.session.commit()
    return render_template('tenant/notifications.html', notifications=notifs)


@tenant_bp.route('/documents')
def documents():
    lease = Lease.query.filter_by(tenant_id=current_user.id, status='active').first()
    return render_template('tenant/documents.html', lease=lease)


@tenant_bp.route('/messages', methods=['GET', 'POST'])
def messages():
    if request.method == 'POST':
        recipient_id = request.form.get('recipient_id', type=int)
        msg_text = request.form.get('message', '').strip()
        if recipient_id and msg_text:
            msg = Message(
                sender_id=current_user.id,
                recipient_id=recipient_id,
                message=msg_text,
                subject=request.form.get('subject', ''),
            )
            db.session.add(msg)
            db.session.commit()
            flash('Message sent.', 'success')

    inbox = Message.query.filter_by(recipient_id=current_user.id).order_by(
        Message.created_at.desc()
    ).all()
    return render_template('tenant/messages.html', inbox=inbox)


@tenant_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if request.method == 'POST':
        f = request.form
        current_user.first_name = f.get('first_name', current_user.first_name)
        current_user.last_name = f.get('last_name', current_user.last_name)
        current_user.phone = f.get('phone', current_user.phone)
        current_user.notification_sms = f.get('notification_sms') == 'on'
        current_user.notification_email = f.get('notification_email') == 'on'
        db.session.commit()
        flash('Profile updated.', 'success')
    return render_template('tenant/profile.html')


# ─────────────────────────────────────────────────────────────────────────────
# CARETAKER BLUEPRINT
# ─────────────────────────────────────────────────────────────────────────────

caretaker_bp = Blueprint('caretaker', __name__, url_prefix='/caretaker', template_folder='templates')


def _require_caretaker():
    if not current_user.is_authenticated or current_user.role not in ('caretaker', 'super_admin'):
        abort(403)


@caretaker_bp.before_request
@login_required
def caretaker_before_request():
    _require_caretaker()


@caretaker_bp.route('/dashboard')
def dashboard():
    assigned_tasks = MaintenanceRequest.query.filter_by(
        assigned_to_id=current_user.id
    ).filter(
        MaintenanceRequest.status.in_(['assigned', 'in_progress', 'awaiting_parts'])
    ).order_by(MaintenanceRequest.urgency.desc(), MaintenanceRequest.submitted_at).all()

    pending_purchases = None
    if assigned_tasks:
        from app.models.maintenance import PurchaseRequest
        pending_purchases = PurchaseRequest.query.filter(
            PurchaseRequest.maintenance_request_id.in_([t.id for t in assigned_tasks]),
            PurchaseRequest.status == 'pending',
        ).all()

    return render_template(
        'caretaker/dashboard.html',
        assigned_tasks=assigned_tasks,
        pending_purchases=pending_purchases,
    )


@caretaker_bp.route('/tasks')
def tasks():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    q = MaintenanceRequest.query.filter_by(assigned_to_id=current_user.id)
    if status:
        q = q.filter_by(status=status)
    pagination = paginate_query(q.order_by(MaintenanceRequest.submitted_at.desc()), page)
    return render_template('caretaker/tasks.html', pagination=pagination, status=status)


@caretaker_bp.route('/tasks/<int:task_id>', methods=['GET', 'POST'])
def task_detail(task_id):
    mr = MaintenanceRequest.query.filter_by(id=task_id, assigned_to_id=current_user.id).first_or_404()
    from app.models.maintenance import PurchaseRequest

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_status':
            new_status = request.form.get('status')
            valid_transitions = {
                'assigned': ['in_progress', 'awaiting_parts'],
                'in_progress': ['awaiting_parts', 'awaiting_approval', 'completed'],
                'awaiting_parts': ['in_progress'],
                'awaiting_approval': ['in_progress'],
            }
            if new_status in valid_transitions.get(mr.status, []):
                hist = MaintenanceStatusHistory(
                    request_id=mr.id,
                    changed_by_id=current_user.id,
                    old_status=mr.status,
                    new_status=new_status,
                    notes=request.form.get('notes', ''),
                )
                db.session.add(hist)
                mr.status = new_status
                mr.updated_at = datetime.utcnow()
                if new_status == 'completed':
                    mr.completed_at = datetime.utcnow()
                db.session.commit()

                # Notify tenant
                notif = Notification(
                    user_id=mr.tenant_id,
                    title=f'Maintenance Update: {mr.title}',
                    message=f'Your request {mr.ticket_number} status: {new_status.replace("_", " ").title()}.',
                    notification_type='maintenance',
                    resource_type='maintenance_request',
                    resource_id=mr.id,
                )
                db.session.add(notif)
                db.session.commit()

                if mr.tenant.phone and mr.tenant.notification_sms:
                    sms_service.send_maintenance_update(
                        mr.tenant.phone, mr.tenant.first_name,
                        mr.ticket_number, new_status, mr.unit.unit_number
                    )
                flash(f'Status updated to {new_status}.', 'success')

        elif action == 'request_purchase':
            pr = PurchaseRequest(
                maintenance_request_id=mr.id,
                requested_by_id=current_user.id,
                item_description=request.form.get('item_description', ''),
                estimated_cost=float(request.form.get('estimated_cost', 0)),
                vendor_name=request.form.get('vendor_name', ''),
                vendor_phone=request.form.get('vendor_phone', ''),
            )
            db.session.add(pr)
            mr.status = 'awaiting_approval'
            mr.requires_approval = True

            # Notify landlord
            prop = Property.query.get(mr.property_id)
            notif = Notification(
                user_id=prop.landlord_id,
                title=f'Purchase Request: KSh {float(pr.estimated_cost):,.0f}',
                message=f'Caretaker {current_user.full_name} requests KSh {float(pr.estimated_cost):,.0f} for: {pr.item_description}',
                notification_type='maintenance',
                resource_type='purchase_request',
                resource_id=pr.id,
                priority='high',
            )
            db.session.add(notif)
            db.session.commit()
            flash('Purchase request sent to landlord.', 'success')

        elif action == 'upload_receipt':
            receipt = request.files.get('receipt')
            pr_id = request.form.get('purchase_request_id', type=int)
            if receipt and pr_id:
                pr = PurchaseRequest.query.get_or_404(pr_id)
                path = save_file(receipt, 'receipts', 'rcpt_')
                pr.receipt_path = path
                pr.actual_cost = float(request.form.get('actual_cost', pr.estimated_cost))
                pr.mpesa_receipt = request.form.get('mpesa_receipt', '')
                pr.status = 'purchased'
                pr.purchased_at = datetime.utcnow()

                # Add expense
                from app.models.payment import Expense
                exp = Expense(
                    uuid=generate_uuid(),
                    property_id=mr.property_id,
                    unit_id=mr.unit_id,
                    maintenance_request_id=mr.id,
                    recorded_by_id=current_user.id,
                    category='maintenance',
                    description=pr.item_description,
                    amount=pr.actual_cost,
                    expense_date=date.today(),
                    payment_method=request.form.get('payment_method', 'mpesa'),
                    receipt_path=path,
                    receipt_reference=pr.mpesa_receipt,
                    vendor_name=pr.vendor_name,
                    status='pending',
                )
                db.session.add(exp)
                db.session.commit()
                flash('Receipt uploaded. Expense logged.', 'success')

        return redirect(url_for('caretaker.task_detail', task_id=task_id))

    purchase_requests = PurchaseRequest.query.filter_by(maintenance_request_id=task_id).all()
    messages = MaintenanceMessage.query.filter_by(request_id=task_id).order_by(MaintenanceMessage.created_at).all()
    return render_template('caretaker/task_detail.html', mr=mr, purchase_requests=purchase_requests, messages=messages)


@caretaker_bp.route('/inspections', methods=['GET', 'POST'])
def inspections():
    from app.models.maintenance import Inspection
    if request.method == 'POST':
        f = request.form
        insp = Inspection(
            property_id=int(f.get('property_id', 0)),
            unit_id=f.get('unit_id') and int(f.get('unit_id')) or None,
            conducted_by_id=current_user.id,
            inspection_type=f.get('inspection_type', 'routine'),
            scheduled_date=datetime.strptime(f.get('scheduled_date', date.today().isoformat()), '%Y-%m-%d').date(),
            actual_date=date.today() if f.get('status') == 'completed' else None,
            status=f.get('status', 'scheduled'),
            notes=f.get('notes', ''),
            boiler_pressure_ok=f.get('boiler_pressure_ok') == 'on',
            fire_extinguisher_ok=f.get('fire_extinguisher_ok') == 'on',
            common_area_clean=f.get('common_area_clean') == 'on',
            security_lights_ok=f.get('security_lights_ok') == 'on',
            water_pressure_ok=f.get('water_pressure_ok') == 'on',
            drainage_ok=f.get('drainage_ok') == 'on',
            general_condition=f.get('general_condition', 'good'),
        )
        db.session.add(insp)
        db.session.commit()
        flash('Inspection logged.', 'success')

    page = request.args.get('page', 1, type=int)
    from app.models.maintenance import Inspection
    q = Inspection.query.filter_by(conducted_by_id=current_user.id)
    pagination = paginate_query(q.order_by(Inspection.scheduled_date.desc()), page)
    # get assigned properties
    from app.models.property import Property
    properties = Property.query.filter_by(caretaker_id=current_user.id, is_active=True).all()
    return render_template('caretaker/inspections.html', pagination=pagination, properties=properties)


# ─────────────────────────────────────────────────────────────────────────────
# AGENT BLUEPRINT
# ─────────────────────────────────────────────────────────────────────────────

agent_bp = Blueprint('agent', __name__, url_prefix='/agent', template_folder='templates')


def _require_agent():
    if not current_user.is_authenticated or current_user.role not in ('agent', 'super_admin'):
        abort(403)


@agent_bp.before_request
@login_required
def agent_before_request():
    _require_agent()


@agent_bp.route('/dashboard')
def dashboard():
    managed_props = Property.query.filter_by(agent_id=current_user.id, is_active=True).all()
    prop_ids = [p.id for p in managed_props]
    vacant_units = Unit.query.filter(
        Unit.property_id.in_(prop_ids), Unit.status == 'vacant', Unit.is_active == True
    ).all()
    active_leases = Lease.query.filter(
        Lease.agent_id == current_user.id, Lease.status == 'active'
    ).all()
    return render_template(
        'agent/dashboard.html',
        properties=managed_props,
        vacant_units=vacant_units,
        active_leases=active_leases,
    )


@agent_bp.route('/listings')
def listings():
    prop_ids = [p.id for p in Property.query.filter_by(agent_id=current_user.id).all()]
    vacant_units = Unit.query.filter(
        Unit.property_id.in_(prop_ids), Unit.status == 'vacant', Unit.is_active == True
    ).order_by(Unit.rent_amount).all()
    return render_template('agent/listings.html', vacant_units=vacant_units)


@agent_bp.route('/leases')
def leases():
    page = request.args.get('page', 1, type=int)
    q = Lease.query.filter_by(agent_id=current_user.id).order_by(Lease.created_at.desc())
    pagination = paginate_query(q, page)
    return render_template('agent/leases.html', pagination=pagination)


@agent_bp.route('/commissions')
def commissions():
    active_leases = Lease.query.filter_by(agent_id=current_user.id, status='active').all()
    total_commission = sum(
        float(l.rent_amount) * float(l.unit.property.agent_commission_percentage or 0) / 100
        for l in active_leases
    )
    return render_template('agent/commissions.html', leases=active_leases, total_commission=total_commission)


@agent_bp.route('/applicants')
def applicants():
    """Placeholder for applicant tracking."""
    return render_template('agent/applicants.html')
