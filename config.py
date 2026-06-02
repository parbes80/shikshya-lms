import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable must be set")

    _db_url = os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR}/shikshya.db')
    if _db_url.startswith('postgresql://') and '?sslmode' not in _db_url:
        _db_url += '?sslmode=require'
    SQLALCHEMY_DATABASE_URI = _db_url

    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_MAX_AGE = 86400 * 30

    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_DURATION = 86400 * 30

    PERMANENT_SESSION_LIFETIME = timedelta(days=30)

    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "200 per day;50 per hour;10 per minute"
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')

    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', '')

    SITE_NAME = 'Shikshya'
    SITE_URL = os.environ.get('SITE_URL', 'http://localhost:5000')

    @staticmethod
    def init_app(app):
        upload_dirs = ['videos', 'assignments', 'avatars', 'certificates', 'thumbnails', 'labs', 'evaluations']
        for d in upload_dirs:
            path = os.path.join(app.config['UPLOAD_FOLDER'], d)
            try:
                os.makedirs(path, exist_ok=True)
            except OSError as e:
                app.logger.error(f"Could not create upload directory {path}: {e}")
