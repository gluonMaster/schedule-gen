import json
import logging
import os
import re
import sys
import tempfile
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from html import unescape

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(THIS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from gear_xls.runtime_paths import (
    get_individual_lessons_path,
    get_schedule_html_path,
)
from gear_xls.day_constants import DAY_TO_WEEKDAY, TRIAL_ONLY_DAYS, WEB_EDITOR_DAY_SET

try:
    from .base_schedule_manager import (
        BASE_SCHEDULE_PATH,
        base_has_group_lessons_in_column,
        get_base_revision,
        get_base_schedule,
        publish_base,
    )
except ImportError:
    from base_schedule_manager import (
        BASE_SCHEDULE_PATH,
        base_has_group_lessons_in_column,
        get_base_revision,
        get_base_schedule,
        publish_base,
    )


INDIVIDUAL_LESSONS_PATH = get_individual_lessons_path()
INDIVIDUAL_LOCK_PATH = INDIVIDUAL_LESSONS_PATH + ".lock"
SCHEDULE_HTML_PATH = get_schedule_html_path()
VALID_DAYS = WEB_EDITOR_DAY_SET
_DAY_TO_WEEKDAY = DAY_TO_WEEKDAY
_ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ind_mutex = threading.Lock()
logger = logging.getLogger(__name__)
_HTML_BLOCK_PATTERN = re.compile(
    r"<div(?P<attrs>[^>]*class=['\"][^'\"]*activity-block[^'\"]*['\"][^>]*)>(?P<body>.*?)</div>",
    re.I | re.S,
)


def _empty_state():
    return {"last_modified": None, "blocks": []}


def _normalize_block(block):
    normalized = {}
    for key, value in (block or {}).items():
        normalized[key] = value.strip() if isinstance(value, str) else value
    return normalized


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
        logger.warning("Failed to release individual lock: %s", exc)


@contextmanager
def _locked_individual_file():
    os.makedirs(os.path.dirname(INDIVIDUAL_LOCK_PATH), exist_ok=True)
    with open(INDIVIDUAL_LOCK_PATH, "a+b") as lock_fp:
        backend = _acquire_file_lock(lock_fp)
        try:
            yield
        finally:
            _release_file_lock(lock_fp, backend)


def _read_individual():
    if not os.path.exists(INDIVIDUAL_LESSONS_PATH):
        return _empty_state()
    try:
        with open(INDIVIDUAL_LESSONS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty_state()
        blocks = data.get("blocks", [])
        return {
            "last_modified": data.get("last_modified"),
            "blocks": blocks if isinstance(blocks, list) else [],
        }
    except Exception as exc:
        logger.warning("Failed to read individual lessons: %s", exc)
        return _empty_state()


def _write_individual(state):
    os.makedirs(os.path.dirname(INDIVIDUAL_LESSONS_PATH), exist_ok=True)
    payload = {
        "last_modified": datetime.utcnow().isoformat(),
        "blocks": state.get("blocks", []),
    }
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=os.path.dirname(INDIVIDUAL_LESSONS_PATH),
            delete=False,
            suffix=".tmp",
            mode="w",
            encoding="utf-8",
        ) as tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name
        os.replace(tmp_path, INDIVIDUAL_LESSONS_PATH)
        state["last_modified"] = payload["last_modified"]
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _pristine_individual_state(state):
    return state.get("last_modified") is None and not state.get("blocks")


def _to_int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_embedded_individual_block(attrs_text, body):
    attrs = {
        key: unescape(value)
        for key, value in re.findall(r"data-([\w-]+)=['\"]([^'\"]*)['\"]", attrs_text)
    }
    lesson_type = (attrs.get("lesson-type") or "").strip()
    style_match = re.search(r"style=['\"]([^'\"]*)['\"]", attrs_text, re.I)
    color_match = (
        re.search(r"background-color\s*:\s*([^;]+)", style_match.group(1), re.I)
        if style_match
        else None
    )
    lines = [
        unescape(line)
        for line in (
            re.sub(r"<[^>]+>", "", raw_line).strip()
            for raw_line in re.sub(r"<br\s*/?>", "\n", body, flags=re.I).splitlines()
        )
        if line
    ]
    time_match = None
    time_index = -1
    block = None
    error = None

    if lesson_type not in ("individual", "nachhilfe", "trial"):
        return None

    for index in range(len(lines) - 1, -1, -1):
        time_match = re.fullmatch(
            r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", lines[index]
        )
        if time_match:
            time_index = index
            break

    if time_index < 1:
        return None

    block = {
        "id": str(uuid.uuid4()),
        "day": (attrs.get("day") or "").strip(),
        "building": (attrs.get("building") or "").strip(),
        "room": lines[time_index - 1].strip(),
        "start_time": time_match.group(1),
        "end_time": time_match.group(2),
        "subject": lines[0] if lines else "",
        "teacher": lines[1] if len(lines) > 1 else "",
        "students": lines[2] if len(lines) > 2 else "",
        "lesson_type": lesson_type,
    }

    if lesson_type == "trial":
        raw_trial_dates = attrs.get("trial-dates")
        if raw_trial_dates:
            try:
                parsed_trial_dates = json.loads(raw_trial_dates)
                if isinstance(parsed_trial_dates, list):
                    block["trial_dates"] = [str(item) for item in parsed_trial_dates if item is not None]
                else:
                    block["trial_dates"] = []
                    logger.warning("Skip invalid embedded trial-dates payload: %r", raw_trial_dates)
            except Exception as exc:
                block["trial_dates"] = []
                logger.warning("Failed to parse embedded trial-dates JSON: %s", exc)

    if color_match:
        block["color"] = color_match.group(1).strip()

    if attrs.get("start-row") is not None:
        block["start_row"] = _to_int_or_none(attrs.get("start-row"))
    if attrs.get("row-span") is not None:
        block["row_span"] = _to_int_or_none(attrs.get("row-span"))

    error = _validate_block(block, "admin")
    if error:
        logger.warning("Skip embedded non-group block due to validation error: %s", error)
        return None

    return block


def _load_embedded_individual_blocks():
    if not os.path.exists(SCHEDULE_HTML_PATH):
        return []

    try:
        with open(SCHEDULE_HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()
    except Exception as exc:
        logger.warning("Failed to read schedule HTML for individual bootstrap: %s", exc)
        return []

    blocks = []
    for match in _HTML_BLOCK_PATTERN.finditer(html):
        block = _parse_embedded_individual_block(
            match.group("attrs"), match.group("body")
        )
        if block:
            blocks.append(block)
    return blocks


def _bootstrap_individual_from_html_if_needed(state):
    embedded_blocks = []

    if not _pristine_individual_state(state):
        return state

    if get_base_schedule().get("published_at") is not None:
        return state

    embedded_blocks = _load_embedded_individual_blocks()
    if not embedded_blocks:
        return state

    state["blocks"] = embedded_blocks
    _write_individual(state)
    logger.info(
        "Bootstrapped %d non-group blocks from %s into individual_lessons.json",
        len(embedded_blocks),
        SCHEDULE_HTML_PATH,
    )
    return state


_ROLE_ALLOWED_TYPES = {
    "admin":     {"group", "individual", "nachhilfe", "trial"},
    "editor":    {"individual", "nachhilfe", "trial"},
    "organizer": {"trial"},
}


@dataclass
class IndividualMutationResult:
    value: object = None
    error: str | None = None
    individual_revision: str | None = None
    individual_cleanup_removed: int = 0
    cleanup_removed_ids: list | None = None

    def __iter__(self):
        yield self.value
        yield self.error

    @property
    def force_individual_refresh(self):
        return self.individual_cleanup_removed > 0


def _today_local_date() -> date:
    return datetime.now().date()


def _parse_iso_date_or_none(value):
    if not isinstance(value, str) or not _ISO_DATE_PATTERN.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _eligible_trial_dates_for_cleanup(block):
    if not isinstance(block, dict):
        return None
    if block.get("lesson_type") != "trial":
        return None

    trial_dates = block.get("trial_dates")
    if not isinstance(trial_dates, list) or not trial_dates:
        return None

    day = str(block.get("day", "")).strip()
    expected_weekday = _DAY_TO_WEEKDAY.get(day)
    if expected_weekday is None:
        return None

    parsed_dates = []
    for value in trial_dates:
        parsed = _parse_iso_date_or_none(value)
        if parsed is None:
            return None
        if parsed.weekday() != expected_weekday:
            return None
        parsed_dates.append(parsed)

    return parsed_dates


def _is_expired_trial_block(block, today=None):
    parsed_dates = _eligible_trial_dates_for_cleanup(block)
    if not parsed_dates:
        return False
    today = today or _today_local_date()
    return max(parsed_dates) < today


def _prune_expired_trial_blocks(state, today=None):
    blocks = state.get("blocks", []) if isinstance(state, dict) else []
    if not isinstance(blocks, list) or not blocks:
        return {"removed": 0, "removed_ids": []}

    today = today or _today_local_date()
    remaining = []
    removed_ids = []

    for block in blocks:
        if _is_expired_trial_block(block, today=today):
            removed_ids.append(block.get("id") if isinstance(block, dict) else None)
        else:
            remaining.append(block)

    if removed_ids:
        state["blocks"] = remaining

    return {"removed": len(removed_ids), "removed_ids": removed_ids}


def _validate_trial_not_expired_for_write(block, today=None):
    if _is_expired_trial_block(block, today=today):
        return "trial_dates must include today or a future date"
    return None


def _mutation_result(value, error, state, cleanup):
    return IndividualMutationResult(
        value=value,
        error=error,
        individual_revision=state.get("last_modified") if isinstance(state, dict) else None,
        individual_cleanup_removed=int(cleanup.get("removed") or 0) if isinstance(cleanup, dict) else 0,
        cleanup_removed_ids=list(cleanup.get("removed_ids") or []) if isinstance(cleanup, dict) else [],
    )


def _finish_mutation(value, error, state, cleanup, should_write):
    if should_write:
        _write_individual(state)
    return _mutation_result(value, error, state, cleanup)


def _validate_block(block, role):
    for field in ("day", "start_time", "end_time", "lesson_type", "subject", "room", "building"):
        if not str(block.get(field, "")).strip():
            return f"{field} required"
    if block["day"] not in VALID_DAYS:
        return "Invalid day"
    allowed = _ROLE_ALLOWED_TYPES.get(role)
    if allowed is not None and block.get("lesson_type") not in allowed:
        return "Forbidden lesson_type"
    if block["day"] in TRIAL_ONLY_DAYS and block.get("lesson_type") != "trial":
        return "Sunday is allowed only for trial lessons"
    if block.get("lesson_type") == "trial":
        dates = block.get("trial_dates", [])
        if not isinstance(dates, list):
            return "trial_dates must be a list"
        expected_weekday = _DAY_TO_WEEKDAY[block["day"]]
        normalized_dates = []
        seen_dates = set()
        for d in dates:
            if not isinstance(d, str) or not _ISO_DATE_PATTERN.fullmatch(d):
                return "trial_dates entries must be YYYY-MM-DD strings"
            try:
                parsed_date = datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                return f"trial_dates contains invalid date: {d}"
            if parsed_date.weekday() != expected_weekday:
                return f"trial_dates contains date {d} not matching block day {block['day']}"
            if d not in seen_dates:
                seen_dates.add(d)
                normalized_dates.append(d)
        if not normalized_dates:
            return "trial_dates must contain at least one date"
        block["trial_dates"] = sorted(normalized_dates)
    else:
        # Strip trial_dates from non-trial blocks to avoid stale data
        block.pop("trial_dates", None)
    for name, min_value in (("start_row", 0), ("row_span", 1)):
        value = block.get(name)
        if value is None:
            continue
        try:
            value = int(value)
        except (TypeError, ValueError):
            return f"{name} invalid"
        if value < min_value:
            return f"{name} invalid"
        block[name] = value
    return None


def get_individual_lessons():
    with _ind_mutex:
        with _locked_individual_file():
            state = _read_individual()
            state = _bootstrap_individual_from_html_if_needed(state)
            cleanup = _prune_expired_trial_blocks(state)
            if cleanup["removed"]:
                _write_individual(state)
                logger.info(
                    "Removed %d expired trial blocks from individual state",
                    cleanup["removed"],
                )
            return state


def get_individual_revision(prune_expired=True):
    if prune_expired:
        return get_individual_lessons().get("last_modified")
    with _ind_mutex:
        with _locked_individual_file():
            return _read_individual().get("last_modified")


def add_block(block, role):
    with _ind_mutex:
        with _locked_individual_file():
            state = _read_individual()
            cleanup = _prune_expired_trial_blocks(state)
            new_block = _normalize_block(block)
            error = _validate_block(new_block, role)
            if error:
                return _finish_mutation(None, error, state, cleanup, cleanup["removed"] > 0)
            error = _validate_trial_not_expired_for_write(new_block)
            if error:
                return _finish_mutation(None, error, state, cleanup, cleanup["removed"] > 0)
            new_block["id"] = str(uuid.uuid4())
            state["blocks"].append(new_block)
            return _finish_mutation(new_block, None, state, cleanup, True)


def update_block(block_id, updates, role):
    with _ind_mutex:
        with _locked_individual_file():
            state = _read_individual()
            cleanup = _prune_expired_trial_blocks(state)
            for index, block in enumerate(state["blocks"]):
                if block.get("id") != block_id:
                    continue
                merged = dict(block)
                merged.update(_normalize_block(updates))
                merged["id"] = block_id
                error = _validate_block(merged, role)
                if error:
                    return _finish_mutation(None, error, state, cleanup, cleanup["removed"] > 0)
                error = _validate_trial_not_expired_for_write(merged)
                if error:
                    return _finish_mutation(None, error, state, cleanup, cleanup["removed"] > 0)
                state["blocks"][index] = merged
                return _finish_mutation(merged, None, state, cleanup, True)
            error = "EXPIRED_TRIAL_PRUNED" if block_id in cleanup.get("removed_ids", []) else "NOT_FOUND"
            return _finish_mutation(None, error, state, cleanup, cleanup["removed"] > 0)


def delete_block(block_id, role=None):
    with _ind_mutex:
        with _locked_individual_file():
            state = _read_individual()
            cleanup = _prune_expired_trial_blocks(state)
            target = next((b for b in state["blocks"] if b.get("id") == block_id), None)
            if target is None:
                error = "EXPIRED_TRIAL_PRUNED" if block_id in cleanup.get("removed_ids", []) else None
                return _finish_mutation(False, error, state, cleanup, cleanup["removed"] > 0)
            if role == "organizer" and target.get("lesson_type") != "trial":
                return _finish_mutation(False, "FORBIDDEN", state, cleanup, cleanup["removed"] > 0)
            state["blocks"] = [b for b in state["blocks"] if b.get("id") != block_id]
            return _finish_mutation(True, None, state, cleanup, True)


def convert_block_to_regular(block_id, role):
    try:
        from .lesson_type_utils import infer_regular_type_from_subject
    except ImportError:
        from lesson_type_utils import infer_regular_type_from_subject

    with _ind_mutex:
        with _locked_individual_file():
            state = _read_individual()
            cleanup = _prune_expired_trial_blocks(state)
            for index, block in enumerate(state["blocks"]):
                if block.get("id") != block_id:
                    continue
                if block.get("lesson_type") != "trial":
                    return _finish_mutation(None, "NOT_TRIAL", state, cleanup, cleanup["removed"] > 0)
                if role not in ("admin", "editor", "organizer"):
                    return _finish_mutation(None, "FORBIDDEN", state, cleanup, cleanup["removed"] > 0)
                if block.get("day") in TRIAL_ONLY_DAYS:
                    return _finish_mutation(
                        None,
                        "Sunday is allowed only for trial lessons",
                        state,
                        cleanup,
                        cleanup["removed"] > 0,
                    )
                merged = dict(block)
                merged.pop("trial_dates", None)
                merged["lesson_type"] = infer_regular_type_from_subject(merged.get("subject", ""))
                state["blocks"][index] = merged
                return _finish_mutation(merged, None, state, cleanup, True)
            error = "EXPIRED_TRIAL_PRUNED" if block_id in cleanup.get("removed_ids", []) else "NOT_FOUND"
            return _finish_mutation(None, error, state, cleanup, cleanup["removed"] > 0)


def individual_column_has_non_trial_blocks(building, day, room):
    with _ind_mutex:
        with _locked_individual_file():
            state = _read_individual()
    return any(
        block.get("building") == building
        and block.get("day") == day
        and block.get("room") == room
        and block.get("lesson_type") != "trial"
        for block in state.get("blocks", [])
        if isinstance(block, dict)
    )


def delete_column_blocks(building, day, room):
    with _ind_mutex:
        with _locked_individual_file():
            state = _read_individual()
            cleanup = _prune_expired_trial_blocks(state)
            remaining = []
            removed = 0
            for block in state["blocks"]:
                if block.get("building") == building and block.get("day") == day and block.get("room") == room:
                    removed += 1
                else:
                    remaining.append(block)
            if removed:
                state["blocks"] = remaining
            return _finish_mutation(removed, None, state, cleanup, bool(removed or cleanup["removed"]))
