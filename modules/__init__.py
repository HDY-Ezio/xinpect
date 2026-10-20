"""Xinpect modules package"""
from .constants import app, DB_PATH, logger  # noqa: F401
from .db import get_db, close_db, init_db, is_admin_user  # noqa: F401
from .helpers import login_required, get_current_user, is_vip_user  # noqa: F401

from .csrf_protection import generate_csrf_token
app.jinja_env.globals['csrf_token'] = generate_csrf_token
