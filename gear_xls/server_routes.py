#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль с маршрутами для веб-сервера Flask.
"""

import json
import logging
import os
import re
import sys
from datetime import timedelta

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template_string,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from flask_cors import CORS

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(THIS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

from gear_xls.runtime_paths import (
    HEALTH_MARKER,
    ensure_runtime_dirs,
    get_excel_exports_dir,
    get_js_modules_dir,
    get_project_root,
    get_project_root_id,
    get_schedule_html_path,
    get_server_log_path,
    get_spiski_dir,
    get_static_dir,
    load_server_config,
    set_project_root_env,
)

from auth import authenticate, current_user, get_or_create_secret_key, login_required, role_required
import backup_manager
from excel_exporter import ExcelExportValidationError, process_schedule_export_request
import lock_manager
import restore_manager
import rooms_report
import rooms_routes
import state_manager
from base_schedule_manager import BaseRevisionConflict, BaseScheduleValidationError


def _build_log_handlers():
    ensure_runtime_dirs()
    handlers = [logging.FileHandler(get_server_log_path(), encoding="utf-8")]
    if _stdout_supports_text("Запуск Flask-сервера"):
        handlers.insert(0, logging.StreamHandler(sys.stdout))
    return handlers


def _stdout_supports_text(text: str) -> bool:
    stream = getattr(sys, "stdout", None)
    if stream is None:
        return False
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except Exception:
        return False
    return True


def configure_logging():
    if getattr(configure_logging, "_configured", False):
        return
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    for handler in _build_log_handlers():
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    configure_logging._configured = True


configure_logging()
logger = logging.getLogger("server_routes")

app = Flask(__name__)
app.secret_key = get_or_create_secret_key()
app.permanent_session_lifetime = timedelta(hours=8)
app.config["SESSION_COOKIE_NAME"] = f"schedgen_session_{get_project_root_id()}"
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
CORS(app, resources={r"/api/spiski/*": {"origins": "*"}})
JSON_AUTH_PATHS = {
    "/api/lock/status",
    "/api/lock/acquire",
    "/api/lock/release",
    "/api/lock/heartbeat",
    "/api/lock",
    "/api/status",
    "/api/blocks",
    "/api/columns",
    "/api/individual_lessons",
    "/api/schedule",
    "/api/schedule/publish",
    "/api/rooms/availability",
    "/api/backups",
    "/api/restore/status",
    "/api/restore/status/clear",
}
RESTORE_LOCKED_STATUS = 423
RESTORE_BLOCK_MESSAGE = (
    "\u0410\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440 "
    "\u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442 "
    "\u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435 "
    "\u0431\u0430\u0437\u044b \u0440\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u044f. "
    "\u0420\u0430\u0431\u043e\u0442\u0430 \u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e "
    "\u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d\u0430. "
    "\u0412\u044b \u0441\u043c\u043e\u0436\u0435\u0442\u0435 \u0437\u0430\u0439\u0442\u0438 "
    "\u043f\u043e\u0441\u043b\u0435 \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0438\u044f "
    "\u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f."
)


def _json_auth_path(path):
    return (
        path in JSON_AUTH_PATHS
        or path.startswith("/api/blocks/")
        or path.startswith("/api/backups/")
        or path.startswith("/api/restore/")
    )


@app.before_request
def ensure_json_401_for_lock_api():
    if _json_auth_path(request.path) and session.get("login") is None:
        return jsonify({"error": "Unauthorized"}), 401


@app.before_request
def csrf_same_origin_check():
    """Reject mutating requests whose Origin header does not match the server."""
    if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
        return
    if request.path in ("/login",):
        return
    origin = request.headers.get("Origin", "")
    if not origin:
        return  # No Origin: same-origin sendBeacon / form submit — allow
    scheme = "https" if request.is_secure else "http"
    expected = f"{scheme}://{request.host}"
    if origin != expected:
        logger.warning(
            "CSRF: rejected %s %s — Origin %r != %r",
            request.method, request.path, origin, expected,
        )
        return jsonify({"error": "Forbidden", "code": "CSRF_FAILED"}), 403


def _restore_blocks_requests(status):
    return bool(status.get("active") or status.get("recovery_required"))


def _restore_public_status(status):
    return {
        "active": bool(status.get("active")),
        "started_at": status.get("started_at"),
        "started_by": status.get("started_by"),
        "message": status.get("message"),
        "generation": int(status.get("generation") or 0),
        "last_completed_at": status.get("last_completed_at"),
        "last_completed_by": status.get("last_completed_by"),
        "last_restored_from": status.get("last_restored_from"),
        "recovery_required": bool(status.get("recovery_required")),
        "recovery_message": status.get("recovery_message"),
        "safety_backup_id": status.get("safety_backup_id"),
    }


def _restore_status_api_payload(status):
    public_status = _restore_public_status(status)
    return {
        "ok": True,
        "restore_in_progress": _restore_blocks_requests(status),
        **public_status,
    }


def _restore_status_summary(status):
    return {
        "active": bool(status.get("active")),
        "generation": int(status.get("generation") or 0),
        "last_completed_at": status.get("last_completed_at"),
        "recovery_required": bool(status.get("recovery_required")),
        "message": status.get("recovery_message") or status.get("message"),
    }


def _restore_error_payload(status):
    payload = {
        "ok": False,
        "error": "Restore in progress",
        "code": "RESTORE_IN_PROGRESS",
        "message": RESTORE_BLOCK_MESSAGE,
        "restore_generation": int(status.get("generation") or 0),
    }
    if status.get("recovery_required"):
        payload["recovery_required"] = True
        payload["recovery_message"] = status.get("recovery_message")
    return payload


def _restore_block_response(status):
    return jsonify(_restore_error_payload(status)), RESTORE_LOCKED_STATUS


def _individual_mutation_payload(result, include_revision=False):
    payload = {}
    cleanup_removed = int(getattr(result, "individual_cleanup_removed", 0) or 0)
    revision = getattr(result, "individual_revision", None)
    if include_revision and revision is not None:
        payload["individual_revision"] = revision
    if cleanup_removed:
        payload["individual_cleanup_removed"] = cleanup_removed
        payload["force_individual_refresh"] = True
        if revision is not None:
            payload["individual_revision"] = revision
    return payload


def _is_backup_download_path(path):
    return re.fullmatch(r"/api/backups/[^/]+/download", path or "") is not None


def _is_backup_restore_path(path):
    return re.fullmatch(r"/api/backups/[^/]+/restore", path or "") is not None


def _restore_request_allowed():
    path = request.path
    method = request.method
    role = session.get("role")

    if path.startswith("/static/") or path.startswith("/js_modules/"):
        return True
    if path in ("/login", "/logout", "/health"):
        return True
    if method == "GET" and path in ("/api/restore/status", "/api/status"):
        return True
    if method == "POST" and path == "/api/restore/status/clear":
        return True
    if role == "admin" and method == "GET" and path == "/api/backups":
        return True
    if role == "admin" and method == "GET" and _is_backup_download_path(path):
        return True
    if role == "admin" and method == "POST" and _is_backup_restore_path(path):
        return True
    return False


RESTORE_STATUS_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{{ title }}</title>
<style>
body{font-family:Arial,sans-serif;margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f4f6f8;color:#202124}
main{max-width:760px;padding:32px}
h1{font-size:24px;margin:0 0 16px}
p{font-size:17px;line-height:1.55}
pre{background:#fff;border:1px solid #d8dee4;border-radius:6px;padding:16px;overflow:auto}
.warning{color:#b3261e;font-weight:600}
</style>
</head>
<body>
<main>
<h1>{{ title }}</h1>
<p>{{ message }}</p>
{% if details %}<p class="{{ 'warning' if recovery_required else '' }}">{{ details }}</p>{% endif %}
{% if is_admin %}<pre>{{ status_json }}</pre>{% endif %}
</main>
</body>
</html>"""


