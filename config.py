import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

_IS_PRODUCTION = os.environ.get('FLASK_ENV', 'development').lower() == 'production'


def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() == 'true'


def normalize_database_url(url):
    """Normalize Postgres URLs supplied by hosting providers.

    Handles Heroku/Render-style ``postgres://`` URLs and makes sure SSL
    mode is requested for every supported driver (psycopg2 and psycopg 3).
    """
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]

    if url.startswith(('postgresql://', 'postgresql+psycopg://', 'postgresql+psycopg2://')):
        if 'sslmode=' not in url:
            url += ('&' if '?' in url else '?') + 'sslmode=require'

    return url


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable must be set")

    _db_url = normalize_database_url(
        os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR}/shikshya.db')
    )
    SQLALCHEMY_DATABASE_URI = _db_url

    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Create tables / run bootstrap on startup. Disable in tests and migrations.
    AUTO_INIT_DB = True

    # Demo users, courses and other sample data are opt-in and must never be
    # enabled in production. Roles are always ensured separately so that
    # registration and the create-admin CLI work on an empty database.
    SEED_DEMO_DATA = os.environ.get('SEED_DEMO_DATA', 'False').lower() == 'true'

    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', _IS_PRODUCTION)
    SESSION_COOKIE_MAX_AGE = 60 * 60 * 12

    # Reject a session whose identity fingerprint changes (Flask-Login).
    SESSION_PROTECTION = 'strong'

    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_DURATION = timedelta(days=7)

    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    # Trust X-Forwarded-* only when the app is actually behind a reverse proxy.
    TRUST_PROXY_HEADERS = _env_bool('TRUST_PROXY_HEADERS', _IS_PRODUCTION)
    FORCE_HTTPS = _env_bool('FORCE_HTTPS', _IS_PRODUCTION)
    ENABLE_CSP_REPORT_ONLY = True
    CONTENT_SECURITY_POLICY_REPORT_ONLY = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'self'; "
        "object-src 'none'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com "
        "https://fonts.googleapis.com; "
        "font-src 'self' data: https://cdnjs.cloudflare.com "
        "https://fonts.gstatic.com; "
        "img-src 'self' data: blob: https:; "
        "media-src 'self' blob: https:; "
        "connect-src 'self';"
    )


    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "200 per day;50 per hour;10 per minute"
    # Flask-Limiter 3.x reads RATELIMIT_STORAGE_URI. Accept the older
    # RATELIMIT_STORAGE_URL name too so existing deployments keep working.
    RATELIMIT_STORAGE_URI = os.environ.get(
        'RATELIMIT_STORAGE_URI',
        os.environ.get('RATELIMIT_STORAGE_URL', 'memory://'),
    )
    RATELIMIT_STORAGE_URL = RATELIMIT_STORAGE_URI

    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', '')

    SITE_NAME = 'Shikshya'
    SITE_URL = os.environ.get('SITE_URL', 'http://localhost:5000')

    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', '')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', '')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', '')

    @staticmethod
    def init_app(app):
        upload_dirs = [
            'videos', 'assignments', 'avatars', 'certificates', 'thumbnails',
            'labs', 'evaluations', 'documents', 'lab_manuals',
        ]
        for d in upload_dirs:
            path = os.path.join(app.config['UPLOAD_FOLDER'], d)
            try:
                os.makedirs(path, exist_ok=True)
            except OSError as e:
                app.logger.error(f"Could not create upload directory {path}: {e}")
