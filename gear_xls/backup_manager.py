from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import struct
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any

from gear_xls.runtime_paths import (
    get_backup_dir,
    get_base_schedule_path,
    get_individual_lessons_path,
    get_project_root_id,
    get_schedule_html_path,
    get_spiski_dir,
)
from gear_xls.day_constants import (
    DAY_TO_WEEKDAY,
    PUBLIC_SCHEDULE_DAY_SET,
    TRIAL_ONLY_DAYS,
    WEB_EDITOR_DAY_SET,
)


BACKUP_SCHEMA = "schedgen.web_editor_backup"
BACKUP_SCHEMA_VERSION = 1
BACKUP_ID_RE = re.compile(r"^schedgen_backup_\d{8}_\d{6}_[0-9a-f]{8}$")
BACKUP_FILENAME_RE = re.compile(r"^(schedgen_backup_\d{8}_\d{6}_[0-9a-f]{8})\.zip$")
ALLOWED_BACKUP_KINDS = {"manual", "safety", "uploaded"}

MAX_COMMENT_CHARS = 500
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_ZIP_FILES = 30
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_SINGLE_FILE_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
MAX_SCHEDULE_HTML_BYTES = 25 * 1024 * 1024
MAX_JSON_BYTES = 10 * 1024 * 1024
MAX_SPISKI_FILE_BYTES = 1 * 1024 * 1024

ALLOWED_SPISKI_FILENAMES = (
    "disciplins.txt",
    "groups.txt",
    "teachers.txt",
    "kabinets_Villa.txt",
    "kabinets_Kolibri.txt",
)
SPISKI_ARCHIVE_PATHS = tuple(f"spiski/{name}" for name in ALLOWED_SPISKI_FILENAMES)
EXPECTED_CONTENT_PATHS = (
    "state/base_schedule.json",
    "state/individual_lessons.json",
    "html/schedule.html",
    *SPISKI_ARCHIVE_PATHS,
)
EXPECTED_ARCHIVE_PATHS = ("manifest.json", *EXPECTED_CONTENT_PATHS)
EXPECTED_ARCHIVE_PATH_SET = set(EXPECTED_ARCHIVE_PATHS)
EXPECTED_CONTENT_PATH_SET = set(EXPECTED_CONTENT_PATHS)

VALID_DAYS = WEB_EDITOR_DAY_SET
VALID_PUBLIC_DAYS = PUBLIC_SCHEDULE_DAY_SET
VALID_BASE_LESSON_TYPES = {"group"}
VALID_INDIVIDUAL_LESSON_TYPES = {"individual", "nachhilfe", "trial"}
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
def _joined_marker(*parts: str) -> str:
    return "".join(parts)


LEGACY_SCHEDULE_MARKERS = (
    _joined_marker("save", "Schedule"),
    _joined_marker("save", "Intermediate"),
    _joined_marker("/save", "_intermediate"),
    _joined_marker("final", "_schedule.html"),
    _joined_marker("intermediate", "_schedule.html"),
    _joined_marker("body.", "static", "-schedule"),
    _joined_marker("static", "-schedule"),
)


