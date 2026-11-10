"""Shared Flask extensions.

Kept in a separate module so blueprints can use the limiter without importing
the application factory (which would create a circular import).
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
