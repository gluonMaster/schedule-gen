"""Snapshot provenance checks and guarded application of a generated editor.

Flask and the GUI generator may run in different processes. Writers therefore
take the existing file locks (individual, then base: the order used by
state_manager.publish_base) and compare revisions inside them. Lock ownership
(lock.json) is only read here; a generation never clears another user's lock.
"""
import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from gear_xls.base_schedule_manager import _acquire_file_lock, _normalize_revision, _release_file_lock
from gear_xls.schedule_exchange import normalize_sync_metadata

BASE_FILE = "base_schedule.json"
INDIVIDUAL_FILE = "individual_lessons.json"
LOCK_WAIT_SECONDS = 10.0
LEGACY_IMPORT_MESSAGE = (
    "Excel без метаданных исходного снимка допустим только для первичного импорта "
    "в пустое состояние. Сначала создайте актуальный экспорт."
)


class SnapshotConflictError(RuntimeError):
    """The snapshot may not replace or publish the current editor state."""


GUARD_KEYS = ("expected_individual_revision", "lock_version", "expected_html_revision")
GUARD_ERRORS = {
    "NO_LOCK": (403, "No active lock"),
    "STALE_LOCK": (403, "Сессия редактирования в этой вкладке устарела. Обновите страницу и начните редактирование снова."),
    "INDIVIDUAL_REVISION_CONFLICT": (
        409, "Индивидуальные занятия изменились на сервере. Изменение не применено: обновите данные и повторите."),
    "SCHEDULE_HTML_CHANGED": (
        409, "Расписание было перегенерировано или восстановлено после загрузки страницы. Обновите страницу."),
}


def parse_write_guard(login, data, revision_key="expected_individual_revision"):
    """(guard, None) or (None, missing marker); a missing marker never allows a blind write."""
    lock_version = data.get("lock_version")
    try:
        lock_version = None if isinstance(lock_version, bool) else int(lock_version)
    except (TypeError, ValueError):
        lock_version = None
    if revision_key not in data:
        return None, revision_key
    if lock_version is None:
        return None, "lock_version"
    target = "expected_revision" if revision_key == "expected_individual_revision" else revision_key
    return {"login": login, "lock_version": lock_version, target: data[revision_key]}, None


def schedule_html_revision(data):
    return hashlib.sha256(data).hexdigest()[:20]


def write_guard_error(lock_state, current_revision, guard, check_revision=True):
    """Error code for a guarded write, checked inside the individual critical section."""
    if guard is None:
        return None
    if lock_state.get("holder") != guard.get("login"):
        return "NO_LOCK"
    if lock_state.get("version") != guard.get("lock_version"):
        return "STALE_LOCK"
    if (check_revision and "expected_revision" in guard
            and _normalize_revision(guard["expected_revision"]) != _normalize_revision(current_revision)):
        return "INDIVIDUAL_REVISION_CONFLICT"
    return None


def _state_is_empty(base_state, individual_state):
    return not (base_state.get("blocks") or base_state.get("published_at")
                or individual_state.get("blocks") or individual_state.get("last_modified"))


def snapshot_conflict(sync_metadata, base_state, individual_state):
    """Why a normalized snapshot may not replace/publish the current state, or None."""
    if sync_metadata is None:
        return None if _state_is_empty(base_state, individual_state) else LEGACY_IMPORT_MESSAGE
    if sync_metadata["snapshot_scope"] != "full":
        return "Частичный Excel-снимок не может заменять состояние редактора."
    changed = []
    if _normalize_revision(sync_metadata["source_base_revision"]) != _normalize_revision(base_state.get("published_at")):
        changed.append("базовое расписание")
    if _normalize_revision(sync_metadata["source_individual_revision"]) != _normalize_revision(
            individual_state.get("last_modified")):
        changed.append("индивидуальные занятия/аренда")
    if changed:
        return ("После экспорта изменилось: " + ", ".join(changed) + ". Результат не применён: "
                "создайте новый экспорт из веб-редактора и повторите.")
    return None


def export_snapshot_conflict(sync_metadata, records, client_html_revision, *,
                             html_revision, base_revision, individual_state):
    """Server confirmation that an exported full payload matches the revisions it claims."""
    if sync_metadata is None or sync_metadata["snapshot_scope"] != "full":
        return None
    stale = []
    if client_html_revision is None or _normalize_revision(client_html_revision) != _normalize_revision(html_revision):
        stale.append("страница редактора")
    if _normalize_revision(sync_metadata["source_base_revision"]) != _normalize_revision(base_revision):
        stale.append("базовое расписание")
    if _normalize_revision(sync_metadata["source_individual_revision"]) != _normalize_revision(
            individual_state.get("last_modified")):
        stale.append("индивидуальные занятия/аренда")
    else:
        exported = {str(row.get("block_id") or "").strip() for row in records or [] if isinstance(row, dict)}
        current = {str(block.get("id")) for block in individual_state.get("blocks", [])
                   if isinstance(block, dict) and block.get("id")}
        if exported - {""} != current:
            stale.append("состав индивидуальных занятий/аренды")
    if not stale:
        return None
    return ("Экспорт отменён: данные страницы не совпадают с текущим состоянием сервера ("
            + ", ".join(stale) + "). Обновите страницу и повторите экспорт.")