class BackupError(RuntimeError):
    def __init__(self, message: str, code: str = "BACKUP_ERROR", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class BackupValidationError(BackupError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_created_at(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _empty_base_state() -> dict[str, Any]:
    return {"published_at": None, "published_by": None, "blocks": []}


def _empty_individual_state() -> dict[str, Any]:
    return {"last_modified": None, "blocks": []}


def normalize_comment(comment: object) -> str:
    normalized = str(comment or "").strip()
    if len(normalized) > MAX_COMMENT_CHARS:
        raise BackupError(
            "Backup comment is too long",
            code="COMMENT_TOO_LONG",
            status_code=400,
        )
    return normalized


def validate_backup_id(backup_id: object) -> str:
    if not isinstance(backup_id, str) or not BACKUP_ID_RE.fullmatch(backup_id):
        raise BackupValidationError("Invalid backup id", code="INVALID_BACKUP_ID", status_code=400)
    return backup_id


def get_backup_path(backup_id: str, project_root: str | None = None) -> str:
    backup_id = validate_backup_id(backup_id)
    backup_dir = os.path.abspath(get_backup_dir(project_root))
    path = os.path.abspath(os.path.join(backup_dir, f"{backup_id}.zip"))
    if os.path.commonpath([backup_dir, path]) != backup_dir:
        raise BackupValidationError("Invalid backup id", code="INVALID_BACKUP_ID", status_code=400)
    return path


def _generate_backup_id(moment: datetime) -> str:
    timestamp = moment.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"schedgen_backup_{timestamp}_{uuid.uuid4().hex[:8]}"


def _allocate_backup_destination(backup_dir: str, moment: datetime) -> tuple[str, str]:
    for _ in range(100):
        candidate_id = _generate_backup_id(moment)
        candidate_path = os.path.join(backup_dir, f"{candidate_id}.zip")
        if not os.path.exists(candidate_path):
            return candidate_id, candidate_path
    raise BackupError(
        "Could not allocate backup filename",
        code="BACKUP_FILENAME_COLLISION",
        status_code=500,
    )


def _read_limited_file(path: str, *, max_bytes: int, label: str) -> bytes:
    try:
        size = os.path.getsize(path)
    except FileNotFoundError as exc:
        raise BackupError(f"{label} is missing", code="SOURCE_FILE_MISSING", status_code=400) from exc
    if size > max_bytes:
        raise BackupError(f"{label} is too large", code="SOURCE_FILE_TOO_LARGE", status_code=400)
    with open(path, "rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise BackupError(f"{label} is too large", code="SOURCE_FILE_TOO_LARGE", status_code=400)
    return data


def _parse_json_bytes(data: bytes, *, label: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BackupValidationError(
            f"{label} is not valid UTF-8",
            code="INVALID_JSON_STATE",
            status_code=400,
        ) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise BackupValidationError(
            f"{label} is not valid JSON",
            code="INVALID_JSON_STATE",
            status_code=400,
        ) from exc


def _read_state_json(
    path: str,
    *,
    label: str,
    default_state: dict[str, Any],
    validator,
) -> tuple[bytes, dict[str, Any]]:
    if not os.path.exists(path):
        validator(default_state, label=label)
        return _json_bytes(default_state), dict(default_state)

    data = _read_limited_file(path, max_bytes=MAX_JSON_BYTES, label=label)
    parsed = _parse_json_bytes(data, label=label)
    validator(parsed, label=label)
    return data, parsed


def _time_minutes(value: str) -> int:
    hours, minutes = value.split(":", 1)
    return int(hours) * 60 + int(minutes)


def _validate_non_empty_string(block: dict[str, Any], field: str, *, label: str, index: int) -> None:
    value = block.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BackupValidationError(
            f"{label} block {index}: {field} must be a non-empty string",
            code="INVALID_JSON_STATE",
            status_code=400,
        )


def _validate_optional_string(block: dict[str, Any], field: str, *, label: str, index: int) -> None:
    value = block.get(field)
    if value is not None and not isinstance(value, str):
        raise BackupValidationError(
            f"{label} block {index}: {field} must be a string",
            code="INVALID_JSON_STATE",
            status_code=400,
        )


def _validate_optional_int(
    block: dict[str, Any], field: str, *, minimum: int, label: str, index: int
) -> None:
    value = block.get(field)
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise BackupValidationError(
            f"{label} block {index}: {field} must be an integer >= {minimum}",
            code="INVALID_JSON_STATE",
            status_code=400,
        )


def _validate_common_block(
    block: Any,
    *,
    label: str,
    index: int,
    allowed_lesson_types: set[str],
    allowed_days: set[str] | frozenset[str],
    require_id: bool,
) -> None:
    if not isinstance(block, dict):
        raise BackupValidationError(
            f"{label} block {index} must be an object",
            code="INVALID_JSON_STATE",
            status_code=400,
        )
    required = ["building", "day", "room", "subject", "start_time", "end_time", "lesson_type"]
    if require_id:
        required.insert(0, "id")
    for field in required:
        _validate_non_empty_string(block, field, label=label, index=index)

    lesson_type = block["lesson_type"]
    if lesson_type not in allowed_lesson_types:
        raise BackupValidationError(
            f"{label} block {index}: unsupported lesson_type",
            code="INVALID_JSON_STATE",
            status_code=400,
        )
    if block["day"] not in allowed_days:
        raise BackupValidationError(
            f"{label} block {index}: invalid day",
            code="INVALID_JSON_STATE",
            status_code=400,
        )
    if not TIME_RE.fullmatch(block["start_time"]) or not TIME_RE.fullmatch(block["end_time"]):
        raise BackupValidationError(
            f"{label} block {index}: invalid time format",
            code="INVALID_JSON_STATE",
            status_code=400,
        )
    if _time_minutes(block["end_time"]) <= _time_minutes(block["start_time"]):
        raise BackupValidationError(
            f"{label} block {index}: end_time must be greater than start_time",
            code="INVALID_JSON_STATE",
            status_code=400,
        )
    for field in ("teacher", "students", "color", "room_display"):
        _validate_optional_string(block, field, label=label, index=index)
    _validate_optional_int(block, "start_row", minimum=0, label=label, index=index)
    _validate_optional_int(block, "row_span", minimum=1, label=label, index=index)

    for field, value in block.items():
        if isinstance(value, str) and len(value) > 1000:
            raise BackupValidationError(
                f"{label} block {index}: {field} is too long",
                code="INVALID_JSON_STATE",
                status_code=400,
            )


def validate_base_state(data: Any, *, label: str = "base_schedule.json") -> None:
    if not isinstance(data, dict):
        raise BackupValidationError(
            f"{label} must be a JSON object",
            code="INVALID_JSON_STATE",
            status_code=400,
        )
    blocks = data.get("blocks")
    if not isinstance(blocks, list):
        raise BackupValidationError(
            f"{label} blocks must be a list",
            code="INVALID_JSON_STATE",
            status_code=400,
        )
    for index, block in enumerate(blocks):
        _validate_common_block(
            block,
            label=label,
            index=index,
            allowed_lesson_types=VALID_BASE_LESSON_TYPES,
            allowed_days=VALID_PUBLIC_DAYS,
            require_id=False,
        )


def validate_individual_state(data: Any, *, label: str = "individual_lessons.json") -> None:
    if not isinstance(data, dict):
        raise BackupValidationError(
            f"{label} must be a JSON object",
            code="INVALID_JSON_STATE",
            status_code=400,
        )
    blocks = data.get("blocks")
    if not isinstance(blocks, list):
        raise BackupValidationError(
            f"{label} blocks must be a list",
            code="INVALID_JSON_STATE",
            status_code=400,
        )
    seen_ids: set[str] = set()
    for index, block in enumerate(blocks):
        _validate_common_block(
            block,
            label=label,
            index=index,
            allowed_lesson_types=VALID_INDIVIDUAL_LESSON_TYPES,
            allowed_days=VALID_DAYS,
            require_id=True,
        )
        block_id = block["id"]
        if block_id in seen_ids:
            raise BackupValidationError(
                f"{label} block {index}: duplicate id",
                code="INVALID_JSON_STATE",
                status_code=400,
            )
        seen_ids.add(block_id)
        if block["day"] in TRIAL_ONLY_DAYS and block["lesson_type"] != "trial":
            raise BackupValidationError(
                f"{label} block {index}: Sunday is allowed only for trial lessons",
                code="INVALID_JSON_STATE",
                status_code=400,
            )
        if block["lesson_type"] != "trial":
            continue
        trial_dates = block.get("trial_dates")
        if not isinstance(trial_dates, list) or not trial_dates:
            raise BackupValidationError(
                f"{label} block {index}: trial_dates must be a non-empty list",
                code="INVALID_JSON_STATE",
                status_code=400,
            )
        expected_weekday = DAY_TO_WEEKDAY[block["day"]]
        for raw_date in trial_dates:
            if not isinstance(raw_date, str) or not ISO_DATE_RE.fullmatch(raw_date):
                raise BackupValidationError(
                    f"{label} block {index}: invalid trial date",
                    code="INVALID_JSON_STATE",
                    status_code=400,
                )
            try:
                parsed_date = datetime.strptime(raw_date, "%Y-%m-%d")
            except ValueError as exc:
                raise BackupValidationError(
                    f"{label} block {index}: invalid trial date",
                    code="INVALID_JSON_STATE",
                    status_code=400,
                ) from exc
            if parsed_date.weekday() != expected_weekday:
                raise BackupValidationError(
                    f"{label} block {index}: trial date weekday mismatch",
                    code="INVALID_JSON_STATE",
                    status_code=400,
                )


def validate_schedule_html_bytes(data: bytes) -> None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BackupValidationError(
            "schedule.html is not valid UTF-8",
            code="INVALID_SCHEDULE_HTML",
            status_code=400,
        ) from exc
    if not text.strip():
        raise BackupValidationError(
            "schedule.html is empty",
            code="INVALID_SCHEDULE_HTML",
            status_code=400,
        )
    lower_text = text.lower()
    if "<html" not in lower_text:
        raise BackupValidationError(
            "schedule.html must contain <html",
            code="INVALID_SCHEDULE_HTML",
            status_code=400,
        )
    if "schedule-container" not in text:
        raise BackupValidationError(
            "schedule.html must contain schedule-container",
            code="INVALID_SCHEDULE_HTML",
            status_code=400,
        )
    if "#menuDropdown" not in text and 'id="menuDropdown"' not in text and "id='menuDropdown'" not in text:
        raise BackupValidationError(
            "schedule.html must contain menuDropdown",
            code="INVALID_SCHEDULE_HTML",
            status_code=400,
        )
    for marker in LEGACY_SCHEDULE_MARKERS:
        if marker in text:
            raise BackupValidationError(
                f"schedule.html contains legacy artifact: {marker}",
                code="INVALID_SCHEDULE_HTML",
                status_code=400,
            )


def validate_spiski_bytes(data: bytes, *, label: str) -> None:
    if b"\x00" in data:
        raise BackupValidationError(
            f"{label} contains NUL bytes",
            code="INVALID_SPISKI_FILE",
            status_code=400,
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BackupValidationError(
            f"{label} is not valid UTF-8",
            code="INVALID_SPISKI_FILE",
            status_code=400,
        ) from exc
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.strip() and len(line.strip()) > 200:
            raise BackupValidationError(
                f"{label} line {line_number} is too long",
                code="INVALID_SPISKI_FILE",
                status_code=400,
            )


def _read_schedule_html(project_root: str | None) -> bytes:
    path = get_schedule_html_path(project_root)
    if not os.path.exists(path):
        raise BackupError(
            "schedule.html is missing; generate the schedule before creating a backup",
            code="SCHEDULE_HTML_MISSING",
            status_code=400,
        )
    data = _read_limited_file(path, max_bytes=MAX_SCHEDULE_HTML_BYTES, label="schedule.html")
    validate_schedule_html_bytes(data)
    return data


def _read_spiski_file(project_root: str | None, filename: str) -> bytes:
    path = os.path.join(get_spiski_dir(project_root), filename)
    if not os.path.exists(path):
        return b""
    data = _read_limited_file(path, max_bytes=MAX_SPISKI_FILE_BYTES, label=f"spiski/{filename}")
    validate_spiski_bytes(data, label=f"spiski/{filename}")
    return data


def _collect_source_files(project_root: str | None) -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any]]:
    base_bytes, base_state = _read_state_json(
        get_base_schedule_path(project_root),
        label="base_schedule.json",
        default_state=_empty_base_state(),
        validator=validate_base_state,
    )
    individual_bytes, individual_state = _read_state_json(
        get_individual_lessons_path(project_root),
        label="individual_lessons.json",
        default_state=_empty_individual_state(),
        validator=validate_individual_state,
    )
    files = {
        "state/base_schedule.json": base_bytes,
        "state/individual_lessons.json": individual_bytes,
        "html/schedule.html": _read_schedule_html(project_root),
    }
    for filename in ALLOWED_SPISKI_FILENAMES:
        files[f"spiski/{filename}"] = _read_spiski_file(project_root, filename)
    return files, base_state, individual_state


def _build_manifest(
    *,
    files: dict[str, bytes],
    base_state: dict[str, Any],
    individual_state: dict[str, Any],
    created_at: str,
    created_by: str,
    created_by_display_name: str,
    comment: str,
    backup_kind: str,
    project_root: str | None,
) -> dict[str, Any]:
    return {
        "schema": BACKUP_SCHEMA,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "backup_kind": backup_kind,
        "created_at": created_at,
        "created_by": str(created_by or ""),
        "created_by_display_name": str(created_by_display_name or ""),
        "comment": comment,
        "project_root_id": get_project_root_id(project_root),
        "app": "Kolibri SchedGen",
        "source": "web_editor_persisted_state",
        "dirty_dom_included": False,
        "base_revision": base_state.get("published_at"),
        "individual_revision": individual_state.get("last_modified"),
        "includes": {
            "schedule_html": True,
            "base_schedule": True,
            "individual_lessons": True,
            "spiski": True,
            "lock_state": False,
            "restore_status": False,
            "source_excel": False,
        },
        "spiski_files": list(ALLOWED_SPISKI_FILENAMES),
        "files": [
            {"path": path, "sha256": _sha256(files[path]), "size": len(files[path])}
            for path in EXPECTED_CONTENT_PATHS
        ],
    }


def _write_zip(path: str, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for archive_path in EXPECTED_ARCHIVE_PATHS:
            archive.writestr(archive_path, entries[archive_path])


def _normalize_uploaded_original_filename(original_filename: object) -> str:
    value = str(original_filename or "").replace("\x00", "").strip()
    value = value.replace("\\", "/").split("/")[-1]
    value = "".join(ch if ch >= " " and ch != "\x7f" else " " for ch in value)
    value = " ".join(value.split())
    return value[:255]


def _copy_upload_to_temp(file_stream, backup_dir: str) -> str:
    if file_stream is None:
        raise BackupValidationError(
            "Missing multipart file field",
            code="MISSING_UPLOAD_FILE",
            status_code=400,
        )

    fd, tmp_path = tempfile.mkstemp(prefix=".upload_", suffix=".zip.tmp", dir=backup_dir)
    total = 0
    try:
        with os.fdopen(fd, "wb") as handle:
            while True:
                chunk = file_stream.read(1024 * 1024)
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise BackupValidationError(
                        "Uploaded backup is too large",
                        code="UPLOAD_TOO_LARGE",
                        status_code=413,
                    )
                handle.write(chunk)
        if total == 0:
            raise BackupValidationError(
                "Uploaded backup is empty",
                code="EMPTY_UPLOAD_FILE",
                status_code=400,
            )
        return tmp_path
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def _trusted_uploaded_manifest(
    manifest: dict[str, Any],
    *,
    uploaded_at: str,
    uploaded_by: str,
    uploaded_by_display_name: str,
    original_filename: object,
) -> dict[str, Any]:
    trusted = dict(manifest)
    trusted["backup_kind"] = "uploaded"
    trusted["uploaded_at"] = uploaded_at
    trusted["uploaded_by"] = str(uploaded_by or "")
    trusted["uploaded_by_display_name"] = str(uploaded_by_display_name or "")
    original_name = _normalize_uploaded_original_filename(original_filename)
    if original_name:
        trusted["uploaded_original_filename"] = original_name
    else:
        trusted.pop("uploaded_original_filename", None)
    return trusted


def store_uploaded_backup(
    file_stream,
    original_filename: object,
    uploaded_by: str,
    uploaded_by_display_name: str,
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    backup_dir = get_backup_dir(project_root)
    os.makedirs(backup_dir, exist_ok=True)

    source_tmp_path = _copy_upload_to_temp(file_stream, backup_dir)
    rewritten_tmp_path = None
    try:
        original_manifest = validate_backup_zip(source_tmp_path, deep=True)
        entries = _load_zip_entries(source_tmp_path)

        moment = _utc_now()
        trusted_manifest = _trusted_uploaded_manifest(
            original_manifest,
            uploaded_at=_format_created_at(moment),
            uploaded_by=uploaded_by,
            uploaded_by_display_name=uploaded_by_display_name,
            original_filename=original_filename,
        )
        entries["manifest.json"] = _json_bytes(trusted_manifest)

        final_backup_id, final_path = _allocate_backup_destination(backup_dir, moment)

        fd, rewritten_tmp_path = tempfile.mkstemp(
            prefix=".uploaded_backup_",
            suffix=".zip.tmp",
            dir=backup_dir,
        )
        os.close(fd)
        _write_zip(rewritten_tmp_path, entries)
        trusted_manifest = validate_backup_zip(rewritten_tmp_path, deep=True)
        os.replace(rewritten_tmp_path, final_path)
        rewritten_tmp_path = None

        return _metadata_from_manifest(
            final_backup_id,
            os.path.basename(final_path),
            final_path,
            trusted_manifest,
            project_root=project_root,
            valid=True,
            invalid_reason=None,
        )
    finally:
        for tmp_path in (source_tmp_path, rewritten_tmp_path):
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


def create_backup(
    created_by: str,
    created_by_display_name: str,
    comment: object = "",
    backup_kind: str = "manual",
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    comment = normalize_comment(comment)
    if backup_kind not in ALLOWED_BACKUP_KINDS:
        raise BackupError("Invalid backup kind", code="INVALID_BACKUP_KIND", status_code=400)

    files, base_state, individual_state = _collect_source_files(project_root)
    moment = _utc_now()
    created_at = _format_created_at(moment)
    manifest = _build_manifest(
        files=files,
        base_state=base_state,
        individual_state=individual_state,
        created_at=created_at,
        created_by=created_by,
        created_by_display_name=created_by_display_name,
        comment=comment,
        backup_kind=backup_kind,
        project_root=project_root,
    )
    entries = {"manifest.json": _json_bytes(manifest), **files}

    backup_dir = get_backup_dir(project_root)
    os.makedirs(backup_dir, exist_ok=True)
    final_backup_id, final_path = _allocate_backup_destination(backup_dir, moment)

    fd, tmp_path = tempfile.mkstemp(prefix=".backup_", suffix=".zip.tmp", dir=backup_dir)
    os.close(fd)
    try:
        _write_zip(tmp_path, entries)
        validate_backup_zip(tmp_path, deep=True)
        os.replace(tmp_path, final_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return _metadata_from_manifest(
        final_backup_id,
        os.path.basename(final_path),
        final_path,
        manifest,
        project_root=project_root,
        valid=True,
        invalid_reason=None,
    )


def _specific_limit_for_archive_path(path: str) -> int:
    if path == "html/schedule.html":
        return MAX_SCHEDULE_HTML_BYTES
    if path.startswith("state/") or path == "manifest.json":
        return MAX_JSON_BYTES
    if path.startswith("spiski/"):
        return MAX_SPISKI_FILE_BYTES
    return MAX_SINGLE_FILE_UNCOMPRESSED_BYTES


def _validate_zip_entry_info(info: zipfile.ZipInfo) -> None:
    name = info.filename
    if not name or "\\" in name:
        raise BackupValidationError("Unsafe ZIP entry path", code="UNSAFE_ZIP_ENTRY", status_code=400)
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise BackupValidationError("Unsafe ZIP entry path", code="UNSAFE_ZIP_ENTRY", status_code=400)
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise BackupValidationError("Unsafe ZIP entry path", code="UNSAFE_ZIP_ENTRY", status_code=400)
    if info.flag_bits & 0x1:
        raise BackupValidationError("Encrypted ZIP entries are not supported", code="ENCRYPTED_ZIP_ENTRY", status_code=400)
    mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    if file_type and not stat.S_ISREG(mode):
        raise BackupValidationError("ZIP entry must be a regular file", code="UNSAFE_ZIP_ENTRY", status_code=400)
    if info.is_dir():
        raise BackupValidationError("ZIP directory entries are not supported", code="UNEXPECTED_ZIP_ENTRY", status_code=400)
    if info.file_size > MAX_SINGLE_FILE_UNCOMPRESSED_BYTES:
        raise BackupValidationError("ZIP entry is too large", code="ZIP_ENTRY_TOO_LARGE", status_code=400)
    specific_limit = _specific_limit_for_archive_path(name)
    if info.file_size > specific_limit:
        raise BackupValidationError("ZIP entry exceeds path limit", code="ZIP_ENTRY_TOO_LARGE", status_code=400)


def _read_zip_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    specific_limit = _specific_limit_for_archive_path(info.filename)
    try:
        with archive.open(info, "r") as handle:
            data = handle.read(specific_limit + 1)
    except Exception as exc:
        raise BackupValidationError("Failed to read ZIP entry", code="INVALID_BACKUP_ZIP", status_code=400) from exc
    if len(data) > specific_limit:
        raise BackupValidationError("ZIP entry exceeds path limit", code="ZIP_ENTRY_TOO_LARGE", status_code=400)
    return data


def _raw_zip_central_directory_names(path: str) -> list[bytes]:
    try:
        file_size = os.path.getsize(path)
        with open(path, "rb") as handle:
            tail_size = min(file_size, 65557)
            handle.seek(file_size - tail_size)
            tail = handle.read(tail_size)
            eocd_offset_in_tail = tail.rfind(b"PK\x05\x06")
            if eocd_offset_in_tail < 0 or len(tail) - eocd_offset_in_tail < 22:
                return []
            eocd = tail[eocd_offset_in_tail : eocd_offset_in_tail + 22]
            fields = struct.unpack("<4s4H2LH", eocd)
            central_dir_size = fields[5]
            central_dir_offset = fields[6]
            if central_dir_offset < 0 or central_dir_size < 0:
                return []
            if central_dir_offset + central_dir_size > file_size:
                return []
            handle.seek(central_dir_offset)
            central_dir = handle.read(central_dir_size)
    except OSError:
        return []

    names: list[bytes] = []
    offset = 0
    while offset + 46 <= len(central_dir):
        if central_dir[offset : offset + 4] != b"PK\x01\x02":
            break
        filename_len = int.from_bytes(central_dir[offset + 28 : offset + 30], "little")
        extra_len = int.from_bytes(central_dir[offset + 30 : offset + 32], "little")
        comment_len = int.from_bytes(central_dir[offset + 32 : offset + 34], "little")
        filename_start = offset + 46
        filename_end = filename_start + filename_len
        if filename_end > len(central_dir):
            break
        names.append(central_dir[filename_start:filename_end])
        offset = filename_end + extra_len + comment_len
    return names


def _validate_raw_zip_entry_names(path: str) -> None:
    for raw_name in _raw_zip_central_directory_names(os.fspath(path)):
        if b"\\" in raw_name:
            raise BackupValidationError("Unsafe ZIP entry path", code="UNSAFE_ZIP_ENTRY", status_code=400)


def _load_zip_entries(path: str) -> dict[str, bytes]:
    _validate_raw_zip_entry_names(path)
    if not zipfile.is_zipfile(path):
        raise BackupValidationError("File is not a ZIP archive", code="INVALID_BACKUP_ZIP", status_code=400)
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if not infos:
                raise BackupValidationError("Backup ZIP is empty", code="EMPTY_BACKUP_ZIP", status_code=400)
            if len(infos) > MAX_ZIP_FILES:
                raise BackupValidationError("Backup ZIP has too many files", code="TOO_MANY_ZIP_ENTRIES", status_code=400)

            seen: set[str] = set()
            total_size = 0
            entries: dict[str, bytes] = {}
            for info in infos:
                _validate_zip_entry_info(info)
                if info.filename in seen:
                    raise BackupValidationError("Duplicate ZIP entry", code="DUPLICATE_ZIP_ENTRY", status_code=400)
                seen.add(info.filename)
                total_size += info.file_size
                if total_size > MAX_UNCOMPRESSED_BYTES:
                    raise BackupValidationError("Backup ZIP is too large", code="ZIP_TOO_LARGE", status_code=400)
                entries[info.filename] = _read_zip_entry(archive, info)
            return entries
    except zipfile.BadZipFile as exc:
        raise BackupValidationError("File is not a valid ZIP archive", code="INVALID_BACKUP_ZIP", status_code=400) from exc


def _validate_exact_archive_paths(entries: dict[str, bytes]) -> None:
    actual = set(entries)
    missing = EXPECTED_ARCHIVE_PATH_SET - actual
    extra = actual - EXPECTED_ARCHIVE_PATH_SET
    if missing:
        raise BackupValidationError(
            f"Backup ZIP is missing required file: {sorted(missing)[0]}",
            code="BACKUP_FILE_MISSING",
            status_code=400,
        )
    if extra:
        raise BackupValidationError(
            f"Backup ZIP contains unexpected file: {sorted(extra)[0]}",
            code="UNEXPECTED_BACKUP_FILE",
            status_code=400,
        )


def _validate_manifest(manifest: Any, entries: dict[str, bytes]) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise BackupValidationError("manifest.json must be an object", code="INVALID_MANIFEST", status_code=400)
    if manifest.get("schema") != BACKUP_SCHEMA:
        raise BackupValidationError("Unsupported backup schema", code="UNSUPPORTED_BACKUP_SCHEMA", status_code=400)
    if manifest.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise BackupValidationError(
            "Unsupported backup schema version",
            code="UNSUPPORTED_BACKUP_SCHEMA_VERSION",
            status_code=400,
        )
    if manifest.get("backup_kind") not in ALLOWED_BACKUP_KINDS:
        raise BackupValidationError("Invalid backup kind", code="INVALID_MANIFEST", status_code=400)

    files = manifest.get("files")
    if not isinstance(files, list):
        raise BackupValidationError("manifest.files must be a list", code="INVALID_MANIFEST", status_code=400)

    seen: set[str] = set()
    for file_entry in files:
        if not isinstance(file_entry, dict):
            raise BackupValidationError("manifest.files entries must be objects", code="INVALID_MANIFEST", status_code=400)
        archive_path = file_entry.get("path")
        if archive_path not in EXPECTED_CONTENT_PATH_SET:
            raise BackupValidationError("manifest.files contains unexpected path", code="INVALID_MANIFEST", status_code=400)
        if archive_path in seen:
            raise BackupValidationError("manifest.files contains duplicate path", code="INVALID_MANIFEST", status_code=400)
        seen.add(archive_path)

        data = entries[archive_path]
        if file_entry.get("sha256") != _sha256(data):
            raise BackupValidationError("Manifest checksum mismatch", code="CHECKSUM_MISMATCH", status_code=400)
        if file_entry.get("size") != len(data):
            raise BackupValidationError("Manifest size mismatch", code="CHECKSUM_MISMATCH", status_code=400)

    if seen != EXPECTED_CONTENT_PATH_SET:
        raise BackupValidationError("manifest.files must list every backup file exactly once", code="INVALID_MANIFEST", status_code=400)
    return manifest


def read_manifest_from_zip(path: str) -> dict[str, Any]:
    entries = _load_zip_entries(path)
    _validate_exact_archive_paths(entries)
    if "manifest.json" not in entries:
        raise BackupValidationError("manifest.json is missing", code="BACKUP_FILE_MISSING", status_code=400)
    manifest = _parse_json_bytes(entries["manifest.json"], label="manifest.json")
    return _validate_manifest(manifest, entries)


def validate_backup_zip(path: str, *, deep: bool = True) -> dict[str, Any]:
    entries = _load_zip_entries(path)
    _validate_exact_archive_paths(entries)
    manifest = _parse_json_bytes(entries["manifest.json"], label="manifest.json")
    manifest = _validate_manifest(manifest, entries)

    if deep:
        validate_base_state(
            _parse_json_bytes(entries["state/base_schedule.json"], label="state/base_schedule.json"),
            label="state/base_schedule.json",
        )
        validate_individual_state(
            _parse_json_bytes(
                entries["state/individual_lessons.json"],
                label="state/individual_lessons.json",
            ),
            label="state/individual_lessons.json",
        )
        validate_schedule_html_bytes(entries["html/schedule.html"])
        for archive_path in SPISKI_ARCHIVE_PATHS:
            validate_spiski_bytes(entries[archive_path], label=archive_path)

    return manifest


def _metadata_from_manifest(
    backup_id: str,
    filename: str,
    path: str,
    manifest: dict[str, Any] | None,
    *,
    project_root: str | None,
    valid: bool,
    invalid_reason: str | None,
) -> dict[str, Any]:
    current_project_root_id = get_project_root_id(project_root)
    manifest = manifest if isinstance(manifest, dict) else {}
    manifest_project_root_id = manifest.get("project_root_id")
    safe_download_url = (
        f"/api/backups/{backup_id}/download" if BACKUP_ID_RE.fullmatch(backup_id) else None
    )
    return {
        "id": backup_id,
        "filename": filename,
        "backup_kind": manifest.get("backup_kind"),
        "created_at": manifest.get("created_at"),
        "created_by": manifest.get("created_by"),
        "created_by_display_name": manifest.get("created_by_display_name"),
        "uploaded_at": manifest.get("uploaded_at"),
        "uploaded_by": manifest.get("uploaded_by"),
        "uploaded_by_display_name": manifest.get("uploaded_by_display_name"),
        "uploaded_original_filename": manifest.get("uploaded_original_filename"),
        "comment": manifest.get("comment") or "",
        "base_revision": manifest.get("base_revision"),
        "individual_revision": manifest.get("individual_revision"),
        "project_root_id": manifest_project_root_id,
        "project_root_matches": (
            manifest_project_root_id == current_project_root_id
            if manifest_project_root_id is not None
            else None
        ),
        "size": os.path.getsize(path) if os.path.exists(path) else None,
        "valid": valid,
        "invalid_reason": invalid_reason,
        "download_url": safe_download_url,
    }


def list_backups(project_root: str | None = None) -> list[dict[str, Any]]:
    backup_dir = get_backup_dir(project_root)
    os.makedirs(backup_dir, exist_ok=True)
    backups: list[dict[str, Any]] = []
    for filename in os.listdir(backup_dir):
        if not filename.endswith(".zip"):
            continue
        path = os.path.join(backup_dir, filename)
        if not os.path.isfile(path):
            continue
        backup_id = filename[:-4]
        manifest: dict[str, Any] | None = None
        valid = True
        invalid_reason = None
        try:
            manifest = validate_backup_zip(path, deep=True)
        except BackupError as exc:
            valid = False
            invalid_reason = exc.message
        except Exception as exc:
            valid = False
            invalid_reason = str(exc)
        if not BACKUP_ID_RE.fullmatch(backup_id):
            valid = False
            invalid_reason = invalid_reason or "Invalid backup filename"
        backups.append(
            _metadata_from_manifest(
                backup_id,
                filename,
                path,
                manifest,
                project_root=project_root,
                valid=valid,
                invalid_reason=invalid_reason,
            )
        )
    backups.sort(key=lambda item: item.get("filename") or "", reverse=True)
    return backups
