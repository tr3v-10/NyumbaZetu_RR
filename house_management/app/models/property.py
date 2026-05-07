"""
Property and Unit models — the physical assets being managed.
"""
from datetime import datetime
from app.extensions import db


class Property(db.Model):
    __tablename__ = 'properties'

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    landlord_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    caretaker_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Identity
    name = db.Column(db.String(255), nullable=False)
    property_reference = db.Column(db.String(50), unique=True, nullable=False)  # e.g., NYM-001
    property_type = db.Column(
        db.Enum('residential', 'commercial', 'mixed_use', 'apartment_block', 'standalone', name='property_types'),
        nullable=False,
        default='residential'
    )
    description = db.Column(db.Text, nullable=True)

    # Location
    county = db.Column(db.String(100), nullable=False)
    sub_county = db.Column(db.String(100), nullable=True)
    ward = db.Column(db.String(100), nullable=True)
    street_address = db.Column(db.String(255), nullable=False)
    postal_code = db.Column(db.String(20), nullable=True)
    latitude = db.Column(db.Numeric(10, 8), nullable=True)
    longitude = db.Column(db.Numeric(11, 8), nullable=True)
    google_maps_url = db.Column(db.Text, nullable=True)
    landmark = db.Column(db.String(255), nullable=True)  # e.g., "Near ABC School"

    # Financial
    water_account_number = db.Column(db.String(50), nullable=True)
    electricity_account_number = db.Column(db.String(50), nullable=True)
    mpesa_paybill = db.Column(db.String(20), nullable=True)
    mpesa_till = db.Column(db.String(20), nullable=True)
    mpesa_account_name = db.Column(db.String(100), nullable=True)
    bank_name = db.Column(db.String(100), nullable=True)
    bank_account_number = db.Column(db.String(50), nullable=True)
    bank_branch = db.Column(db.String(100), nullable=True)
    bank_swift_code = db.Column(db.String(20), nullable=True)

    # Bank API integration flags
    equity_api_enabled = db.Column(db.Boolean, default=False)
    kcb_api_enabled = db.Column(db.Boolean, default=False)
    coop_api_enabled = db.Column(db.Boolean, default=False)
    equity_account_ref = db.Column(db.String(100), nullable=True)
    kcb_account_ref = db.Column(db.String(100), nullable=True)
    coop_account_ref = db.Column(db.String(100), nullable=True)

    # Service charges
    garbage_collection_fee = db.Column(db.Numeric(10, 2), default=0)
    security_fee = db.Column(db.Numeric(10, 2), default=0)
    management_fee_percentage = db.Column(db.Numeric(5, 2), default=0)  # % of rent
    agent_commission_percentage = db.Column(db.Numeric(5, 2), default=0)

    # Status
    is_active = db.Column(db.Boolean, default=True)
    year_built = db.Column(db.Integer, nullable=True)
    total_floors = db.Column(db.Integer, default=1)
    has_lift = db.Column(db.Boolean, default=False)
    has_parking = db.Column(db.Boolean, default=False)
    has_generator = db.Column(db.Boolean, default=False)
    has_borehole = db.Column(db.Boolean, default=False)
    has_security = db.Column(db.Boolean, default=False)
    has_cctv = db.Column(db.Boolean, default=False)

    # Photos
    cover_photo = db.Column(db.String(500), nullable=True)

    # Compliance
    county_permit_number = db.Column(db.String(100), nullable=True)
    county_permit_expiry = db.Column(db.Date, nullable=True)
    fire_safety_certificate = db.Column(db.String(100), nullable=True)
    fire_safety_expiry = db.Column(db.Date, nullable=True)
    nema_certificate = db.Column(db.String(100), nullable=True)
    structural_inspection_date = db.Column(db.Date, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    landlord = db.relationship('User', foreign_keys=[landlord_id], backref='properties')
    agent = db.relationship('User', foreign_keys=[agent_id])
    caretaker = db.relationship('User', foreign_keys=[caretaker_id])
    units = db.relationship('Unit', backref='property', lazy='dynamic', cascade='all, delete-orphan')
    maintenance_requests = db.relationship('MaintenanceRequest', backref='property', lazy='dynamic')
    announcements = db.relationship('Announcement', backref='property', lazy='dynamic')
    documents = db.relationship('PropertyDocument', backref='property', lazy='dynamic')
    inspections = db.relationship('Inspection', backref='property', lazy='dynamic')

    @property
    def total_units(self):
        return self.units.count()

    @property
    def occupied_units(self):
        return self.units.filter_by(status='occupied').count()

    @property
    def vacancy_rate(self):
        total = self.total_units
        if total == 0:
            return 0
        return round(((total - self.occupied_units) / total) * 100, 1)

    @property
    def occupancy_rate(self):
        return round(100 - self.vacancy_rate, 1)

    def __repr__(self):
        return f'<Property {self.name} [{self.property_reference}]>'


class Unit(db.Model):
    __tablename__ = 'units'

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)

    # Identity
    unit_number = db.Column(db.String(20), nullable=False)  # e.g., A1, 101, Ground Floor
    floor = db.Column(db.Integer, default=0)
    unit_type = db.Column(
        db.Enum('studio', 'bedsitter', '1br', '2br', '3br', '4br', '5br_plus', 'commercial', 'penthouse', name='unit_types'),
        nullable=False
    )
    description = db.Column(db.Text, nullable=True)

    # Dimensions
    size_sqm = db.Column(db.Numeric(8, 2), nullable=True)
    bedrooms = db.Column(db.Integer, default=0)
    bathrooms = db.Column(db.Integer, default=1)
    has_balcony = db.Column(db.Boolean, default=False)
    has_ensuite = db.Column(db.Boolean, default=False)
    is_furnished = db.Column(db.Boolean, default=False)
    has_dsq = db.Column(db.Boolean, default=False)  # Domestic Staff Quarters

    # Financial
    rent_amount = db.Column(db.Numeric(12, 2), nullable=False)
    deposit_amount = db.Column(db.Numeric(12, 2), nullable=True)
    deposit_months = db.Column(db.Integer, default=2)
    service_charge = db.Column(db.Numeric(10, 2), default=0)
    water_charge = db.Column(db.Numeric(10, 2), default=0)
    electricity_charge = db.Column(db.Numeric(10, 2), default=0)
    garbage_charge = db.Column(db.Numeric(10, 2), default=0)
    caretaker_charge = db.Column(db.Numeric(10, 2), default=0)

    # Meter readings
    water_meter_number = db.Column(db.String(50), nullable=True)
    electricity_meter_number = db.Column(db.String(50), nullable=True)
    last_water_reading = db.Column(db.Numeric(10, 2), default=0)
    last_electricity_reading = db.Column(db.Numeric(10, 2), default=0)
    last_meter_reading_date = db.Column(db.Date, nullable=True)

    # Unique payment reference
    payment_reference = db.Column(db.String(50), unique=True, nullable=True)  # e.g., UNIT12-A1

    # Status
    status = db.Column(
        db.Enum('vacant', 'occupied', 'reserved', 'under_maintenance', 'unavailable', name='unit_statuses'),
        default='vacant',
        nullable=False
    )
    is_active = db.Column(db.Boolean, default=True)

    # Photos
    cover_photo = db.Column(db.String(500), nullable=True)

    # Due date
    rent_due_day = db.Column(db.Integer, default=1)  # Day of month rent is due

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    leases = db.relationship('Lease', backref='unit', lazy='dynamic')
    maintenance_requests = db.relationship('MaintenanceRequest', backref='unit', lazy='dynamic')
    meter_readings = db.relationship('MeterReading', backref='unit', lazy='dynamic')
    unit_photos = db.relationship('UnitPhoto', backref='unit', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def current_lease(self):
        from app.models.tenant import Lease
        return self.leases.filter_by(status='active').first()

    @property
    def current_tenant(self):
        lease = self.current_lease
        if lease:
            return lease.tenant
        return None

    @property
    def total_monthly_charge(self):
        return float(
            (self.rent_amount or 0) +
            (self.service_charge or 0) +
            (self.water_charge or 0) +
            (self.electricity_charge or 0) +
            (self.garbage_charge or 0) +
            (self.caretaker_charge or 0)
        )

    def __repr__(self):
        return f'<Unit {self.unit_number} @ {self.property_id}>'


class UnitPhoto(db.Model):
    __tablename__ = 'unit_photos'

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    caption = db.Column(db.String(255), nullable=True)
    is_cover = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MeterReading(db.Model):
    __tablename__ = 'meter_readings'

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=False, index=True)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    meter_type = db.Column(db.Enum('water', 'electricity', name='meter_types'), nullable=False)
    previous_reading = db.Column(db.Numeric(10, 2), nullable=False)
    current_reading = db.Column(db.Numeric(10, 2), nullable=False)
    units_consumed = db.Column(db.Numeric(10, 2), nullable=False)
    rate_per_unit = db.Column(db.Numeric(10, 4), nullable=False)
    amount_due = db.Column(db.Numeric(12, 2), nullable=False)
    reading_date = db.Column(db.Date, nullable=False)
    photo_path = db.Column(db.String(500), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_billed = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    recorded_by = db.relationship('User', foreign_keys=[recorded_by_id])


class PropertyDocument(db.Model):
    __tablename__ = 'property_documents'

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False, index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    doc_type = db.Column(db.String(50), nullable=False)  # title_deed, county_permit, nema, etc.
    title = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])
