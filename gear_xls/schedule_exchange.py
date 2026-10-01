"""Metadata at the existing Schedule/Plannung workbook boundaries."""
import json
import re
from gear_xls.day_constants import WEB_EDITOR_DAY_SET

from gear_xls.lesson_type_utils import (
    classify_lesson_type, is_legacy_rental_subject, validate_rental_dates,
)

SYNC_SHEET = "__schedule_sync"
SYNC_KEYS = ("format_version", "source_base_revision", "source_individual_revision", "snapshot_scope")
MANAGED_TYPES = {"individual", "nachhilfe", "trial", "rental"}
RECORD_COLUMNS = ("block_id", "rental_dates_json", "source_layer", "color", "block_metadata_json")
CORE_FIELDS = {
    "id", "block_id", "subject", "teacher", "students", "group", "room", "room_display",
    "building", "day", "start_time", "end_time", "duration", "lesson_type", "color",
    "trial_dates", "rental_dates", "trial_dates_json", "rental_dates_json", "source_layer",
    "start_row", "row_span", "row_start", "rowspan", "col", "block_metadata_json",
    "pause_before", "pause_after", "block_metadata",
}


class ScheduleExchangeError(ValueError):
    pass


def normalize_sync_metadata(metadata):
    # None is unknown provenance; present blank revision cells mean an empty layer.
    if metadata is None:
        return None
    if not isinstance(metadata, dict) or any(key not in metadata for key in SYNC_KEYS):
        raise ScheduleExchangeError("Incomplete schedule snapshot metadata")
    if str(metadata["format_version"]) != "1":
        raise ScheduleExchangeError("Unsupported schedule snapshot format_version")
    result = {"format_version": 1}
    for key in SYNC_KEYS[1:3]:
        value = metadata[key]
        if value is not None and not isinstance(value, str):
            raise ScheduleExchangeError(f"{key} must be a string or an explicit empty revision")
        result[key] = value if value is not None else ""
    if metadata["snapshot_scope"] not in ("full", "partial"):
        raise ScheduleExchangeError("Invalid snapshot_scope")
    result["snapshot_scope"] = metadata["snapshot_scope"]
    return result


def read_sync_metadata(workbook):
    if SYNC_SHEET not in workbook.sheetnames:
        return None
    metadata = {}
    for key, value, *_ in workbook[SYNC_SHEET].iter_rows(min_row=2, max_col=2, values_only=True):
        if key is None:
            continue
        if key in metadata:
            raise ScheduleExchangeError(f"Duplicate snapshot key: {key}")
        metadata[key] = value
    return normalize_sync_metadata(metadata)


def write_sync_metadata(workbook, metadata):
    metadata = normalize_sync_metadata(metadata)
    if metadata is None:
        return
    sheet = workbook.create_sheet(SYNC_SHEET)
    sheet.append(["key", "value"])
    for key in SYNC_KEYS:
        sheet.append([key, metadata[key]])
        sheet.cell(sheet.max_row, 2).number_format = "@" if key != "format_version" else "0"
    sheet.sheet_state = "veryHidden"


def dates_from_record(record, field):
    raw = record.get(field + "_json", record.get(field, []))
    if raw in (None, ""):
        raw = []
    try:
        dates = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError) as exc:
        raise ScheduleExchangeError(f"Invalid {field}_json") from exc
    if not isinstance(dates, list):
        raise ScheduleExchangeError(f"{field} must be a list")
    if field in record and record[field] != dates:
        raise ScheduleExchangeError(f"Conflicting {field} and {field}_json")
    return dates


def _clock_text(value):
    # The editor page sends {hour, minute} objects (block_utils' minutesToTime); Excel may give time values.
    if isinstance(value, dict) and "hour" in value and "minute" in value:
        try:
            return f"{int(value['hour']):02d}:{int(value['minute']):02d}"
        except (TypeError, ValueError):
            return str(value)
    if hasattr(value, "hour") and hasattr(value, "minute"):
        return f"{value.hour:02d}:{value.minute:02d}"
    return str(value or "")