def _restore_schedule_page(status):
    is_admin = session.get("role") == "admin"
    recovery_required = bool(status.get("recovery_required"))
    title = "Restore recovery required" if recovery_required and is_admin else "Restore in progress"
    details = status.get("recovery_message") or status.get("message")
    response = app.make_response(
        render_template_string(
            RESTORE_STATUS_PAGE_TEMPLATE,
            title=title,
            message=RESTORE_BLOCK_MESSAGE,
            details=details,
            recovery_required=recovery_required,
            is_admin=is_admin,
            status_json=json.dumps(
                _restore_status_api_payload(status),
                ensure_ascii=False,
                indent=2,
            ),
        )
    )
    response.status_code = RESTORE_LOCKED_STATUS
    response.headers["Cache-Control"] = "no-store"
    return response


@app.before_request
def block_requests_during_restore():
    status = restore_manager.get_restore_status()
    if not _restore_blocks_requests(status):
        return
    if _restore_request_allowed():
        return
    if request.path == "/schedule" and request.method == "GET":
        if session.get("login") is None:
            return
        return _restore_schedule_page(status)
    if request.path.startswith("/api/") or request.path == "/export_to_excel":
        return _restore_block_response(status)


@app.after_request
def set_no_store_for_api(response):
    if request.path.startswith("/api/") or request.path == "/schedule":
        response.headers["Cache-Control"] = "no-store"
    return response

