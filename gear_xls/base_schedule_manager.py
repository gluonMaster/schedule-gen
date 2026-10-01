import json
import logging
import os
import sys
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(THIS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from gear_xls.runtime_paths import get_base_schedule_path
from gear_xls.room_name_utils import normalize_room_fields
from gear_xls.day_constants import PUBLIC_SCHEDULE_DAY_SET


BASE_SCHEDULE_PATH = get_base_schedule_path()
BASE_LOCK_PATH = BASE_SCHEDULE_PATH + ".lock"
_base_mutex = threading.Lock()
logger = logging.getLogger(__name__)


class BaseRevisionConflict(Exception):
    def __init__(self, expected_revision, current_revision):
        super().__init__("Base schedule revision conflict")
        self.expected_revision = expected_revision
        self.current_revision = current_revision


class BaseScheduleValidationError(Exception):
    def __init__(self, message, code="INVALID_BASE_DAY"):
        super().__init__(message)
        self.message = message
        self.code = code


def _empty_base():
    return {"published_at": None, "published_by": None, "blocks": []}


def _acquire_file_lock(fp):
    try:
        import msvcrt

        fp.seek(0)
        if os.path.getsize(fp.name) == 0:
            fp.write(b"0")
            fp.flush()
            fp.seek(0)
        msvcrt.locking(fp.fileno(), msvcrt.LK_NBLCK, 1)
        return "msvcrt"
    except ImportError:
        try:
            import fcntl
        except ImportError as exc:
            raise RuntimeError("Cannot acquire file lock") from exc
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return "fcntl"
        except OSError as exc:
            raise RuntimeError("Cannot acquire file lock") from exc
    except OSError as exc:
        raise RuntimeError("Cannot acquire file lock") from exc


def _release_file_lock(fp, backend):
    try:
        if backend == "msvcrt":
            import msvcrt

            fp.seek(0)
            msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
            return
        if backend == "fcntl":
            import fcntl

            fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
    except Exception as exc:
        logger.warning("Failed to release base schedule lock: %s", exc)


@contextmanager
def _locked_base_file():
    os.makedirs(os.path.dirname(BASE_LOCK_PATH), exist_ok=True)
    with open(BASE_LOCK_PATH, "a+b") as lock_fp:
        backend = _acquire_file_lock(lock_fp)
        try:
            yield
        finally:
            _release_file_lock(lock_fp, backend)


def _read_base():
    if not os.path.exists(BASE_SCHEDULE_PATH):
        return _empty_base()
    try:
        with open(BASE_SCHEDULE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty_base()
        blocks = data.get("blocks", [])
        return {
            "published_at": data.get("published_at"),
            "published_by": data.get("published_by"),
            "blocks": blocks if isinstance(blocks, list) else [],
        }
    except Exception as exc:
        logger.warning("Failed to read base schedule: %s", exc)
        return _empty_base()


def _normalize_base_blocks(blocks):
    normalized_blocks = []

    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        normalized_blocks.append(normalize_room_fields(block))

    return normalized_blocks


def _validate_public_base_block(block, index):
    day = str(block.get("day") or "").strip()
    lesson_type = str(block.get("lesson_type") or "").strip() or "group"

    if lesson_type != "group":
        return
    if day not in PUBLIC_SCHEDULE_DAY_SET:
        code = "SUNDAY_REGULAR_FORBIDDEN" if day == "So" else "INVALID_BASE_DAY"
        raise BaseScheduleValidationError(
            f"Base/group block {index} has invalid public schedule day: {day or '<empty>'}",
            code=code,
        )


def _normalize_revision(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _normalize_signature_value(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return {
            str(key): _normalize_signature_value(value[key])
            for key in sorted(value.keys())
        }
    if isinstance(value, list):
        return [_normalize_signature_value(item) for item in value]
    return value


def _base_blocks_signature(blocks):
    normalized = []

    for block in _normalize_base_blocks(blocks):
        if not isinstance(block, dict):
            continue
        normalized.append(_normalize_signature_value(block))

    normalized.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_base(state):
    os.makedirs(os.path.dirname(BASE_SCHEDULE_PATH), exist_ok=True)
    payload = {
        "published_at": state.get("published_at"),
        "published_by": state.get("published_by"),
        "blocks": state.get("blocks", []),
    }
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=os.path.dirname(BASE_SCHEDULE_PATH),
            delete=False,
            suffix=".tmp",
            mode="w",
            encoding="utf-8",
        ) as tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name
        os.replace(tmp_path, BASE_SCHEDULE_PATH)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def get_base_schedule():
    state = _read_base()
    state["blocks"] = _normalize_base_blocks(state.get("blocks", []))
    return state


def get_base_revision():
    return get_base_schedule().get("published_at")


def publish_base(blocks, published_by, expected_base_revision=None):
    with _base_mutex:
        with _locked_base_file():
            current_state = _read_base()
            current_revision = _normalize_revision(current_state.get("published_at"))
            expected_revision = _normalize_revision(expected_base_revision)

            if expected_revision != current_revision:
                raise BaseRevisionConflict(expected_revision, current_revision)

            filtered_blocks = []
            for index, block in enumerate(blocks or []):
                if not isinstance(block, dict):
                    continue
                normalized_block = normalize_room_fields(block)
                _validate_public_base_block(normalized_block, index)
                if normalized_block.get("lesson_type") == "group":
                    filtered_blocks.append(normalized_block)
            if _base_blocks_signature(current_state.get("blocks", [])) == _base_blocks_signature(
                filtered_blocks
            ):
                current_state["blocks"] = _normalize_base_blocks(current_state.get("blocks", []))
                current_state["changed"] = False
                return current_state

            state = {
                "published_at": datetime.utcnow().isoformat(),
                "published_by": published_by,
                "blocks": filtered_blocks,
                "changed": True,
            }
            _write_base(state)
            return state


def base_has_group_lessons_in_column(building, day, room):
    blocks = get_base_schedule().get("blocks", [])
    return any(
        block.get("building") == building
        and block.get("day") == day
        and block.get("room") == room
        and block.get("lesson_type") == "group"
        for block in blocks
        if isinstance(block, dict)
    )