def normalize_exchange_record(record, *, legacy=False):
    result = dict(record)
    explicit_type = str(result.get("lesson_type") or "").strip().lower()
    trial_dates = dates_from_record(result, "trial_dates")
    rental_dates = dates_from_record(result, "rental_dates")
    if legacy and is_legacy_rental_subject(result.get("subject")):
        explicit_type = "rental"
        rental_dates = trial_dates if trial_dates else rental_dates
        trial_dates = []
    lesson_type = explicit_type or classify_lesson_type(result.get("subject"))
    if lesson_type not in MANAGED_TYPES | {"group"}:
        raise ScheduleExchangeError(f"Invalid lesson_type: {lesson_type}")
    if rental_dates and lesson_type != "rental" or trial_dates and lesson_type != "trial":
        raise ScheduleExchangeError("Dates contradict lesson_type")
    result.update(lesson_type=lesson_type, trial_dates=trial_dates, rental_dates=rental_dates)
    result['trial_dates_json'] = json.dumps(trial_dates, ensure_ascii=False) if lesson_type == 'trial' else ''
    result['rental_dates_json'] = json.dumps(rental_dates, ensure_ascii=False) if lesson_type == 'rental' else ''
    if lesson_type in ("rental", "trial"):
        field = "rental_dates" if lesson_type == "rental" else "trial_dates"
        error = validate_rental_dates(result.get("day"), result[field])
        # Empty ordinary trial dates retain the existing weekly trial semantics.
        if error and not (lesson_type == "trial" and not result[field]):
            raise ScheduleExchangeError(error.replace("rental_dates", field))
    if lesson_type == "rental":
        if not isinstance(result.get('day'), str) or result['day'] not in WEB_EDITOR_DAY_SET:
            raise ScheduleExchangeError("Invalid rental day")
        for key in ("start_time", "end_time"):
            result[key] = _clock_text(result.get(key))
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", result[key]):
                raise ScheduleExchangeError(f"Invalid rental {key}")
        start, end = (sum(int(n) * factor for n, factor in zip(result[key].split(":"), (60, 1)))
                      for key in ("start_time", "end_time"))
        try:
            duration = float(result.get('duration') or 0)
        except (TypeError, ValueError) as exc:
            raise ScheduleExchangeError("Invalid rental duration") from exc
        if end <= start or duration != end - start:
            raise ScheduleExchangeError("Rental duration contradicts start_time/end_time")
        result['duration'] = int(duration)
        if not result.get("room") or not result.get("building"):
            raise ScheduleExchangeError("Rental room and building are required")
    raw_id = result.get('block_id')
    block_id = str(raw_id).strip() if raw_id is not None else ''
    if lesson_type in MANAGED_TYPES and result.get('id'):
        if block_id and block_id != str(result['id']):
            raise ScheduleExchangeError("id contradicts block_id")
        block_id = str(result['id'])
    source_layer = str(result.get("source_layer") or "").strip()
    if lesson_type == "group" and (block_id or source_layer == "individual"):
        raise ScheduleExchangeError("Group row cannot carry a managed block_id/source_layer")
    expected_layer = "individual" if lesson_type in MANAGED_TYPES else "base"
    if source_layer and source_layer != expected_layer:
        raise ScheduleExchangeError("source_layer contradicts lesson_type")
    result.update(block_id=block_id, source_layer=expected_layer)
    raw_extra = result.get("block_metadata_json") or result.get("block_metadata") or {
        key: value for key, value in result.items() if key not in CORE_FIELDS
    }
    try:
        extra = json.loads(raw_extra) if isinstance(raw_extra, str) else raw_extra
    except (TypeError, ValueError) as exc:
        raise ScheduleExchangeError("Invalid block_metadata_json") from exc
    if not isinstance(extra, dict) or CORE_FIELDS.intersection(extra):
        raise ScheduleExchangeError("block_metadata_json contradicts canonical columns")
    result["block_metadata"] = extra
    return result


def check_unique_block_ids(records, sync_metadata=None):
    seen = set()
    for record in records:
        block_id = record.get("block_id")
        if sync_metadata is not None and record.get('lesson_type') in MANAGED_TYPES and not block_id:
            raise ScheduleExchangeError("Managed snapshot row is missing block_id")
        if block_id:
            if block_id in seen:
                raise ScheduleExchangeError(f"Duplicate block_id: {block_id}")
            seen.add(block_id)