def read_editor_state(state_dir):
    """Raw base/individual state without pruning; unreadable files are not treated as empty."""
    states = []
    for name, empty in ((BASE_FILE, {"published_at": None, "blocks": []}),
                        (INDIVIDUAL_FILE, {"last_modified": None, "blocks": []})):
        path = os.path.join(state_dir, name)
        if not os.path.exists(path):
            states.append(dict(empty))
            continue
        try:
            with open(path, "r", encoding="utf-8") as source:
                data = json.load(source)
        except (OSError, ValueError) as exc:
            raise SnapshotConflictError(f"Не удалось прочитать {name}: {exc}") from exc
        if not isinstance(data, dict):
            raise SnapshotConflictError(f"Некорректное содержимое {name}")
        states.append(data)
    return states[0], states[1]


def check_snapshot_current(sync_metadata, state_dir):
    message = snapshot_conflict(normalize_sync_metadata(sync_metadata), *read_editor_state(state_dir))
    if message:
        raise SnapshotConflictError(message)


@contextmanager
def _waiting_file_lock(path, timeout):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    deadline = time.monotonic() + timeout
    with open(path, "a+b") as lock_fp:
        while True:
            try:
                backend = _acquire_file_lock(lock_fp)
                break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise SnapshotConflictError(
                        "Состояние редактора занято другой операцией. Повторите генерацию позже."
                    ) from None
                time.sleep(0.05)
        try:
            yield
        finally:
            _release_file_lock(lock_fp, backend)


@contextmanager
def locked_editor_state(state_dir, timeout=LOCK_WAIT_SECONDS):
    with _waiting_file_lock(os.path.join(state_dir, INDIVIDUAL_FILE + ".lock"), timeout):
        with _waiting_file_lock(os.path.join(state_dir, BASE_FILE + ".lock"), timeout):
            yield


def _check_no_restore(state_dir):
    path = os.path.join(state_dir, "restore_status.json")
    try:
        with open(path, "r", encoding="utf-8") as source:
            status = json.load(source)
    except (OSError, ValueError):
        return
    if isinstance(status, dict) and (status.get("active") or status.get("restore_in_progress")
                                     or status.get("recovery_required")):
        raise SnapshotConflictError("Идёт восстановление из резервной копии; генерация не применена.")


def _prepared_blocks(individual_blocks, sync_metadata):
    blocks = [dict(block) for block in individual_blocks or []]
    seen_ids = set()
    for block in blocks:
        if not block.get("id"):
            if sync_metadata is not None:
                raise SnapshotConflictError("Управляемая запись снимка не содержит block_id")
            block["id"] = str(uuid.uuid4())  # one-time primary legacy import only
        if block["id"] in seen_ids:
            raise SnapshotConflictError(f"Duplicate block_id: {block['id']}")
        seen_ids.add(block["id"])
    return blocks


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _replace_file(path, data):
    from gear_xls.restore_manager import _replace_file as replace_file

    replace_file(path, data)


def replace_files_with_rollback(operations):
    """Atomic per-file writes; already replaced files get their previous bytes back on failure."""
    previous = {}
    for path, _data in operations:
        previous[path] = None
        if os.path.exists(path):
            with open(path, "rb") as source:
                previous[path] = source.read()
    replaced = []
    try:
        for path, data in operations:
            _replace_file(path, data)
            replaced.append(path)
    except Exception as exc:
        failures = []
        for path in reversed(replaced):
            try:
                if previous[path] is None:
                    os.remove(path)
                else:
                    _replace_file(path, previous[path])
            except Exception as rollback_exc:  # report every file that could not be restored
                failures.append(f"{path}: {rollback_exc}")
        if failures:
            raise SnapshotConflictError(
                "Применение генерации прервано, откат не завершён: " + "; ".join(failures)
            ) from exc
        raise SnapshotConflictError(
            f"Применение генерации прервано ({exc}); прежние HTML/JSON восстановлены."
        ) from exc


def apply_generated_state(individual_blocks, sync_metadata, state_dir, html_source=None, html_target=None):
    """Replace the editor HTML/JSON with a prepared generation if its snapshot is still current."""
    sync_metadata = normalize_sync_metadata(sync_metadata)
    if sync_metadata is not None and sync_metadata["snapshot_scope"] != "full":
        raise SnapshotConflictError("Частичный Excel-снимок не может заменять состояние редактора.")
    blocks = _prepared_blocks(individual_blocks, sync_metadata)
    html_bytes = None
    if html_source is not None:
        with open(html_source, "rb") as source:
            html_bytes = source.read()

    with locked_editor_state(state_dir):
        _check_no_restore(state_dir)
        base_state, individual_state = read_editor_state(state_dir)
        message = snapshot_conflict(sync_metadata, base_state, individual_state)
        if message:
            raise SnapshotConflictError(message)
        if sync_metadata is not None:
            current_ids = {block.get("id") for block in individual_state.get("blocks", []) if isinstance(block, dict)}
            generated_ids = {block["id"] for block in blocks}
            if current_ids != generated_ids:
                raise SnapshotConflictError(
                    "Управляемые записи результата не совпадают с экспортированным снимком "
                    f"(нет: {sorted(current_ids - generated_ids)}, лишние: {sorted(generated_ids - current_ids)})."
                )
        # A generation always gets a new individual revision so the same snapshot applies only once.
        revision = datetime.now(timezone.utc).isoformat()
        operations = []
        if html_bytes is not None:
            operations.append((html_target, html_bytes))
        operations.append((os.path.join(state_dir, BASE_FILE),
                           _json_bytes({"published_at": None, "published_by": None, "blocks": []})))
        operations.append((os.path.join(state_dir, INDIVIDUAL_FILE),
                           _json_bytes({"last_modified": revision, "blocks": blocks})))
        replace_files_with_rollback(operations)
    return revision
