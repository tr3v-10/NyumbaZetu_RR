"""
Models package — import all models so SQLAlchemy can discover them.
"""
from app.models.user import User, AuditLog
from app.models.property import Property, Unit, UnitPhoto, MeterReading, PropertyDocument
from app.models.tenant import TenantProfile, Lease, TenantDocument, InventoryItem
from app.models.payment import Invoice, Payment, AutoPaySchedule, BankStatement, MpesaTransaction, Expense
from app.models.maintenance import (
    MaintenanceRequest, MaintenancePhoto, MaintenanceStatusHistory,
    MaintenanceMessage, PurchaseRequest, Inspection
)
from app.models.visitor import VisitorLog, Notification, Announcement, Message, SMSLog

__all__ = [
    'User', 'AuditLog',
    'Property', 'Unit', 'UnitPhoto', 'MeterReading', 'PropertyDocument',
    'TenantProfile', 'Lease', 'TenantDocument', 'InventoryItem',
    'Invoice', 'Payment', 'AutoPaySchedule', 'BankStatement', 'MpesaTransaction', 'Expense',
    'MaintenanceRequest', 'MaintenancePhoto', 'MaintenanceStatusHistory',
    'MaintenanceMessage', 'PurchaseRequest', 'Inspection',
    'VisitorLog', 'Notification', 'Announcement', 'Message', 'SMSLog',
]
