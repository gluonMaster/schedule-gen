import functools
import json
import logging
import os
import secrets
import sys

import bcrypt
from flask import jsonify, redirect, request, session, url_for

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(THIS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from gear_xls.runtime_paths import get_secret_key_path, get_users_json_path


SESSION_LIFETIME_HOURS = 8

logger = logging.getLogger(__name__)


def load_users() -> list[dict]:
    users_path = get_users_json_path()
    if not os.path.exists(users_path):
        logger.warning("Users config not found: %s", users_path)
        return []

    try:
        with open(users_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning("Failed to load users config: %s", exc)
        return []

    users = data.get("users", [])
    return users if isinstance(users, list) else []


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def authenticate(login: str, password: str) -> dict | None:
    for user in load_users():
        if user.get("login") != login:
            continue
        if not verify_password(password, user.get("password_hash", "")):
            return None
        sanitized = dict(user)
        sanitized.pop("password_hash", None)
        return sanitized
    return None


def get_or_create_secret_key() -> str:
    secret_key_path = get_secret_key_path()
    if os.path.exists(secret_key_path):
        with open(secret_key_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    os.makedirs(os.path.dirname(secret_key_path), exist_ok=True)
    secret_key = secrets.token_hex(32)
    with open(secret_key_path, "w", encoding="utf-8") as f:
        f.write(secret_key)
    return secret_key


def _wants_json_response() -> bool:
    accept_header = request.headers.get("Accept", "")
    return request.is_json or "application/json" in accept_header


def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("login") is None:
            if _wants_json_response():
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapper


def role_required(*roles):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("role") not in roles:
                return jsonify({"error": "Forbidden", "code": "FORBIDDEN"}), 403
            return f(*args, **kwargs)

        return wrapper

    return decorator


def current_user() -> dict:
    return {
        "login": session.get("login"),
        "display_name": session.get("display_name"),
        "role": session.get("role"),
    }
