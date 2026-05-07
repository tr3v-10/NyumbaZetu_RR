"""
API Blueprint — M-Pesa callbacks, bank webhooks, mobile-friendly JSON endpoints,
visitor fingerprint collection from JS.
"""
import hmac
import hashlib
import logging
from datetime import datetime, date
from flask import Blueprint, request, jsonify, current_app, abort
from flask_login import login_required, current_user
from app.extensions import db, limiter, csrf
from app.models.visitor import VisitorLog, Notification
from app.models.payment import MpesaTransaction, Invoice, Payment
from app.services.mpesa import mpesa_service
from app.services.sms_bank_analytics import bank_service

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api', template_folder='templates')


# ─── M-Pesa Callbacks (exempt from CSRF — Safaricom sends raw JSON) ──────────

@api_bp.route('/mpesa/callback', methods=['POST'])
@csrf.exempt
def mpesa_callback():
    """
    Safaricom calls this URL after an STK Push completes (success or failure).
    No authentication needed — Safaricom initiates this.
    We validate by checking the checkout_request_id against our records.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        logger.info(f"M-Pesa callback received: {data}")

        success = mpesa_service.process_callback(data)

        if success:
            # Trigger receipt generation (async in production)
            _send_payment_receipt_notification(data)

        return jsonify({'ResultCode': 0, 'ResultDesc': 'Accepted'}), 200
    except Exception as e:
        logger.error(f"M-Pesa callback error: {e}")
        return jsonify({'ResultCode': 0, 'ResultDesc': 'Accepted'}), 200  # Always ACK Safaricom


@api_bp.route('/mpesa/stk-query/<checkout_request_id>', methods=['GET'])
@login_required
@limiter.limit("30 per minute")
def mpesa_stk_query(checkout_request_id):
    txn = MpesaTransaction.query.filter_by(checkout_request_id=checkout_request_id).first()
    if not txn:
        return jsonify({'status': 'not_found'}), 404
    result = mpesa_service.query_transaction(checkout_request_id)
    return jsonify({'status': txn.status, 'transaction': result})


@api_bp.route('/mpesa/initiate', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def initiate_mpesa():
    data = request.get_json() or request.form.to_dict()
    invoice_id = data.get('invoice_id')
    phone = data.get('phone', current_user.phone)
    invoice = Invoice.query.filter_by(id=invoice_id, tenant_id=current_user.id).first_or_404()

    success, result = mpesa_service.stk_push(
        phone_number=phone,
        amount=float(invoice.balance_due),
        account_reference=invoice.payment_reference or invoice.invoice_number,
        transaction_desc=f"Rent {invoice.invoice_number[:13]}",
        invoice_id=invoice.id,
    )
    return jsonify({'success': success, 'data': result}), 200 if success else 400


# ─── Bank Webhook (bank sends statement notification) ─────────────────────────

@api_bp.route('/bank/webhook/<bank_name>', methods=['POST'])
@csrf.exempt
def bank_webhook(bank_name):
    """Receive bank transaction notifications."""
    if bank_name not in ('equity', 'kcb', 'coop'):
        return jsonify({'error': 'Unknown bank'}), 400

    # Verify webhook signature
    signature = request.headers.get('X-Webhook-Signature', '')
    secret = current_app.config.get(f'{bank_name.upper()}_API_SECRET', '')
    payload = request.get_data()
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected) and current_app.config.get('FLASK_ENV') == 'production':
        return jsonify({'error': 'Invalid signature'}), 401

    data = request.get_json(force=True, silent=True) or {}
    try:
        transactions = data.get('transactions', [data])
        property_id = request.args.get('property_id', type=int)
        if property_id:
            result = bank_service.reconcile_transactions(property_id, transactions, bank_name)
            return jsonify(result), 200
    except Exception as e:
        logger.error(f"Bank webhook error: {e}")
    return jsonify({'status': 'received'}), 200


# ─── Bank SMS Capture ─────────────────────────────────────────────────────────

@api_bp.route('/bank/sms-capture', methods=['POST'])
@login_required
def bank_sms_capture():
    """
    Mobile app sends bank SMS text for parsing and reconciliation.
    Fallback for landlords without direct bank API integration.
    """
    data = request.get_json() or {}
    sms_text = data.get('sms_text', '')
    bank_name = data.get('bank_name', 'equity')
    property_id = data.get('property_id', type(int) if False else None)

    parsed = bank_service.parse_bank_sms(sms_text, bank_name)
    return jsonify({'parsed': parsed, 'success': bool(parsed.get('amount'))})


# ─── Visitor Fingerprint Collection (from frontend JS) ───────────────────────

@api_bp.route('/fingerprint', methods=['POST'])
@csrf.exempt
@limiter.limit("60 per minute")
def collect_fingerprint():
    """
    Frontend JS sends additional browser fingerprint data:
    screen dimensions, timezone, language, platform, canvas fingerprint, etc.
    We upsert this into the most recent VisitorLog for the session.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        session_id = request.cookies.get('session', '')

        log = VisitorLog.query.filter_by(
            ip_address=request.remote_addr
        ).order_by(VisitorLog.visited_at.desc()).first()

        if log:
            log.screen_width = data.get('screenWidth')
            log.screen_height = data.get('screenHeight')
            log.color_depth = data.get('colorDepth')
            log.pixel_ratio = data.get('devicePixelRatio')
            log.timezone_offset = data.get('timezoneOffset')
            log.language = data.get('language')
            log.platform = data.get('platform')
            log.do_not_track = data.get('doNotTrack')
            log.cookie_enabled = data.get('cookieEnabled')
            log.java_enabled = data.get('javaEnabled')
            # Device fingerprint hash (canvas + audio + webgl)
            if data.get('fingerprint'):
                log.device_fingerprint = str(data.get('fingerprint'))[:255]
            db.session.commit()

        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        logger.debug(f"Fingerprint collect error: {e}")
        return jsonify({'status': 'error'}), 200


