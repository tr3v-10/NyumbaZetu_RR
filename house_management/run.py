"""
NyumbaManager — Application Entry Point
"""
import os
from app import create_app
from app.extensions import db, socketio

config_name = os.environ.get('FLASK_ENV', 'development')
app = create_app(config_name)


@app.shell_context_processor
def make_shell_context():
    from app.models import (
        User, AuditLog, Property, Unit, Lease, Invoice, Payment,
        MaintenanceRequest, VisitorLog, Notification, Announcement
    )
    return dict(
        db=db,
        User=User,
        AuditLog=AuditLog,
        Property=Property,
        Unit=Unit,
        Lease=Lease,
        Invoice=Invoice,
        Payment=Payment,
        MaintenanceRequest=MaintenanceRequest,
        VisitorLog=VisitorLog,
        Notification=Notification,
        Announcement=Announcement,
    )


@app.cli.command('create-db')
def create_db():
    """Create all database tables."""
    with app.app_context():
        db.create_all()
        print("✓ Database tables created.")


@app.cli.command('create-superadmin')
def create_superadmin():
    """Create the initial super admin account interactively."""
    from app.models.user import User
    from app.utils import generate_uuid
    from datetime import datetime

    email = input("Super admin email: ").strip().lower()
    if User.query.filter_by(email=email).first():
        print(f"✗ User with email {email} already exists.")
        return

    first_name = input("First name: ").strip()
    last_name = input("Last name: ").strip()
    phone = input("Phone (+254...): ").strip() or None

    import getpass
    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        print("✗ Password too short.")
        return

    user = User(
        uuid=generate_uuid(),
        email=email,
        phone=phone,
        first_name=first_name,
        last_name=last_name,
        role='super_admin',
        is_active=True,
        is_verified=True,
        email_verified=True,
        terms_accepted=True,
        terms_accepted_at=datetime.utcnow(),
        privacy_accepted=True,
        privacy_accepted_at=datetime.utcnow(),
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"✓ Super admin {first_name} {last_name} <{email}> created with ID {user.id}.")


@app.cli.command('seed-demo')
def seed_demo():
    """Seed demo data for testing."""
    from app.models.user import User
    from app.models.property import Property, Unit
    from app.models.tenant import Lease
    from app.utils import generate_uuid, generate_property_reference, generate_payment_reference, generate_lease_number
    from datetime import datetime, date

    print("Seeding demo data…")

    # Landlord
    landlord = User.query.filter_by(email='landlord@demo.ke').first()
    if not landlord:
        landlord = User(uuid=generate_uuid(), email='landlord@demo.ke', first_name='James', last_name='Mwangi',
                        phone='+254712000001', role='landlord', is_active=True, is_verified=True,
                        terms_accepted=True, privacy_accepted=True)
        landlord.set_password('demo1234')
        db.session.add(landlord)

    # Tenant
    tenant = User.query.filter_by(email='tenant@demo.ke').first()
    if not tenant:
        tenant = User(uuid=generate_uuid(), email='tenant@demo.ke', first_name='Amina', last_name='Ochieng',
                      phone='+254722000002', role='tenant', is_active=True, is_verified=True,
                      terms_accepted=True, privacy_accepted=True)
        tenant.set_password('demo1234')
        db.session.add(tenant)

    # Caretaker
    caretaker = User.query.filter_by(email='caretaker@demo.ke').first()
    if not caretaker:
        caretaker = User(uuid=generate_uuid(), email='caretaker@demo.ke', first_name='Peter', last_name='Njoroge',
                         phone='+254733000003', role='caretaker', is_active=True, is_verified=True,
                         terms_accepted=True, privacy_accepted=True)
        caretaker.set_password('demo1234')
        db.session.add(caretaker)

    db.session.flush()

    # Property
    prop = Property.query.filter_by(landlord_id=landlord.id).first()
    if not prop:
        prop = Property(
            uuid=generate_uuid(), landlord_id=landlord.id, caretaker_id=caretaker.id,
            name='Greenview Apartments', property_reference=generate_property_reference(),
            property_type='apartment_block', county='Nairobi', sub_county='Westlands',
            street_address='Off Waiyaki Way, Westlands', mpesa_paybill='400200',
            mpesa_account_name='Greenview Rent', bank_name='Equity Bank',
            bank_account_number='0123456789', bank_branch='Westlands'
        )
        db.session.add(prop)
        db.session.flush()

        # Units
        for i in range(1, 6):
            unit = Unit(
                uuid=generate_uuid(), property_id=prop.id,
                unit_number=f'A{i}', unit_type='2br',
                rent_amount=25000, deposit_amount=50000,
                service_charge=500, garbage_charge=300,
                bedrooms=2, bathrooms=1, floor=i,
                status='vacant' if i > 1 else 'occupied',
            )
            unit.payment_reference = generate_payment_reference(prop.id, unit.unit_number)
            db.session.add(unit)
        db.session.flush()

    db.session.commit()
    print("✓ Demo data seeded. Logins: landlord@demo.ke | tenant@demo.ke | caretaker@demo.ke — all password: demo1234")


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=app.config.get('DEBUG', False))
