"""
Africa's Talking SMS Service — rent reminders, receipts, announcements.
"""
import logging
import requests
from datetime import datetime
from flask import current_app

logger = logging.getLogger(__name__)


class SMSService:
    def __init__(self):
        self.api_key = None
        self.username = None
        self.sender_id = None
        self._gateway = None

    def init_app(self, app):
        self.api_key = app.config.get('AT_API_KEY', '')
        self.username = app.config.get('AT_USERNAME', 'sandbox')
        self.sender_id = app.config.get('AT_SENDER_ID', 'NyumbaApp')

    def send_sms(self, phone_numbers, message, message_type='general', user_id=None):
        """
        Send SMS via Africa's Talking.
        phone_numbers: list of strings or single string
        Returns: (success: bool, response: dict)
        """
        from app.models.visitor import SMSLog
        from app.extensions import db

        if isinstance(phone_numbers, str):
            phone_numbers = [phone_numbers]

        # Normalize phones
        phones = [self._normalize_phone(p) for p in phone_numbers]
        phones_str = ','.join(phones)

        url = 'https://api.africastalking.com/version1/messaging'
        headers = {
            'apiKey': self.api_key,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
        }
        payload = {
            'username': self.username,
            'to': phones_str,
            'message': message,
        }
        if self.sender_id:
            payload['from'] = self.sender_id

        try:
            response = requests.post(url, data=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            recipients = data.get('SMSMessageData', {}).get('Recipients', [])
            for i, phone in enumerate(phones):
                r = recipients[i] if i < len(recipients) else {}
                log = SMSLog(
                    recipient_phone=phone,
                    recipient_id=user_id,
                    message=message,
                    message_type=message_type,
                    gateway_response=data,
                    message_id=r.get('messageId'),
                    status=r.get('status', 'pending').lower(),
                    cost=self._parse_cost(r.get('cost', '0')),
                    sent_at=datetime.utcnow(),
                )
                db.session.add(log)
            db.session.commit()

            logger.info(f"SMS sent to {phones_str}: {data}")
            return True, data
        except Exception as e:
            logger.error(f"SMS send error: {e}")
            return False, {'error': str(e)}

    def send_rent_reminder(self, tenant_phone, tenant_name, unit_number, amount, due_date, landlord_name):
        message = (
            f"Dear {tenant_name}, this is a reminder that your rent of KSh {amount:,.0f} "
            f"for Unit {unit_number} is due on {due_date}. "
            f"Pay via M-Pesa or bank transfer. Contact {landlord_name} for assistance. "
            f"- NyumbaManager"
        )
        return self.send_sms(tenant_phone, message, 'rent_reminder')

    def send_payment_receipt(self, tenant_phone, tenant_name, amount, receipt_number, period, unit_number):
        message = (
            f"Dear {tenant_name}, payment of KSh {amount:,.0f} for Unit {unit_number} "
            f"({period}) received. Receipt: {receipt_number}. "
            f"Thank you. - NyumbaManager"
        )
        return self.send_sms(tenant_phone, message, 'payment_receipt')

    def send_maintenance_update(self, tenant_phone, tenant_name, ticket_number, status, unit_number):
        status_msg = {
            'assigned': 'has been assigned to a caretaker',
            'in_progress': 'is being attended to',
            'completed': 'has been resolved',
        }.get(status, f'status updated to {status}')
        message = (
            f"Dear {tenant_name}, your maintenance request {ticket_number} "
            f"for Unit {unit_number} {status_msg}. "
            f"- NyumbaManager"
        )
        return self.send_sms(tenant_phone, message, 'maintenance')

    def send_broadcast(self, phone_numbers, title, body):
        message = f"[{title}] {body} - NyumbaManager"
        return self.send_sms(phone_numbers, message, 'announcement')

    def _normalize_phone(self, phone):
        phone = str(phone).strip().replace(' ', '').replace('-', '')
        if phone.startswith('+254'):
            return phone
        elif phone.startswith('254'):
            return f'+{phone}'
        elif phone.startswith('07') or phone.startswith('01'):
            return f'+254{phone[1:]}'
        elif phone.startswith('7') or phone.startswith('1'):
            return f'+254{phone}'
        return phone

    def _parse_cost(self, cost_str):
        try:
            return float(str(cost_str).replace('KES', '').replace('USD', '').strip())
        except Exception:
            return 0.0


sms_service = SMSService()


# ─── Bank Reconciliation Service ─────────────────────────────────────────────

class BankService:
    """
    Bank API integration for statement fetching and reconciliation.
    Supports Equity, KCB, Co-op Bank via their respective APIs.
    Falls back to SMS capture parsing for landlords without direct API.
    """

    def __init__(self):
        self.equity_key = None
        self.kcb_key = None
        self.coop_key = None

    def init_app(self, app):
        self.equity_key = app.config.get('EQUITY_API_KEY', '')
        self.kcb_key = app.config.get('KCB_API_KEY', '')
        self.coop_key = app.config.get('COOP_API_KEY', '')

    def fetch_equity_transactions(self, property_obj, from_date, to_date):
        """Fetch transactions from Equity Bank API."""
        url = f"{current_app.config['EQUITY_BASE_URL']}/accounts/{property_obj.equity_account_ref}/transactions"
        headers = {
            'Authorization': f'Bearer {self._get_equity_token()}',
            'Content-Type': 'application/json',
        }
        params = {'fromDate': from_date.isoformat(), 'toDate': to_date.isoformat()}
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json().get('transactions', [])
        except Exception as e:
            logger.error(f"Equity fetch error: {e}")
            return []

    def reconcile_transactions(self, property_id, transactions, bank_name):
        """
        Match incoming bank transactions against pending invoices using payment references.
        Unmatched transactions go to a review queue.
        """
        from app.models.payment import BankStatement, Invoice, Payment
        from app.models.property import Property
        from app.extensions import db
        import uuid as uuid_mod

        matched = 0
        unmatched = 0

        for txn in transactions:
            ref = (txn.get('reference') or '').upper()
            amount = float(txn.get('credit', 0) or 0)

            if amount <= 0:
                continue

            stmt = BankStatement(
                property_id=property_id,
                bank_name=bank_name,
                account_number=txn.get('account', ''),
                transaction_id=txn.get('id', str(uuid_mod.uuid4())),
                transaction_date=datetime.fromisoformat(txn.get('date', datetime.utcnow().isoformat())),
                description=txn.get('description', ''),
                credit_amount=amount,
                reference=ref,
                raw_data=txn,
            )

            # Try to match by payment reference
            invoice = Invoice.query.filter(
                Invoice.payment_reference == ref,
                Invoice.status.in_(['sent', 'partial', 'overdue'])
            ).first()

            if invoice:
                stmt.is_reconciled = True
                stmt.reconciled_at = datetime.utcnow()
                payment = Payment(
                    uuid=str(uuid_mod.uuid4()),
                    invoice_id=invoice.id,
                    tenant_id=invoice.tenant_id,
                    property_id=property_id,
                    unit_id=invoice.unit_id,
                    landlord_id=invoice.lease.landlord_id,
                    payment_method=bank_name + '_bank',
                    amount=amount,
                    payment_date=stmt.transaction_date,
                    bank_reference=ref,
                    bank_transaction_id=txn.get('id'),
                    status='completed',
                    reconciliation_status='matched',
                    reconciled_at=datetime.utcnow(),
                )
                db.session.add(payment)

                invoice.amount_paid = float(invoice.amount_paid or 0) + amount
                invoice.balance_due = float(invoice.total_amount) - float(invoice.amount_paid)
                if invoice.balance_due <= 0:
                    invoice.status = 'paid'
                    invoice.paid_at = datetime.utcnow()
                elif invoice.amount_paid > 0:
                    invoice.status = 'partial'

                stmt.payment_id = payment.id
                matched += 1
            else:
                stmt.is_reconciled = False
                unmatched += 1

            db.session.add(stmt)

        db.session.commit()
        return {'matched': matched, 'unmatched': unmatched, 'total': matched + unmatched}

    def parse_bank_sms(self, sms_text, bank_name='equity'):
        """
        Fallback: parse bank SMS notification to extract transaction details.
        Handles common Equity, KCB, Co-op SMS formats.
        """
        import re
        result = {'amount': None, 'reference': None, 'sender': None, 'date': None}

        # Equity format: "You have received KES 25,000.00 from JOHN DOE on 01/03/2024..."
        equity_pattern = r'received\s+KES\s+([\d,]+\.?\d*)\s+from\s+([A-Z\s]+)\s+on\s+(\d+/\d+/\d+)'
        m = re.search(equity_pattern, sms_text, re.IGNORECASE)
        if m:
            result['amount'] = float(m.group(1).replace(',', ''))
            result['sender'] = m.group(2).strip()
            return result

        # KCB format: "KSh 25,000 credited to Ac 123... Ref: UNIT12-A1"
        kcb_pattern = r'KSh\s+([\d,]+)\s+credited.*?Ref:\s*([A-Z0-9\-]+)'
        m = re.search(kcb_pattern, sms_text, re.IGNORECASE)
        if m:
            result['amount'] = float(m.group(1).replace(',', ''))
            result['reference'] = m.group(2).strip()
            return result

        return result

    def _get_equity_token(self):
        """Get Equity Bank OAuth token."""
        try:
            response = requests.post(
                f"{current_app.config['EQUITY_BASE_URL']}/oauth/token",
                data={
                    'grant_type': 'client_credentials',
                    'client_id': current_app.config['EQUITY_API_KEY'],
                    'client_secret': current_app.config['EQUITY_API_SECRET'],
                },
                timeout=30
            )
            return response.json().get('access_token', '')
        except Exception as e:
            logger.error(f"Equity token error: {e}")
            return ''


bank_service = BankService()


# ─── Analytics Service ───────────────────────────────────────────────────────

class AnalyticsService:
    """
    Generates financial and operational statistics for dashboards.
    """

    def get_landlord_dashboard(self, landlord_id, year=None, month=None):
        """Returns comprehensive stats for a landlord's portfolio."""
        from app.models.property import Property, Unit
        from app.models.payment import Invoice, Payment, Expense
        from app.models.tenant import Lease
        from sqlalchemy import func, extract
        from app.extensions import db
        from datetime import date

        year = year or date.today().year
        month = month or date.today().month

        properties = Property.query.filter_by(landlord_id=landlord_id, is_active=True).all()
        property_ids = [p.id for p in properties]

        # Units summary
        total_units = Unit.query.filter(Unit.property_id.in_(property_ids)).count()
        occupied_units = Unit.query.filter(
            Unit.property_id.in_(property_ids),
            Unit.status == 'occupied'
        ).count()
        occupancy_rate = round((occupied_units / total_units * 100) if total_units > 0 else 0, 1)

        # Revenue this month
        monthly_revenue = db.session.query(func.sum(Payment.amount)).filter(
            Payment.property_id.in_(property_ids),
            Payment.status == 'completed',
            extract('year', Payment.payment_date) == year,
            extract('month', Payment.payment_date) == month,
        ).scalar() or 0

        # Outstanding rent
        outstanding = db.session.query(func.sum(Invoice.balance_due)).filter(
            Invoice.property_id.in_(property_ids),
            Invoice.status.in_(['sent', 'partial', 'overdue']),
        ).scalar() or 0

        # Monthly expenses
        monthly_expenses = db.session.query(func.sum(Expense.amount)).filter(
            Expense.property_id.in_(property_ids),
            Expense.status == 'approved',
            extract('year', Expense.expense_date) == year,
            extract('month', Expense.expense_date) == month,
        ).scalar() or 0

        # Monthly chart data (12 months)
        chart_data = []
        for m in range(1, 13):
            rev = db.session.query(func.sum(Payment.amount)).filter(
                Payment.property_id.in_(property_ids),
                Payment.status == 'completed',
                extract('year', Payment.payment_date) == year,
                extract('month', Payment.payment_date) == m,
            ).scalar() or 0
            exp = db.session.query(func.sum(Expense.amount)).filter(
                Expense.property_id.in_(property_ids),
                Expense.status == 'approved',
                extract('year', Expense.expense_date) == year,
                extract('month', Expense.expense_date) == m,
            ).scalar() or 0
            chart_data.append({'month': m, 'revenue': float(rev), 'expenses': float(exp), 'net': float(rev) - float(exp)})

        # Arrears aging
        from sqlalchemy import case
        arrears_data = {
            '0_30': db.session.query(func.sum(Invoice.balance_due)).filter(
                Invoice.property_id.in_(property_ids),
                Invoice.status.in_(['overdue']),
                Invoice.days_overdue <= 30 if hasattr(Invoice, 'days_overdue') else True,
            ).scalar() or 0,
        }

        # Payment methods split
        payment_methods = db.session.query(
            Payment.payment_method,
            func.sum(Payment.amount),
            func.count(Payment.id)
        ).filter(
            Payment.property_id.in_(property_ids),
            Payment.status == 'completed',
            extract('year', Payment.payment_date) == year,
        ).group_by(Payment.payment_method).all()

        return {
            'summary': {
                'total_properties': len(properties),
                'total_units': total_units,
                'occupied_units': occupied_units,
                'vacant_units': total_units - occupied_units,
                'occupancy_rate': occupancy_rate,
                'monthly_revenue': float(monthly_revenue),
                'outstanding_rent': float(outstanding),
                'monthly_expenses': float(monthly_expenses),
                'net_income': float(monthly_revenue) - float(monthly_expenses),
            },
            'chart_data': chart_data,
            'payment_methods': [
                {'method': pm[0], 'total': float(pm[1]), 'count': pm[2]}
                for pm in payment_methods
            ],
            'properties': properties,
        }

    def get_super_admin_dashboard(self):
        """System-wide stats for the super admin."""
        from app.models.user import User
        from app.models.property import Property, Unit
        from app.models.payment import Invoice, Payment
        from app.models.visitor import VisitorLog
        from sqlalchemy import func, extract
        from app.extensions import db
        from datetime import date, timedelta

        today = date.today()
        this_month = today.month
        this_year = today.year

        total_users = User.query.filter_by(deleted_at=None).count()
        active_users = User.query.filter_by(is_active=True, deleted_at=None).count()
        users_by_role = db.session.query(User.role, func.count(User.id)).group_by(User.role).all()
        total_properties = Property.query.filter_by(is_active=True).count()
        total_units = Unit.query.filter_by(is_active=True).count()
        occupied_units = Unit.query.filter_by(status='occupied', is_active=True).count()

        system_revenue = db.session.query(func.sum(Payment.amount)).filter(
            Payment.status == 'completed',
            extract('year', Payment.payment_date) == this_year,
            extract('month', Payment.payment_date) == this_month,
        ).scalar() or 0

        recent_visitors = VisitorLog.query.filter(
            VisitorLog.visited_at >= (datetime.utcnow() - __import__('datetime').timedelta(days=7))
        ).count()

        visitors_by_country = db.session.query(
            VisitorLog.country, func.count(VisitorLog.id)
        ).group_by(VisitorLog.country).order_by(func.count(VisitorLog.id).desc()).limit(10).all()

        top_ips = db.session.query(
            VisitorLog.ip_address, func.count(VisitorLog.id)
        ).group_by(VisitorLog.ip_address).order_by(func.count(VisitorLog.id).desc()).limit(20).all()

        daily_visits_30 = []
        for i in range(30):
            d = today - __import__('datetime').timedelta(days=i)
            count = VisitorLog.query.filter(
                func.date(VisitorLog.visited_at) == d
            ).count()
            daily_visits_30.append({'date': d.isoformat(), 'visits': count})

        return {
            'users': {
                'total': total_users,
                'active': active_users,
                'by_role': {r[0]: r[1] for r in users_by_role},
            },
            'properties': {
                'total': total_properties,
                'total_units': total_units,
                'occupied': occupied_units,
                'occupancy_rate': round((occupied_units / total_units * 100) if total_units > 0 else 0, 1),
            },
            'revenue': {
                'this_month': float(system_revenue),
            },
            'visitors': {
                'last_7_days': recent_visitors,
                'by_country': [{'country': c[0], 'count': c[1]} for c in visitors_by_country],
                'top_ips': [{'ip': i[0], 'count': i[1]} for i in top_ips],
                'daily_30': daily_visits_30,
            },
        }


analytics_service = AnalyticsService()
