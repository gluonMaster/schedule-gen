from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from gear_xls import backup_manager, lock_manager
from gear_xls.runtime_paths import (
    get_base_schedule_path,
    get_individual_lessons_path,
    get_project_root_id,
    get_restore_status_path,
    get_schedule_html_path,
    get_spiski_dir,
)


RESTORE_STALE_AFTER_SECONDS = 600

DEFAULT_RESTORE_STATUS: dict[str, Any] = {
    "active": False,
    "started_at": None,
    "started_by": None,
    "message": None,
    "generation": 0,
    "last_completed_at": None,
    "last_completed_by": None,
    "last_restored_from": None,
    "recovery_required": False,
    "recovery_message": None,
    "safety_backup_id": None,
}

_status_mutex = threading.Lock()
_restore_mutex = threading.Lock()
logger = logging.getLogger(__name__)


class RestoreStatusError(RuntimeError):
    def __init__(
        self,
        message: str,
        code: str = "RESTORE_STATUS_ERROR",
        status_code: int = 400,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class RestoreError(RuntimeError):
    def __init__(
        self,
        message: str,
        code: str = "RESTORE_ERROR",
        status_code: int = 400,
        *,
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.payload = payload or {}


class _RestoreApplyFailure(RuntimeError):
    def __init__(self, message: str, replaced_paths: list[str]):
        super().__init__(message)
        self.replaced_paths = replaced_paths


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_timestamp(moment: datetime | None = None) -> str:
    return (moment or _utc_now()).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _normalize_generation(value: object) -> int:
    try:
        generation = int(value)
    except (TypeError, ValueError):
        return 0
    return max(generation, 0)


def _normalize_status(data: object) -> dict[str, Any]:
    status = dict(DEFAULT_RESTORE_STATUS)
    if not isinstance(data, dict):
        return status

    status["active"] = bool(data.get("active") or data.get("restore_in_progress"))
    status["started_at"] = _optional_text(data.get("started_at"))
    status["started_by"] = _optional_text(data.get("started_by"))
    status["message"] = _optional_text(data.get("message"))
    status["generation"] = _normalize_generation(data.get("generation"))
    status["last_completed_at"] = _optional_text(data.get("last_completed_at"))
    status["last_completed_by"] = _optional_text(data.get("last_completed_by"))
    status["last_restored_from"] = _optional_text(data.get("last_restored_from"))
    status["recovery_required"] = bool(data.get("recovery_required"))
    status["recovery_message"] = _optional_text(data.get("recovery_message"))
    status["safety_backup_id"] = _optional_text(data.get("safety_backup_id"))
    return status


def _status_path(project_root: str | None = None) -> str:
    return get_restore_status_path(project_root)


def _read_status_unlocked(project_root: str | None = None) -> dict[str, Any]:
    path = _status_path(project_root)
    if not os.path.exists(path):
        return dict(DEFAULT_RESTORE_STATUS)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return _normalize_status(json.load(handle))
    except Exception as exc:
        logger.warning("Failed to read restore status %s: %s", path, exc)
        return dict(DEFAULT_RESTORE_STATUS)


def _write_status_unlocked(status: dict[str, Any], project_root: str | None = None) -> dict[str, Any]:
    normalized = _normalize_status(status)
    path = _status_path(project_root)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=directory,
            delete=False,
            suffix=".tmp",
            mode="w",
            encoding="utf-8",
        ) as tmp:
            json.dump(normalized, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
            tmp_path = tmp.name
        os.replace(tmp_path, path)
        return normalized
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def get_restore_status(project_root: str | None = None) -> dict[str, Any]:
    with _status_mutex:
        return _read_status_unlocked(project_root)


def is_restore_stale(
    status: dict[str, Any] | None = None,
    *,
    project_root: str | None = None,
) -> bool:
    current = status if status is not None else get_restore_status(project_root)
    if not current.get("active") or current.get("recovery_required"):
        return False
    started_at = _parse_timestamp(current.get("started_at"))
    if started_at is None:
        return False
    return _utc_now() - started_at > timedelta(seconds=RESTORE_STALE_AFTER_SECONDS)


def is_restore_active(project_root: str | None = None) -> bool:
    status = get_restore_status(project_root)
    return bool(status.get("active") or status.get("recovery_required"))


def begin_restore(
    started_by: str,
    message: str | None = None,
    *,
    safety_backup_id: str | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    with _status_mutex:
        status = _read_status_unlocked(project_root)
        if status.get("active") or status.get("recovery_required"):
            raise RestoreStatusError(
                "Restore is already in progress",
                code="RESTORE_IN_PROGRESS",
                status_code=423,
            )
        status["active"] = True
        status["started_at"] = _format_timestamp()
        status["started_by"] = started_by
        status["message"] = message
        status["recovery_required"] = False
        status["recovery_message"] = None
        status["safety_backup_id"] = safety_backup_id
        return _write_status_unlocked(status, project_root)


def complete_restore(
    completed_by: str,
    restored_from: str | None,
    *,
    safety_backup_id: str | None = None,
    message: str | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    with _status_mutex:
        status = _read_status_unlocked(project_root)
        status["active"] = False
        status["message"] = message
        status["generation"] = _normalize_generation(status.get("generation")) + 1
        status["last_completed_at"] = _format_timestamp()
        status["last_completed_by"] = completed_by
        status["last_restored_from"] = restored_from
        status["recovery_required"] = False
        status["recovery_message"] = None
        status["safety_backup_id"] = safety_backup_id
        return _write_status_unlocked(status, project_root)


def fail_restore_prewrite(
    message: str | None,
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    with _status_mutex:
        status = _read_status_unlocked(project_root)
        status["active"] = False
        status["message"] = message
        status["recovery_required"] = False
        status["recovery_message"] = None
        return _write_status_unlocked(status, project_root)


def mark_recovery_required(
    message: str,
    *,
    safety_backup_id: str | None = None,
    started_by: str | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    with _status_mutex:
        status = _read_status_unlocked(project_root)
        status["active"] = True
        if not status.get("started_at"):
            status["started_at"] = _format_timestamp()
        if started_by is not None:
            status["started_by"] = started_by
        status["message"] = "Recovery required"
        status["recovery_required"] = True
        status["recovery_message"] = message
        status["safety_backup_id"] = safety_backup_id
        return _write_status_unlocked(status, project_root)


def _cleared_status(status: dict[str, Any]) -> dict[str, Any]:
    cleared = dict(DEFAULT_RESTORE_STATUS)
    for key in (
        "generation",
        "last_completed_at",
        "last_completed_by",
        "last_restored_from",
    ):
        cleared[key] = status.get(key)
    return _normalize_status(cleared)


def clear_restore_status(
    *,
    confirm: bool,
    cleared_by: str | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    if confirm is not True:
        raise RestoreStatusError(
            "Explicit confirmation is required",
            code="CONFIRM_REQUIRED",
            status_code=400,
        )

    with _status_mutex:
        status = _read_status_unlocked(project_root)
        recovery_required = bool(status.get("recovery_required"))
        stale = is_restore_stale(status)
        if status.get("active") and not recovery_required and not stale:
            raise RestoreStatusError(
                "Restore mode is active and is not stale",
                code="RESTORE_NOT_STALE",
                status_code=409,
            )
        cleared = _write_status_unlocked(_cleared_status(status), project_root)

    logger.warning(
        "Restore status cleared by %s (recovery_required=%s, stale=%s)",
        cleared_by or "unknown",
        recovery_required,
        stale,
    )
    return cleared


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _load_json_entry(entries: dict[str, bytes], archive_path: str) -> Any:
    try:
        return json.loads(entries[archive_path].decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise RestoreError(
            f"{archive_path} is not valid UTF-8",
            code="INVALID_JSON_STATE",
            status_code=400,
        ) from exc
    except json.JSONDecodeError as exc:
        raise RestoreError(
            f"{archive_path} is not valid JSON",
            code="INVALID_JSON_STATE",
            status_code=400,
        ) from exc


def _normalized_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [_normalized_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalized_json_value(item) for key, item in value.items()}
    return value


def _normalize_base_state(data: Any, *, restore_revision: str, login: str) -> dict[str, Any]:
    backup_manager.validate_base_state(data, label="state/base_schedule.json")
    state = _normalized_json_value(data)
    backup_manager.validate_base_state(state, label="state/base_schedule.json")

    had_published_revision = data.get("published_at") is not None
    if state.get("blocks") or had_published_revision:
        state["published_at"] = restore_revision
        state["published_by"] = login
    else:
        state["published_at"] = None
        state["published_by"] = None
    return {
        "published_at": state.get("published_at"),
        "published_by": state.get("published_by"),
        "blocks": state.get("blocks", []),
    }


def _normalize_individual_state(data: Any, *, restore_revision: str) -> dict[str, Any]:
    backup_manager.validate_individual_state(data, label="state/individual_lessons.json")
    state = _normalized_json_value(data)

    for block in state.get("blocks", []):
        if not isinstance(block, dict):
            continue
        if block.get("lesson_type") == "trial":
            trial_dates = block.get("trial_dates") or []
            normalized_dates = sorted(dict.fromkeys(str(item).strip() for item in trial_dates))
            block["trial_dates"] = normalized_dates
        else:
            block.pop("trial_dates", None)

    backup_manager.validate_individual_state(state, label="state/individual_lessons.json")
    return {
        "last_modified": restore_revision,
        "blocks": state.get("blocks", []),
    }


def _normalize_spiski_bytes(data: bytes, *, label: str) -> bytes:
    backup_manager.validate_spiski_bytes(data, label=label)
    text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    normalized = text.encode("utf-8")
    backup_manager.validate_spiski_bytes(normalized, label=label)
    return normalized


def _load_validated_backup(
    backup_id: str,
    *,
    allow_foreign_project: bool,
    project_root: str | None = None,
) -> tuple[str, dict[str, Any], dict[str, bytes]]:
    try:
        path = backup_manager.get_backup_path(backup_id, project_root)
    except backup_manager.BackupError as exc:
        raise RestoreError(exc.message, code=exc.code, status_code=exc.status_code) from exc

    if not os.path.exists(path):
        raise RestoreError("Backup not found", code="BACKUP_NOT_FOUND", status_code=404)

    try:
        manifest = backup_manager.validate_backup_zip(path, deep=True)
        entries = backup_manager._load_zip_entries(path)
    except backup_manager.BackupError as exc:
        raise RestoreError(exc.message, code=exc.code, status_code=exc.status_code) from exc

    source_project_root_id = manifest.get("project_root_id")
    current_project_root_id = get_project_root_id(project_root)
    if (
        source_project_root_id is not None
        and source_project_root_id != current_project_root_id
        and not allow_foreign_project
    ):
        raise RestoreError(
            "Backup was created for a different project root",
            code="PROJECT_ROOT_MISMATCH",
            status_code=409,
            payload={
                "backup_project_root_id": source_project_root_id,
                "current_project_root_id": current_project_root_id,
            },
        )

    return path, manifest, entries


def _prepare_restore_payload(
    entries: dict[str, bytes],
    *,
    login: str,
    restore_revision: str,
    update_revisions: bool,
) -> dict[str, Any]:
    base_state = _load_json_entry(entries, "state/base_schedule.json")
    individual_state = _load_json_entry(entries, "state/individual_lessons.json")

    if update_revisions:
        normalized_base = _normalize_base_state(
            base_state,
            restore_revision=restore_revision,
            login=login,
        )
        normalized_individual = _normalize_individual_state(
            individual_state,
            restore_revision=restore_revision,
        )
    else:
        backup_manager.validate_base_state(base_state, label="state/base_schedule.json")
        backup_manager.validate_individual_state(
            individual_state,
            label="state/individual_lessons.json",
        )
        normalized_base = {
            "published_at": base_state.get("published_at"),
            "published_by": base_state.get("published_by"),
            "blocks": base_state.get("blocks", []),
        }
        normalized_individual = {
            "last_modified": individual_state.get("last_modified"),
            "blocks": individual_state.get("blocks", []),
        }

    schedule_html = entries["html/schedule.html"]
    backup_manager.validate_schedule_html_bytes(schedule_html)

    spiski = {}
    for filename in backup_manager.ALLOWED_SPISKI_FILENAMES:
        archive_path = f"spiski/{filename}"
        spiski[filename] = _normalize_spiski_bytes(entries[archive_path], label=archive_path)

    return {
        "base": _json_bytes(normalized_base),
        "individual": _json_bytes(normalized_individual),
        "schedule_html": schedule_html,
        "spiski": spiski,
        "base_revision": normalized_base.get("published_at"),
        "individual_revision": normalized_individual.get("last_modified"),
    }


def _restore_operations(payload: dict[str, Any], project_root: str | None = None) -> list[tuple[str, bytes]]:
    operations: list[tuple[str, bytes]] = [
        (get_base_schedule_path(project_root), payload["base"]),
        (get_individual_lessons_path(project_root), payload["individual"]),
    ]
    spiski_dir = get_spiski_dir(project_root)
    for filename in backup_manager.ALLOWED_SPISKI_FILENAMES:
        operations.append((os.path.join(spiski_dir, filename), payload["spiski"][filename]))
    operations.append((get_schedule_html_path(project_root), payload["schedule_html"]))
    return operations


def _replace_file(path: str, data: bytes) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=directory,
            delete=False,
            suffix=".tmp",
            mode="wb",
        ) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        os.replace(tmp_path, path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _apply_restore_payload(
    payload: dict[str, Any],
    *,
    project_root: str | None = None,
) -> list[str]:
    replaced: list[str] = []
    for path, data in _restore_operations(payload, project_root):
        try:
            _replace_file(path, data)
            replaced.append(path)
        except Exception as exc:
            raise _RestoreApplyFailure(
                str(exc) or exc.__class__.__name__,
                list(replaced),
            ) from exc
    return replaced


def _require_active_lock(login: str, *, project_root: str | None = None) -> None:
    state = lock_manager.get_lock_status(project_root)
    if state.get("holder") != login:
        raise RestoreError(
            "Active edit lock held by the current admin is required",
            code="NO_LOCK",
            status_code=403,
            payload={"lock_holder": state.get("holder")},
        )


def _create_safety_backup(
    backup_id: str,
    login: str,
    display_name: str,
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    return backup_manager.create_backup(
        login,
        display_name,
        comment=f"Safety backup before restore from {backup_id}",
        backup_kind="safety",
        project_root=project_root,
    )


def _rollback_from_safety_backup(
    safety_backup_id: str,
    *,
    login: str,
    project_root: str | None = None,
) -> list[str]:
    _, _, safety_entries = _load_validated_backup(
        safety_backup_id,
        allow_foreign_project=True,
        project_root=project_root,
    )
    payload = _prepare_restore_payload(
        safety_entries,
        login=login,
        restore_revision=_format_timestamp(),
        update_revisions=False,
    )
    return _apply_restore_payload(payload, project_root=project_root)


def restore_backup(
    backup_id: str,
    login: str,
    display_name: str,
    allow_foreign_project: bool = False,
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    _require_active_lock(login, project_root=project_root)
    try:
        backup_id = backup_manager.validate_backup_id(backup_id)
    except backup_manager.BackupError as exc:
        raise RestoreError(exc.message, code=exc.code, status_code=exc.status_code) from exc
    _, _, entries = _load_validated_backup(
        backup_id,
        allow_foreign_project=allow_foreign_project,
        project_root=project_root,
    )
    restore_revision = _format_timestamp()
    payload = _prepare_restore_payload(
        entries,
        login=login,
        restore_revision=restore_revision,
        update_revisions=True,
    )

    if not _restore_mutex.acquire(blocking=False):
        raise RestoreError(
            "Restore is already in progress",
            code="RESTORE_IN_PROGRESS",
            status_code=423,
        )

    safety_backup: dict[str, Any] | None = None
    replaced_paths: list[str] = []
    restore_started = False
    try:
        try:
            begin_restore(
                login,
                f"Restoring from backup {backup_id}",
                project_root=project_root,
            )
            restore_started = True
            safety_backup = _create_safety_backup(
                backup_id,
                login,
                display_name,
                project_root=project_root,
            )
            with _status_mutex:
                status = _read_status_unlocked(project_root)
                status["safety_backup_id"] = safety_backup["id"]
                _write_status_unlocked(status, project_root)

            replaced_paths = _apply_restore_payload(payload, project_root=project_root)
            lock_manager.clear_for_restore(login, project_root=project_root)
            status = complete_restore(
                login,
                backup_id,
                safety_backup_id=safety_backup["id"],
                message="Restore completed",
                project_root=project_root,
            )
            return {
                "ok": True,
                "restored_from": backup_id,
                "safety_backup": {
                    "id": safety_backup["id"],
                    "download_url": safety_backup["download_url"],
                },
                "base_revision": payload["base_revision"],
                "individual_revision": payload["individual_revision"],
                "restore_generation": int(status.get("generation") or 0),
            }
        except RestoreStatusError as exc:
            raise RestoreError(exc.message, code=exc.code, status_code=exc.status_code) from exc
        except backup_manager.BackupError as exc:
            raise RestoreError(exc.message, code=exc.code, status_code=exc.status_code) from exc
        except RestoreError:
            raise
        except _RestoreApplyFailure as exc:
            replaced_paths = exc.replaced_paths
            raise RestoreError(
                str(exc) or exc.__class__.__name__,
                code="RESTORE_FAILED",
                status_code=500,
            ) from exc
        except Exception as exc:
            raise RestoreError(
                str(exc) or exc.__class__.__name__,
                code="RESTORE_FAILED",
                status_code=500,
            ) from exc
    except RestoreError as exc:
        safety_backup_id = safety_backup.get("id") if safety_backup else None
        if not replaced_paths:
            if restore_started:
                fail_restore_prewrite(
                    exc.message,
                    project_root=project_root,
                )
            raise

        try:
            if safety_backup_id is None:
                raise RuntimeError("Safety backup was not created")
            _rollback_from_safety_backup(
                safety_backup_id,
                login=login,
                project_root=project_root,
            )
            status = complete_restore(
                login,
                safety_backup_id,
                safety_backup_id=safety_backup_id,
                message="Restore rolled back after failure",
                project_root=project_root,
            )
        except Exception as rollback_exc:
            status = mark_recovery_required(
                str(rollback_exc) or rollback_exc.__class__.__name__,
                safety_backup_id=safety_backup_id,
                started_by=login,
                project_root=project_root,
            )
            raise RestoreError(
                "Restore failed after partial write and rollback failed",
                code="RESTORE_PARTIAL_FAILURE",
                status_code=500,
                payload={
                    "safety_backup": (
                        {
                            "id": safety_backup_id,
                            "download_url": f"/api/backups/{safety_backup_id}/download",
                        }
                        if safety_backup_id
                        else None
                    ),
                    "restore_generation": int(status.get("generation") or 0),
                    "recovery_required": True,
                    "recovery_message": status.get("recovery_message"),
                    "cause_code": exc.code,
                    "cause": exc.message,
                },
            ) from rollback_exc

        raise RestoreError(
            "Restore failed after partial write; rollback from safety backup succeeded",
            code="RESTORE_ROLLED_BACK",
            status_code=500,
            payload={
                "failed_restore_from": backup_id,
                "safety_backup": {
                    "id": safety_backup_id,
                    "download_url": f"/api/backups/{safety_backup_id}/download",
                },
                "restore_generation": int(status.get("generation") or 0),
                "cause_code": exc.code,
                "cause": exc.message,
            },
        ) from exc
    finally:
        _restore_mutex.release()
