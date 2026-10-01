import json
import logging
import os
import sys
import tempfile
import threading
from datetime import datetime, timedelta

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(THIS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from gear_xls.runtime_paths import get_lock_json_path


LOCK_TIMEOUT_MINUTES = 30
_lock_mutex = threading.Lock()
logger = logging.getLogger(__name__)


def _lock_json_path(project_root=None):
    return get_lock_json_path(project_root)


def _empty_lock_state():
    return {
        "holder": None,
        "version": 0,
        "acquired_at": None,
        "last_heartbeat": None,
        "last_holder": None,
        "released_at": None,
        "released_by": None,
        "release_reason": None,
    }


def _read_lock(project_root=None):
    lock_json_path = _lock_json_path(project_root)
    if not os.path.exists(lock_json_path):
        return _empty_lock_state()
    try:
        with open(lock_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        state = _empty_lock_state()
        if isinstance(data, dict):
            state.update({key: data.get(key) for key in state})
        state["version"] = int(state.get("version") or 0)
        return state
    except Exception as exc:
        logger.warning("Failed to read lock state: %s", exc)
        return _empty_lock_state()


def _write_lock(state, project_root=None):
    lock_json_path = _lock_json_path(project_root)
    directory = os.path.dirname(lock_json_path)
    os.makedirs(directory, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=directory, delete=False, suffix=".tmp", mode="w", encoding="utf-8"
        ) as tmp:
            json.dump(state, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name
        os.replace(tmp_path, lock_json_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _is_expired(state):
    if not state.get("holder") or not state.get("last_heartbeat"):
        return False
    try:
        last_heartbeat = datetime.fromisoformat(state["last_heartbeat"])
    except ValueError:
        return False
    return datetime.utcnow() - last_heartbeat > timedelta(minutes=LOCK_TIMEOUT_MINUTES)


def _clear_lock(state, reason, released_by=None):
    previous_holder = state.get("holder")
    state["holder"] = None
    state["version"] = int(state.get("version") or 0) + 1
    state["acquired_at"] = None
    state["last_heartbeat"] = None
    state["last_holder"] = previous_holder
    state["released_at"] = datetime.utcnow().isoformat()
    state["released_by"] = released_by
    state["release_reason"] = reason


def get_lock_status(project_root=None):
    with _lock_mutex:
        state = _read_lock(project_root)
        if _is_expired(state):
            _clear_lock(state, "timeout")
            _write_lock(state, project_root)
        return state


def acquire_lock(login, project_root=None):
    with _lock_mutex:
        state = _read_lock(project_root)
        if _is_expired(state):
            _clear_lock(state, "timeout")
        if state.get("holder") is not None:
            return {
                "ok": False,
                "holder": state.get("holder"),
                "acquired_at": state.get("acquired_at"),
                "version": state.get("version"),
            }
        now = datetime.utcnow().isoformat()
        state["holder"] = login
        state["version"] = int(state.get("version") or 0) + 1
        state["acquired_at"] = now
        state["last_heartbeat"] = now
        state["released_at"] = None
        state["released_by"] = None
        state["release_reason"] = None
        _write_lock(state, project_root)
        return {"ok": True, "holder": login, "version": state["version"]}


def release_lock(login, version, project_root=None):
    with _lock_mutex:
        state = _read_lock(project_root)
        if state.get("holder") != login:
            return {"ok": False, "error": "Not the lock holder"}
        if state.get("version") != version:
            return {"ok": False, "error": "Version mismatch"}
        _clear_lock(state, "released", released_by=login)
        _write_lock(state, project_root)
        return {"ok": True, "version": state["version"]}


def heartbeat(login, version, project_root=None):
    with _lock_mutex:
        state = _read_lock(project_root)
        if _is_expired(state):
            expired_holder = state.get("holder")
            _clear_lock(state, "timeout")
            _write_lock(state, project_root)
            if expired_holder == login:
                return {
                    "ok": False,
                    "reason": "lock_expired",
                    "current_version": state["version"],
                }
        if state.get("holder") != login or state.get("version") != version:
            if state.get("release_reason") == "force_released" and state.get("last_holder") == login:
                return {
                    "ok": False,
                    "reason": "force_released",
                    "current_version": state["version"],
                }
            return {"ok": False, "reason": "not_holder", "current_version": state["version"]}
        state["last_heartbeat"] = datetime.utcnow().isoformat()
        _write_lock(state, project_root)
        return {"ok": True, "version": state["version"]}


def force_release(released_by_login, project_root=None):
    with _lock_mutex:
        state = _read_lock(project_root)
        previous_holder = state.get("holder")
        _clear_lock(state, "force_released", released_by=released_by_login)
        state["last_holder"] = previous_holder
        _write_lock(state, project_root)
        return {
            "ok": True,
            "previous_holder": previous_holder,
            "version": state["version"],
        }


def clear_for_restore(restored_by_login, project_root=None):
    with _lock_mutex:
        state = _read_lock(project_root)
        previous_holder = state.get("holder")
        _clear_lock(state, "restore_completed", released_by=restored_by_login)
        state["last_holder"] = previous_holder
        _write_lock(state, project_root)
        return {
            "ok": True,
            "previous_holder": previous_holder,
            "version": state["version"],
        }
