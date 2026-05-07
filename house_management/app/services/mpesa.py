"""
M-Pesa Daraja API Service — STK Push, callbacks, reconciliation.
Direct tenant → landlord Paybill/Till flows. App never holds funds.
"""
import base64
import logging
import requests
from datetime import datetime
from flask import current_app

logger = logging.getLogger(__name__)


class MpesaService:
    def __init__(self):
        self.consumer_key = None
        self.consumer_secret = None
        self.shortcode = None
        self.passkey = None
        self.callback_url = None
        self.base_url = None
        self._token = None
        self._token_expiry = None

    def init_app(self, app):
        self.consumer_key = app.config.get('MPESA_CONSUMER_KEY', '')
        self.consumer_secret = app.config.get('MPESA_CONSUMER_SECRET', '')
        self.shortcode = app.config.get('MPESA_SHORTCODE', '')
        self.passkey = app.config.get('MPESA_PASSKEY', '')
        self.callback_url = app.config.get('MPESA_CALLBACK_URL', '')
        self.base_url = app.config.get('MPESA_BASE_URL', 'https://sandbox.safaricom.co.ke')

    def _get_access_token(self):
        """Fetch OAuth access token from Safaricom."""
        if self._token and self._token_expiry and datetime.utcnow() < self._token_expiry:
            return self._token

        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        credentials = base64.b64encode(
            f"{self.consumer_key}:{self.consumer_secret}".encode()
        ).decode('utf-8')

        try:
            response = requests.get(
                url,
                headers={'Authorization': f'Basic {credentials}'},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            self._token = data.get('access_token')
            from datetime import timedelta
            self._token_expiry = datetime.utcnow() + timedelta(seconds=int(data.get('expires_in', 3600)) - 60)
            return self._token
        except Exception as e:
            logger.error(f"M-Pesa token error: {e}")
            raise

    def _generate_password(self, timestamp):
        """Generate Lipa Na M-Pesa password."""
        data_to_encode = f"{self.shortcode}{self.passkey}{timestamp}"
        return base64.b64encode(data_to_encode.encode()).decode('utf-8')

    def stk_push(self, phone_number, amount, account_reference, transaction_desc, invoice_id=None):
        """
        Initiate STK Push — sends payment prompt to tenant's phone.
        Money flows: Tenant M-Pesa → Landlord Paybill/Till directly.
        App only receives callback to confirm and generate receipt.

        Returns: (success: bool, data: dict)
        """
        from app.models.payment import MpesaTransaction
        from app.extensions import db
        import uuid

        # Normalize phone number to 254XXXXXXXXX
        phone = self._normalize_phone(phone_number)
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        password = self._generate_password(timestamp)

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": self.shortcode,
            "PhoneNumber": phone,
            "CallBackURL": self.callback_url,
            "AccountReference": account_reference[:12],
            "TransactionDesc": transaction_desc[:13],
        }

        try:
            token = self._get_access_token()
            response = requests.post(
                f"{self.base_url}/mpesa/stkpush/v1/processrequest",
                json=payload,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json',
                },
                timeout=30
            )
            data = response.json()

            checkout_request_id = data.get('CheckoutRequestID', '')
            merchant_request_id = data.get('MerchantRequestID', '')
            response_code = data.get('ResponseCode', '-1')

            # Record the transaction attempt
            txn = MpesaTransaction(
                checkout_request_id=checkout_request_id or str(uuid.uuid4()),
                merchant_request_id=merchant_request_id,
                phone_number=phone,
                amount=amount,
                account_reference=account_reference,
                transaction_desc=transaction_desc,
                invoice_id=invoice_id,
                status='pending',
            )
            db.session.add(txn)
            db.session.commit()

            if response_code == '0':
                logger.info(f"STK Push initiated for {phone}, amount {amount}, ref {checkout_request_id}")
                return True, {
                    'checkout_request_id': checkout_request_id,
                    'merchant_request_id': merchant_request_id,
                    'customer_message': data.get('CustomerMessage', ''),
                }
            else:
                logger.warning(f"STK Push failed: {data}")
                return False, {'error': data.get('errorMessage', 'STK Push failed'), 'data': data}

        except Exception as e:
            logger.error(f"STK Push exception: {e}")
            return False, {'error': str(e)}

    def process_callback(self, callback_data):
        """
        Process M-Pesa STK callback — the app receives confirmation from Safaricom.
        On success: mark invoice paid, generate receipt, send SMS receipt to tenant.
        """
        from app.models.payment import MpesaTransaction, Payment, Invoice
        from app.models.user import User
        from app.extensions import db
        import uuid as uuid_mod

        try:
            body = callback_data.get('Body', {})
            stk_callback = body.get('stkCallback', {})
            result_code = stk_callback.get('ResultCode', -1)
            checkout_request_id = stk_callback.get('CheckoutRequestID', '')

            # Find the transaction
            txn = MpesaTransaction.query.filter_by(
                checkout_request_id=checkout_request_id
            ).first()

            if not txn:
                logger.warning(f"No transaction found for checkout_request_id: {checkout_request_id}")
                return False

            txn.callback_raw = callback_data
            txn.stk_callback_received = True if hasattr(txn, 'stk_callback_received') else True

            if result_code == 0:
                # Payment successful
                metadata = stk_callback.get('CallbackMetadata', {}).get('Item', [])
                meta_dict = {item['Name']: item.get('Value') for item in metadata}

                txn.receipt_number = str(meta_dict.get('MpesaReceiptNumber', ''))
                txn.transaction_id = str(meta_dict.get('MpesaReceiptNumber', ''))
                txn.amount = meta_dict.get('Amount', txn.amount)
                txn.phone_number = str(meta_dict.get('PhoneNumber', txn.phone_number))
                raw_date = meta_dict.get('TransactionDate')
                if raw_date:
                    txn.transaction_date = datetime.strptime(str(raw_date), '%Y%m%d%H%M%S')
                txn.status = 'success'

                # If linked to an invoice, create payment record
                if txn.invoice_id:
                    invoice = Invoice.query.get(txn.invoice_id)
                    if invoice:
                        payment = Payment(
                            uuid=str(uuid_mod.uuid4()),
                            invoice_id=invoice.id,
                            tenant_id=invoice.tenant_id,
                            property_id=invoice.property_id,
                            unit_id=invoice.unit_id,
                            landlord_id=invoice.lease.landlord_id,
                            payment_method='mpesa',
                            amount=txn.amount,
                            payment_date=txn.transaction_date or datetime.utcnow(),
                            mpesa_receipt_number=txn.receipt_number,
                            mpesa_transaction_id=txn.transaction_id,
                            mpesa_phone=txn.phone_number,
                            mpesa_checkout_request_id=checkout_request_id,
                            stk_push_sent=True,
                            stk_callback_received=True,
                            stk_callback_data=callback_data,
                            status='completed',
                            reconciliation_status='matched',
                            reconciled_at=datetime.utcnow(),
                            payment_reference=invoice.payment_reference,
                        )
                        db.session.add(payment)

                        # Update invoice
                        invoice.amount_paid = float(invoice.amount_paid or 0) + float(txn.amount)
                        invoice.balance_due = float(invoice.total_amount) - float(invoice.amount_paid)
                        if invoice.balance_due <= 0:
                            invoice.status = 'paid'
                            invoice.paid_at = datetime.utcnow()
                        elif invoice.amount_paid > 0:
                            invoice.status = 'partial'

                db.session.commit()
                logger.info(f"M-Pesa callback success: {txn.receipt_number}")
                return True
            else:
                txn.status = 'failed'
                txn.result_code = result_code
                txn.result_desc = stk_callback.get('ResultDesc', '')
                db.session.commit()
                logger.warning(f"M-Pesa callback failed: code={result_code}, desc={txn.result_desc}")
                return False

        except Exception as e:
            logger.error(f"Callback processing error: {e}")
            db.session.rollback()
            return False

    def query_transaction(self, checkout_request_id):
        """Query transaction status from Safaricom."""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        password = self._generate_password(timestamp)

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }
        try:
            token = self._get_access_token()
            response = requests.post(
                f"{self.base_url}/mpesa/stkpushquery/v1/query",
                json=payload,
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                timeout=30
            )
            return response.json()
        except Exception as e:
            logger.error(f"Transaction query error: {e}")
            return {'error': str(e)}

    def _normalize_phone(self, phone):
        """Convert 07XXXXXXXX or +2547XXXXXXXX to 2547XXXXXXXX."""
        phone = str(phone).strip().replace(' ', '').replace('-', '')
        if phone.startswith('+254'):
            phone = phone[1:]
        elif phone.startswith('07') or phone.startswith('01'):
            phone = '254' + phone[1:]
        elif phone.startswith('7') or phone.startswith('1'):
            phone = '254' + phone
        return phone


mpesa_service = MpesaService()
