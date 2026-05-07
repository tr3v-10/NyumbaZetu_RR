"""
NyumbaManager - House Management App Configuration
Kenya-focused property management solution
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration"""
    # App
    APP_NAME = os.environ.get('APP_NAME', 'NyumbaManager')
    APP_URL = os.environ.get('APP_URL', 'http://localhost:5000')
    SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', 'support@housemanager.co.ke')
    SUPPORT_PHONE = os.environ.get('SUPPORT_PHONE', '+254700000000')

    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-prod-abc123xyz')
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY', 'csrf-key-change-in-prod')
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
    BCRYPT_LOG_ROUNDS = int(os.environ.get('BCRYPT_LOG_ROUNDS', 13))

    # Session
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(seconds=int(os.environ.get('PERMANENT_SESSION_LIFETIME', 3600)))
    SESSION_PROTECTION = 'strong'

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://postgres:password@localhost:5432/house_management_db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 10,
        'max_overflow': 20,
    }

    # Cache
    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = os.environ.get('CACHE_REDIS_URL', 'redis://localhost:6379/1')
    CACHE_DEFAULT_TIMEOUT = 300
    CACHE_KEY_PREFIX = 'nyumba_'

    # Rate Limiting
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'redis://localhost:6379/2')
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', '200 per hour')
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_STRATEGY = 'fixed-window'

    # File Uploads
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(basedir, '..', 'uploads'))
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ALLOWED_DOC_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx'}
    ALLOWED_ALL_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_DOC_EXTENSIONS | {'mp4', 'mov', 'avi'}

    # Mail
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@housemanager.co.ke')

    # M-Pesa Daraja API
    MPESA_CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY', '')
    MPESA_CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET', '')
    MPESA_SHORTCODE = os.environ.get('MPESA_SHORTCODE', '174379')
    MPESA_PASSKEY = os.environ.get('MPESA_PASSKEY', '')
    MPESA_CALLBACK_URL = os.environ.get('MPESA_CALLBACK_URL', 'https://example.com/api/mpesa/callback')
    MPESA_ENV = os.environ.get('MPESA_ENV', 'sandbox')
    MPESA_BASE_URL = os.environ.get('MPESA_BASE_URL', 'https://sandbox.safaricom.co.ke')

    # Equity Bank
    EQUITY_API_KEY = os.environ.get('EQUITY_API_KEY', '')
    EQUITY_API_SECRET = os.environ.get('EQUITY_API_SECRET', '')
    EQUITY_ACCOUNT_NUMBER = os.environ.get('EQUITY_ACCOUNT_NUMBER', '')
    EQUITY_BASE_URL = os.environ.get('EQUITY_BASE_URL', 'https://api.equitybank.co.ke')

    # KCB Bank
    KCB_API_KEY = os.environ.get('KCB_API_KEY', '')
    KCB_API_SECRET = os.environ.get('KCB_API_SECRET', '')
    KCB_BASE_URL = os.environ.get('KCB_BASE_URL', 'https://uat.buni.kcbgroup.com')

    # Co-op Bank
    COOP_API_KEY = os.environ.get('COOP_API_KEY', '')
    COOP_API_SECRET = os.environ.get('COOP_API_SECRET', '')
    COOP_BASE_URL = os.environ.get('COOP_BASE_URL', 'https://developer.co-opbank.co.ke')

    # Africa's Talking
    AT_API_KEY = os.environ.get('AT_API_KEY', '')
    AT_USERNAME = os.environ.get('AT_USERNAME', 'sandbox')
    AT_SENDER_ID = os.environ.get('AT_SENDER_ID', 'NyumbaApp')

    # GeoIP
    GEOIP_DATABASE_PATH = os.environ.get('GEOIP_DATABASE_PATH', '/usr/local/share/GeoIP/GeoLite2-City.mmdb')

    # Celery
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/3')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/4')
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_ACCEPT_CONTENT = ['json']

    # Security Headers
    SECURITY_HEADERS = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Content-Security-Policy': (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' wss:;"
        ),
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'geolocation=(), microphone=(), camera=(self)',
    }

    # Pagination
    ITEMS_PER_PAGE = 20
    MAX_ITEMS_PER_PAGE = 100

    # Kenya-specific
    CURRENCY = 'KES'
    CURRENCY_SYMBOL = 'KSh'
    TIMEZONE = 'Africa/Nairobi'
    COUNTRY_CODE = 'KE'
    PHONE_PREFIX = '+254'


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = True
    BCRYPT_LOG_ROUNDS = 4
    CACHE_TYPE = 'SimpleCache'
    RATELIMIT_STORAGE_URL = 'memory://'


class TestingConfig(Config):
    DEBUG = False
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:password@localhost:5432/house_management_test'
    BCRYPT_LOG_ROUNDS = 4
    CACHE_TYPE = 'SimpleCache'
    RATELIMIT_STORAGE_URL = 'memory://'


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = 'https'
    BCRYPT_LOG_ROUNDS = 13


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