LOGIN_PAGE_TEMPLATE = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<title>Вход - SchedGen</title>
<style>
body{font-family:sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;background:#f5f5f5}
.login-box{background:#fff;padding:2rem;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.15);width:320px}
h2{margin-top:0}input{width:100%;box-sizing:border-box;padding:.5rem;margin:.5rem 0 1rem;border:1px solid #ccc;border-radius:4px}
button{width:100%;padding:.6rem;background:#1a73e8;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:1rem}
.error{color:red;margin-bottom:1rem}
</style></head><body>
<div class="login-box">
<h2>SchedGen - Вход</h2>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post">
<label>Логин<input name="login" type="text" autocomplete="username" required></label>
<label>Пароль<input name="password" type="password" autocomplete="current-password" required></label>
<button type="submit">Войти</button>
</form>
</div></body></html>"""
ROOMS_PAGE_TEMPLATE = rooms_routes.ROOMS_PAGE_TEMPLATE

EXCEL_EXPORTS_DIR = get_excel_exports_dir()
SPISKI_DIR = get_spiski_dir()
SPISKI_FILE_MAP = {
    "subjects": "disciplins.txt",
    "groups": "groups.txt",
    "teachers": "teachers.txt",
    "rooms_Villa": "kabinets_Villa.txt",
    "rooms_Kolibri": "kabinets_Kolibri.txt",
}

rooms_routes.configure(login_required, current_user, rooms_report, ROOMS_PAGE_TEMPLATE)
app.register_blueprint(rooms_routes.bp)


def _spiski_sort_key(value):
    """Case-insensitive natural sort key (e.g. '2' < '10')."""
    parts = re.findall(r"\d+|\D+", (value or "").strip())
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.casefold()))
    return tuple(key)


def _load_spiski_data():
    result = {}
    for key, filename in SPISKI_FILE_MAP.items():
        filepath = os.path.join(SPISKI_DIR, filename)
        entries = []
        seen = set()
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    item = line.strip()
                    if not item:
                        continue
                    item_key = item.casefold()
                    if item_key in seen:
                        continue
                    seen.add(item_key)
                    entries.append(item)
        except FileNotFoundError:
            logger.warning("Spiski file not found (using empty list): %s", filepath)
        except Exception as exc:
            logger.warning("Error reading spiski file %s: %s", filepath, exc)
        result[key] = sorted(entries, key=_spiski_sort_key)
    return result


def _build_spiski_data_js(spiski_data):
    return (
        "var spiskiData = {\n"
        f'    "subjects": {json.dumps(spiski_data.get("subjects", []), ensure_ascii=False)},\n'
        f'    "groups": {json.dumps(spiski_data.get("groups", []), ensure_ascii=False)},\n'
        f'    "teachers": {json.dumps(spiski_data.get("teachers", []), ensure_ascii=False)},\n'
        f'    "rooms_Villa": {json.dumps(spiski_data.get("rooms_Villa", []), ensure_ascii=False)},\n'
        f'    "rooms_Kolibri": {json.dumps(spiski_data.get("rooms_Kolibri", []), ensure_ascii=False)}\n'
        "};\n"
        "window.spiskiData = spiskiData;"
    )


def _inject_latest_spiski_data(html):
    fresh_spiski_js = _build_spiski_data_js(_load_spiski_data())
    updated_html, replacements = re.subn(
        r"var spiskiData = \{.*?\};\s*window\.spiskiData = spiskiData;",
        fresh_spiski_js,
        html,
        count=1,
        flags=re.S,
    )
    if replacements == 0:
        logger.warning("Failed to replace embedded spiskiData in schedule HTML")
        return html
    return updated_html


os.makedirs(EXCEL_EXPORTS_DIR, exist_ok=True)
logger.info("Excel export directory ready: %s", EXCEL_EXPORTS_DIR)


@app.route("/js_modules/<path:filename>")
def serve_js_modules(filename):
    return send_from_directory(get_js_modules_dir(), filename)


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(get_static_dir(), filename)


@app.route("/login", methods=["GET", "POST"])
def login():
    error_msg = None
    if request.method == "POST":
        login_value = (request.form.get("login") or "").strip()
        password = request.form.get("password") or ""
        user = authenticate(login_value, password)
        if user:
            session.permanent = True
            session["login"] = user.get("login")
            session["display_name"] = user.get("display_name")
            session["role"] = user.get("role")
            return redirect(url_for("schedule"))
        error_msg = "Неверный логин или пароль"
    return render_template_string(LOGIN_PAGE_TEMPLATE, error=error_msg)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/schedule")
@login_required
def schedule():
    html_path = get_schedule_html_path()
    if not os.path.exists(html_path):
        stub = (
            "<html><body><p>Расписание ещё не создано. "
            "Попросите Аллу сгенерировать расписание.</p></body></html>"
        )
        response = app.make_response(stub)
        response.headers["Cache-Control"] = "no-store"
        return response

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    html = _inject_latest_spiski_data(html)

    user = current_user()
    published_base_available = state_manager.get_base_revision() is not None
    injection = (
        "<script>\n"
        f"  window.CURRENT_USER = {json.dumps(user['login'])};\n"
        f"  window.USER_ROLE = {json.dumps(user['role'])};\n"
        f"  window.DISPLAY_NAME = {json.dumps(user['display_name'])};\n"
        f'  window.PUBLISHED_BASE_AVAILABLE = {"true" if published_base_available else "false"};\n'
        "</script>\n"
        '<link rel="stylesheet" href="/static/nav.css">\n'
    )
    if "</head>" in html:
        html = html.replace("</head>", injection + "</head>", 1)
    else:
        html = injection + html

    auth_ui_tag = (
        '<script src="/static/auth_ui.js"></script>\n'
        '<script src="/static/base_sync_ui.js"></script>\n'
        '<script src="/static/lock_ui.js"></script>\n'
        '<script src="/js_modules/trial_ui.js"></script>\n'
        '<script src="/js_modules/conflict_detector.js?v=20260527_1"></script>\n'
        '<script src="/static/individual_ui.js"></script>\n'
        # Load the search scaffold after the existing schedule UI so it can
        # reuse the injected nav slot and exposed auth/base/individual APIs.
        '<script src="/static/schedule_search_ui.js"></script>\n'
        '<script src="/static/rooms_schedule_focus.js?v=20260521_3"></script>\n'
        '<script src="/static/backup_ui.js"></script>\n'
    )
    if "</body>" in html:
        html = html.replace("</body>", auth_ui_tag + "</body>", 1)
    else:
        html += auth_ui_tag

    response = app.make_response(html)
    response.headers["Cache-Control"] = "no-store"
    return response


def _require_lock(login):
    state = lock_manager.get_lock_status()
    if state.get("holder") != login:
        return {"ok": False, "error": "No active lock", "code": "NO_LOCK"}
    return None


def _backup_error_response(exc):
    status = getattr(exc, "status_code", 400)
    return (
        jsonify(
            {
                "ok": False,
                "error": getattr(exc, "message", str(exc)),
                "code": getattr(exc, "code", "BACKUP_ERROR"),
            }
        ),
        status,
    )


def _restore_manager_error_response(exc):
    status = getattr(exc, "status_code", 400)
    payload = {
        "ok": False,
        "error": getattr(exc, "message", str(exc)),
        "code": getattr(exc, "code", "RESTORE_ERROR"),
    }
    payload.update(getattr(exc, "payload", {}) or {})
    return jsonify(payload), status


def _restore_in_progress():
    return restore_manager.is_restore_active()


@app.route("/api/lock/status")
@login_required
def api_lock_status():
    state = lock_manager.get_lock_status()
    return jsonify(state)


@app.route("/api/lock/acquire", methods=["POST"])
@login_required
def api_lock_acquire():
    user = current_user()
    if user["role"] not in ("admin", "editor", "organizer"):
        return jsonify({"ok": False, "error": "Forbidden", "code": "FORBIDDEN"}), 403
    result = lock_manager.acquire_lock(user["login"])
    return jsonify(result)


@app.route("/api/lock/release", methods=["POST"])
@login_required
def api_lock_release():
    data = request.get_json(force=True, silent=True) or {}
    version = data.get("version")
    user = current_user()
    if version is None:
        return jsonify({"ok": False, "error": "version required"}), 400
    try:
        version = int(version)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid version"}), 400
    result = lock_manager.release_lock(user["login"], version)
    return jsonify(result)


@app.route("/api/lock/heartbeat", methods=["POST"])
@login_required
def api_lock_heartbeat():
    data = request.get_json(force=True, silent=True) or {}
    version = data.get("version")
    user = current_user()
    if version is None:
        return jsonify({"ok": False, "error": "version required"}), 400
    try:
        version = int(version)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid version"}), 400
    result = lock_manager.heartbeat(user["login"], version)
    return jsonify(result)


@app.route("/api/lock", methods=["DELETE"])
@login_required
def api_lock_force_release():
    user = current_user()
    if user["role"] != "admin":
        return jsonify({"ok": False, "error": "Forbidden", "code": "FORBIDDEN"}), 403
    result = lock_manager.force_release(user["login"])
    return jsonify(result)


@app.route("/api/status")
@login_required
def api_status():
    lock_state = lock_manager.get_lock_status()
    restore_status = restore_manager.get_restore_status()
    restore_blocks = _restore_blocks_requests(restore_status)
    return jsonify(
        {
            "lock": {
                "holder": lock_state.get("holder"),
                "version": lock_state.get("version"),
                "acquired_at": lock_state.get("acquired_at"),
                "last_heartbeat": lock_state.get("last_heartbeat"),
            },
            "base_revision": state_manager.get_base_revision(),
            "individual_revision": state_manager.get_individual_revision(
                prune_expired=not restore_blocks
            ),
            "base_updated": False,
            "restore": _restore_status_summary(restore_status),
        }
    )


@app.route("/api/restore/status", methods=["GET"])
@login_required
def api_restore_status():
    return jsonify(_restore_status_api_payload(restore_manager.get_restore_status()))


@app.route("/api/restore/status/clear", methods=["POST"])
@login_required
@role_required("admin")
def api_restore_status_clear():
    data = request.get_json(force=True, silent=True) or {}
    user = current_user()
    previous_status = restore_manager.get_restore_status()
    try:
        status = restore_manager.clear_restore_status(
            confirm=data.get("confirm") is True,
            cleared_by=user["login"],
        )
    except restore_manager.RestoreStatusError as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": exc.message,
                    "code": exc.code,
                }
            ),
            exc.status_code,
        )

    logger.warning(
        "Restore status clear endpoint used by admin=%s recovery_required=%s stale=%s",
        user["login"],
        bool(previous_status.get("recovery_required")),
        restore_manager.is_restore_stale(previous_status),
    )
    return jsonify({"ok": True, "status": _restore_status_api_payload(status)})


@app.route("/api/backups", methods=["GET"])
@login_required
@role_required("admin")
def api_backups_list():
    return jsonify({"ok": True, "backups": backup_manager.list_backups()})


@app.route("/api/backups", methods=["POST"])
@login_required
@role_required("admin")
def api_backups_create():
    if _restore_in_progress():
        return _restore_block_response(restore_manager.get_restore_status())
    data = request.get_json(force=True, silent=True) or {}
    user = current_user()
    try:
        backup = backup_manager.create_backup(
            user["login"],
            user.get("display_name") or user["login"],
            comment=data.get("comment", ""),
            backup_kind="manual",
        )
    except backup_manager.BackupError as exc:
        return _backup_error_response(exc)
    except Exception as exc:
        logger.exception("Unexpected backup creation error")
        return jsonify({"ok": False, "error": str(exc), "code": "BACKUP_CREATE_FAILED"}), 500
    return jsonify(
        {
            "ok": True,
            "backup": {
                "id": backup["id"],
                "filename": backup["filename"],
                "backup_kind": backup["backup_kind"],
                "download_url": backup["download_url"],
            },
        }
    )


@app.route("/api/backups/upload", methods=["POST"])
@login_required
@role_required("admin")
def api_backups_upload():
    if _restore_in_progress():
        return _restore_block_response(restore_manager.get_restore_status())

    uploaded_file = request.files.get("file")
    user = current_user()
    try:
        backup = backup_manager.store_uploaded_backup(
            uploaded_file.stream if uploaded_file is not None else None,
            uploaded_file.filename if uploaded_file is not None else "",
            user["login"],
            user.get("display_name") or user["login"],
        )
    except backup_manager.BackupError as exc:
        return _backup_error_response(exc)
    except Exception as exc:
        logger.exception("Unexpected backup upload error")
        return jsonify({"ok": False, "error": str(exc), "code": "BACKUP_UPLOAD_FAILED"}), 500

    warnings = []
    if backup.get("project_root_matches") is False:
        warnings.append("PROJECT_ROOT_MISMATCH")

    return jsonify(
        {
            "ok": True,
            "backup": {
                "id": backup["id"],
                "filename": backup["filename"],
                "backup_kind": backup["backup_kind"],
                "project_root_matches": backup["project_root_matches"],
                "download_url": backup["download_url"],
            },
            "warnings": warnings,
        }
    )


@app.route("/api/backups/<backup_id>/download", methods=["GET"])
@login_required
@role_required("admin")
def api_backup_download(backup_id):
    try:
        path = backup_manager.get_backup_path(backup_id)
    except backup_manager.BackupError as exc:
        return _backup_error_response(exc)
    if not os.path.exists(path):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Backup not found",
                    "code": "BACKUP_NOT_FOUND",
                }
            ),
            404,
        )
    filename = os.path.basename(path)
    return send_file(
        path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/zip",
    )


@app.route("/api/backups/<backup_id>/restore", methods=["POST"])
@login_required
@role_required("admin")
def api_backup_restore(backup_id):
    data = request.get_json(force=True, silent=True) or {}
    if data.get("confirm") is not True:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Explicit confirmation is required",
                    "code": "CONFIRM_REQUIRED",
                }
            ),
            400,
        )
    if _restore_in_progress():
        return _restore_block_response(restore_manager.get_restore_status())

    user = current_user()
    lock_state = lock_manager.get_lock_status()
    if lock_state.get("holder") != user["login"]:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Active edit lock held by the current admin is required",
                    "code": "NO_LOCK",
                    "lock_holder": lock_state.get("holder"),
                }
            ),
            403,
        )

    try:
        result = restore_manager.restore_backup(
            backup_id,
            user["login"],
            user.get("display_name") or user["login"],
            allow_foreign_project=data.get("allow_foreign_project") is True,
        )
    except restore_manager.RestoreError as exc:
        return _restore_manager_error_response(exc)
    except backup_manager.BackupError as exc:
        return _backup_error_response(exc)
    except Exception as exc:
        logger.exception("Unexpected restore error")
        return jsonify({"ok": False, "error": str(exc), "code": "RESTORE_FAILED"}), 500
    return jsonify(result)


@app.route("/api/individual_lessons")
@login_required
def api_individual_lessons():
    return jsonify(state_manager.get_individual_lessons())


@app.route("/api/schedule")
@login_required
def api_schedule():
    base = state_manager.get_base_schedule()
    ind = state_manager.get_individual_lessons()
    published_base_available = base.get("published_at") is not None
    return jsonify(
        {
            "base": base.get("blocks", []),
            "individual": ind.get("blocks", []),
            "base_revision": base.get("published_at"),
            "individual_revision": ind.get("last_modified"),
            "published_base_available": published_base_available,
        }
    )


@app.route("/api/schedule/publish", methods=["POST"])
@login_required
def api_publish_schedule():
    user = current_user()
    if user["role"] != "admin":
        return jsonify({"ok": False, "error": "Forbidden", "code": "FORBIDDEN"}), 403
    err = _require_lock(user["login"])
    if err:
        logger.warning(
            "Publish rejected without active lock: login=%s code=%s",
            user["login"],
            err.get("code"),
        )
        return jsonify(err), 403
    data = request.get_json(force=True, silent=True) or {}
    blocks = data.get("blocks", [])
    if not isinstance(blocks, list):
        logger.warning("Publish rejected due to invalid payload: blocks is not a list")
        return jsonify({"ok": False, "error": "blocks must be a list"}), 400
    if "expected_base_revision" not in data:
        logger.warning("Publish rejected due to missing expected_base_revision")
        return jsonify(
            {
                "ok": False,
                "error": "expected_base_revision required",
                "code": "EXPECTED_BASE_REVISION_REQUIRED",
            }
        ), 400
    try:
        result = state_manager.publish_base(
            blocks,
            user["login"],
            expected_base_revision=data.get("expected_base_revision"),
        )
    except BaseRevisionConflict as exc:
        logger.warning(
            "Publish rejected due to base revision conflict: login=%s expected=%r current=%r",
            user["login"],
            exc.expected_revision,
            exc.current_revision,
        )
        return jsonify(
            {
                "ok": False,
                "error": "Base schedule has a newer revision",
                "code": "BASE_REVISION_CONFLICT",
                "current_base_revision": exc.current_revision,
            }
        ), 409
    except BaseScheduleValidationError as exc:
        logger.warning(
            "Publish rejected due to invalid base block day: login=%s code=%s error=%s",
            user["login"],
            exc.code,
            exc.message,
        )
        return jsonify(
            {
                "ok": False,
                "error": exc.message,
                "code": exc.code,
            }
        ), 400
    return jsonify(
        {
            "ok": True,
            "published_at": result["published_at"],
            "base_revision": result["published_at"],
            "group_blocks_saved": len(result["blocks"]),
            "changed": result.get("changed", True),
        }
    )


@app.route("/api/blocks", methods=["POST"])
@login_required
def api_create_block():
    user = current_user()
    if user["role"] not in ("admin", "editor", "organizer"):
        return jsonify({"ok": False, "error": "Forbidden", "code": "FORBIDDEN"}), 403
    err = _require_lock(user["login"])
    if err:
        return jsonify(err), 403
    data = request.get_json(force=True, silent=True) or {}
    result = state_manager.add_block(data, user["role"])
    block, error = result
    if error:
        payload = {"ok": False, "error": error, "code": "VALIDATION_ERROR"}
        payload.update(_individual_mutation_payload(result))
        return jsonify(payload), 400
    return jsonify(
        {
            "ok": True,
            "block": block,
            **_individual_mutation_payload(result, include_revision=True),
        }
    )


@app.route("/api/blocks/<block_id>", methods=["PUT"])
@login_required
def api_update_block(block_id):
    user = current_user()
    if user["role"] not in ("admin", "editor", "organizer"):
        return jsonify({"ok": False, "error": "Forbidden", "code": "FORBIDDEN"}), 403
    err = _require_lock(user["login"])
    if err:
        return jsonify(err), 403
    data = request.get_json(force=True, silent=True) or {}
    result = state_manager.update_block(block_id, data, user["role"])
    block, error = result
    if error == "EXPIRED_TRIAL_PRUNED":
        payload = {"ok": False, "error": "Block expired and was pruned", "code": "EXPIRED_TRIAL_PRUNED"}
        payload.update(_individual_mutation_payload(result))
        return jsonify(payload), 404
    if error == "NOT_FOUND":
        payload = {"ok": False, "error": "Block not found", "code": "NOT_FOUND"}
        payload.update(_individual_mutation_payload(result))
        return jsonify(payload), 404
    if error:
        payload = {"ok": False, "error": error, "code": "VALIDATION_ERROR"}
        payload.update(_individual_mutation_payload(result))
        return jsonify(payload), 400
    return jsonify(
        {
            "ok": True,
            "block": block,
            **_individual_mutation_payload(result, include_revision=True),
        }
    )


@app.route("/api/blocks/<block_id>", methods=["DELETE"])
@login_required
def api_delete_block(block_id):
    user = current_user()
    if user["role"] not in ("admin", "editor", "organizer"):
        return jsonify({"ok": False, "error": "Forbidden", "code": "FORBIDDEN"}), 403
    err = _require_lock(user["login"])
    if err:
        return jsonify(err), 403
    result = state_manager.delete_block(block_id, user["role"])
    deleted, del_err = result
    if del_err == "FORBIDDEN":
        payload = {"ok": False, "error": "Forbidden lesson_type", "code": "FORBIDDEN"}
        payload.update(_individual_mutation_payload(result))
        return jsonify(payload), 403
    if del_err == "EXPIRED_TRIAL_PRUNED":
        payload = {"ok": False, "error": "Block expired and was pruned", "code": "EXPIRED_TRIAL_PRUNED"}
        payload.update(_individual_mutation_payload(result))
        return jsonify(payload), 404
    if not deleted:
        payload = {"ok": False, "error": "Block not found", "code": "NOT_FOUND"}
        payload.update(_individual_mutation_payload(result))
        return jsonify(payload), 404
    return jsonify(
        {
            "ok": True,
            **_individual_mutation_payload(result, include_revision=True),
        }
    )


@app.route("/api/blocks/<block_id>/convert", methods=["POST"])
@login_required
def api_convert_block(block_id):
    user = current_user()
    if user["role"] not in ("admin", "editor", "organizer"):
        return jsonify({"ok": False, "error": "Forbidden", "code": "FORBIDDEN"}), 403
    err = _require_lock(user["login"])
    if err:
        return jsonify(err), 403
    result = state_manager.convert_block_to_regular(block_id, user["role"])
    block, error = result
    if error == "EXPIRED_TRIAL_PRUNED":
        payload = {"ok": False, "error": "Block expired and was pruned", "code": "EXPIRED_TRIAL_PRUNED"}
        payload.update(_individual_mutation_payload(result))
        return jsonify(payload), 404
    if error == "NOT_FOUND":
        payload = {"ok": False, "error": "Block not found", "code": "NOT_FOUND"}
        payload.update(_individual_mutation_payload(result))
        return jsonify(payload), 404
    if error == "NOT_TRIAL":
        payload = {"ok": False, "error": "Block is not a trial lesson", "code": "NOT_TRIAL"}
        payload.update(_individual_mutation_payload(result))
        return jsonify(payload), 400
    if error == "FORBIDDEN":
        payload = {"ok": False, "error": "Forbidden", "code": "FORBIDDEN"}
        payload.update(_individual_mutation_payload(result))
        return jsonify(payload), 403
    if error:
        payload = {"ok": False, "error": error}
        payload.update(_individual_mutation_payload(result))
        return jsonify(payload), 400
    return jsonify(
        {
            "ok": True,
            "block": block,
            **_individual_mutation_payload(result, include_revision=True),
        }
    )


@app.route("/api/columns", methods=["POST"])
@login_required
def api_add_column():
    user = current_user()
    if user["role"] not in ("admin", "editor", "organizer"):
        return jsonify({"ok": False, "error": "Forbidden", "code": "FORBIDDEN"}), 403
    err = _require_lock(user["login"])
    if err:
        return jsonify(err), 403
    data = request.get_json(force=True, silent=True) or {}
    building = (data.get("building") or "").strip()
    day = (data.get("day") or "").strip()
    room = (data.get("room") or "").strip()
    if not building or not day or not room:
        return jsonify({"ok": False, "error": "building, day, room required"}), 400
    return jsonify({"ok": True})


@app.route("/api/columns", methods=["DELETE"])
@login_required
def api_delete_column():
    user = current_user()
    if user["role"] not in ("admin", "editor", "organizer"):
        return jsonify({"ok": False, "error": "Forbidden", "code": "FORBIDDEN"}), 403
    err = _require_lock(user["login"])
    if err:
        return jsonify(err), 403
    data = request.get_json(force=True, silent=True) or {}
    building = (data.get("building") or "").strip()
    day = (data.get("day") or "").strip()
    room = (data.get("room") or "").strip()
    if not building or not day or not room:
        return jsonify({"ok": False, "error": "building, day, room required"}), 400
    if user["role"] == "editor" and state_manager.base_has_group_lessons_in_column(
        building, day, room
    ):
        return jsonify(
            {
                "ok": False,
                "error": "Column contains group lessons",
                "code": "COLUMN_HAS_GROUP_LESSONS",
            }
        ), 403
    if user["role"] == "organizer":
        if state_manager.base_has_group_lessons_in_column(building, day, room):
            return jsonify(
                {
                    "ok": False,
                    "error": "Column contains group lessons",
                    "code": "COLUMN_HAS_GROUP_LESSONS",
                }
            ), 403
        if state_manager.individual_column_has_non_trial_blocks(building, day, room):
            return jsonify(
                {
                    "ok": False,
                    "error": "Column contains non-trial lessons",
                    "code": "COLUMN_HAS_NON_TRIAL_BLOCKS",
                }
            ), 403
    result = state_manager.delete_column_blocks(building, day, room)
    count, _error = result
    return jsonify(
        {
            "ok": True,
            "blocks_removed": count,
            **_individual_mutation_payload(result, include_revision=True),
        }
    )


@app.route("/")
def index():
    logger.info("Получен запрос к корневому маршруту")
    return "Excel Export Server is running! Access /export_to_excel via POST request to export schedule."


@app.route("/health")
def health():
    root = get_project_root()
    config = load_server_config(root, include_env=True)
    return jsonify(
        {
            "ok": True,
            "marker": HEALTH_MARKER,
            "project_root": root,
            "project_root_id": get_project_root_id(root),
            "host": config["host"],
            "port": config["port"],
        }
    )


@app.route("/export_to_excel", methods=["POST"])
@login_required
@role_required("admin")
def export_to_excel():
    try:
        schedule_data_json = request.form.get("schedule_data")
        csrf_token = request.form.get("csrf_token", "")

        if not schedule_data_json:
            logger.error("Данные расписания не получены")
            return jsonify({"error": "Данные расписания не получены"}), 400

        logger.info(
            "Получены данные для экспорта в Excel (CSRF: %s)",
            csrf_token[:8] if csrf_token else "отсутствует",
        )
        logger.info("Размер данных: %s байт", len(schedule_data_json))

        output_file = process_schedule_export_request(schedule_data_json, EXCEL_EXPORTS_DIR)
        if not output_file or not os.path.exists(output_file):
            logger.error("Не удалось создать Excel-файл")
            return jsonify({"error": "Не удалось создать Excel-файл"}), 500

        logger.info("Файл готов к отправке: %s", output_file)
        response = send_file(
            output_file,
            as_attachment=True,
            download_name=os.path.basename(output_file),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        logger.info("Excel-файл успешно отправлен: %s", output_file)
        return response

    except ExcelExportValidationError as e:
        logger.warning("Excel export validation failed: %s", e.message)
        return jsonify({"error": e.message, "code": e.code}), 400
    except Exception as e:
        logger.error("Ошибка при экспорте в Excel: %s", e)
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/spiski/add", methods=["POST"])
@login_required
def add_spiski_item():
    try:
        data = request.get_json(force=True, silent=True) or {}
        key = (data.get("key", "") or "").strip()
        value = (data.get("value", "") or "").strip()

        if not key or not value:
            return jsonify({"error": "key and value are required"}), 400
        if len(value) > 200:
            return jsonify({"error": "value too long"}), 400
        if "\n" in value or "\r" in value:
            return jsonify({"error": "value must be a single line"}), 400

        filename = SPISKI_FILE_MAP.get(key)
        if not filename:
            return jsonify({"error": f"Unknown spiski key: {key}"}), 400

        filepath = os.path.join(SPISKI_DIR, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        existing = set()
        entries = []
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    item = line.strip()
                    if not item:
                        continue
                    low = item.casefold()
                    if low in existing:
                        continue
                    existing.add(low)
                    entries.append(item)

        if value.casefold() in existing:
            return jsonify({"ok": True, "added": False, "reason": "already_exists"})

        entries.append(value)
        entries.sort(key=_spiski_sort_key)

        with open(filepath, "w", encoding="utf-8") as f:
            if entries:
                f.write("\n".join(entries) + "\n")

        logger.info("Spiski: added %r to %s", value, filename)
        return jsonify({"ok": True, "added": True})

    except Exception as e:
        logger.error("Error in add_spiski_item: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/spiski/add", methods=["OPTIONS"])
def add_spiski_item_options():
    response = app.make_default_options_response()
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
    return response


@app.route("/export_to_excel", methods=["OPTIONS"])
def export_to_excel_options():
    return app.make_default_options_response()


def run_server(host=None, port=None, project_root=None):
    root = set_project_root_env(project_root)
    ensure_runtime_dirs(root)
    os.makedirs(get_excel_exports_dir(root), exist_ok=True)
    config = load_server_config(root, include_env=True)
    host = host or config["host"]
    port = int(port or config["port"])
    os.environ["HOST"] = str(host)
    os.environ["PORT"] = str(port)
    logger.info("Запуск Flask-сервера на %s:%s (project_root=%s)", host, port, root)
    if getattr(sys, "stdout", None) is not None:
        print(f"=== Flask export server starting on {host}:{port} ===")
        print(f"=== Log file: {get_server_log_path(root)} ===")
    app.run(debug=False, host=host, port=port)


if __name__ == "__main__":
    run_server()