# ─── Notifications ────────────────────────────────────────────────────────────

@api_bp.route('/notifications', methods=['GET'])
@login_required
def get_notifications():
    unread = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).order_by(Notification.created_at.desc()).limit(20).all()
    return jsonify({
        'count': len(unread),
        'notifications': [
            {
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'type': n.notification_type,
                'created_at': n.created_at.isoformat(),
                'action_url': n.action_url,
                'priority': n.priority,
            }
            for n in unread
        ]
    })


@api_bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    n = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first_or_404()
    n.is_read = True
    n.read_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'status': 'ok'})


@api_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({
        'is_read': True, 'read_at': datetime.utcnow()
    })
    db.session.commit()
    return jsonify({'status': 'ok'})


# ─── Dashboard stats (JSON for charts) ───────────────────────────────────────

@api_bp.route('/stats/landlord', methods=['GET'])
@login_required
def landlord_stats():
    if current_user.role not in ('landlord', 'super_admin'):
        abort(403)
    from app.services.sms_bank_analytics import analytics_service
    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', date.today().month, type=int)
    stats = analytics_service.get_landlord_dashboard(current_user.id, year, month)
    # Make serializable
    stats.pop('properties', None)
    return jsonify(stats)


@api_bp.route('/stats/super-admin', methods=['GET'])
@login_required
def super_admin_stats():
    if current_user.role != 'super_admin':
        abort(403)
    from app.services.sms_bank_analytics import analytics_service
    stats = analytics_service.get_super_admin_dashboard()
    return jsonify(stats)


# ─── Units autocomplete ───────────────────────────────────────────────────────

@api_bp.route('/units/search', methods=['GET'])
@login_required
def search_units():
    from app.models.property import Unit, Property
    q = request.args.get('q', '')
    if current_user.role in ('landlord',):
        units = Unit.query.join(Property).filter(
            Property.landlord_id == current_user.id,
            Unit.unit_number.ilike(f'%{q}%')
        ).limit(10).all()
    else:
        units = []
    return jsonify([
        {'id': u.id, 'label': f"{u.unit_number} – {u.property.name}", 'ref': u.payment_reference}
        for u in units
    ])


# ─── Health Check ─────────────────────────────────────────────────────────────

@api_bp.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0',
        'app': 'NyumbaManager',
    }), 200


# ─── Helper ───────────────────────────────────────────────────────────────────

def _send_payment_receipt_notification(callback_data):
    """Parse callback and send receipt notification to tenant."""
    try:
        body = callback_data.get('Body', {})
        stk = body.get('stkCallback', {})
        if stk.get('ResultCode') != 0:
            return

        metadata = stk.get('CallbackMetadata', {}).get('Item', [])
        meta = {i['Name']: i.get('Value') for i in metadata}
        receipt = str(meta.get('MpesaReceiptNumber', ''))
        amount = meta.get('Amount', 0)
        phone = str(meta.get('PhoneNumber', ''))
        checkout_id = stk.get('CheckoutRequestID', '')

        txn = MpesaTransaction.query.filter_by(checkout_request_id=checkout_id).first()
        if txn and txn.invoice_id:
            invoice = Invoice.query.get(txn.invoice_id)
            if invoice:
                notif = Notification(
                    user_id=invoice.tenant_id,
                    title='Payment Received',
                    message=f'KSh {float(amount):,.0f} received via M-Pesa. Receipt: {receipt}',
                    notification_type='payment',
                    resource_type='invoice',
                    resource_id=invoice.id,
                    priority='high',
                )
                db.session.add(notif)
                db.session.commit()

                from app.services.sms_bank_analytics import sms_service
                tenant = invoice.tenant
                if tenant.phone:
                    from calendar import month_name
                    period = f"{month_name[invoice.billing_period_start.month]} {invoice.billing_period_start.year}"
                    sms_service.send_payment_receipt(
                        tenant.phone, tenant.first_name,
                        float(amount), receipt, period, invoice.unit.unit_number
                    )
    except Exception as e:
        logger.error(f"Receipt notification error: {e}")
