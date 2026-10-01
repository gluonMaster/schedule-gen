"""Verifiable repair of legacy Vermietung records in an explicitly given editor state directory.

    dry-run --state-dir DIR --out PLAN.json [--from-plan OLD.json]   (default; reads files only)
    apply   --state-dir DIR --plan PLAN.json --expect-base SHA --expect-individual SHA --backup-dir NEW_DIR
    restore --state-dir DIR --backup-dir DIR

Only records with lesson_type=rental or the exact legacy subject (trim/casefold "Vermietung") are
considered. Base copies are removed only when their full booking semantics match; competing managed
IDs, unclear dates and dates differing from a managed booking stay ambiguities until the plan's
"resolution" field decides them. Apply re-reads the inputs under the phase-4 file locks
(snapshot_guard), refuses an active operator lock, saves the original bytes before the first write
and replaces the files with rollback. Restore puts these bytes back only if nothing changed since.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import date, datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from gear_xls import snapshot_guard  # noqa: E402
from gear_xls.backup_manager import (  # noqa: E402
    BackupValidationError, validate_base_state, validate_individual_state,
)
from gear_xls.day_constants import WEB_EDITOR_DAY_SET  # noqa: E402
from gear_xls.lesson_type_utils import is_legacy_rental_subject, validate_rental_dates  # noqa: E402
from gear_xls.room_name_utils import normalize_room_name  # noqa: E402
from gear_xls.schedule_exchange import dates_from_record  # noqa: E402

PLAN_FORMAT = "schedgen.rental_repair_plan"
BACKUP_FORMAT = "schedgen.rental_repair_backup"
FILES = (snapshot_guard.BASE_FILE, snapshot_guard.INDIVIDUAL_FILE)
LEGACY_TYPES = ("group", "individual", "trial")
DATE_FIELDS = ("trial_dates", "rental_dates", "trial_dates_json", "rental_dates_json")
BASE_ONLY_FIELDS = ("duration", "room_display", "block_id", "source_layer")
TIME_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")


class RepairError(RuntimeError):
    """The plan cannot be created, applied or restored safely."""


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(block, field):
    value = block.get(field)
    return "" if value is None else str(value).strip()


def _minutes(value):
    if not isinstance(value, str) or not TIME_RE.fullmatch(value.strip()):
        raise ValueError(f"некорректное время {value!r}")
    hours, minutes = value.strip().split(":")
    return int(hours) * 60 + int(minutes)


def _is_rental_record(block):
    return _text(block, "lesson_type") == "rental" or is_legacy_rental_subject(block.get("subject"))


def _block_dates(block):
    """Actual booking dates; conflicting or malformed date fields are an ambiguity, not a guess."""
    day = _text(block, "day")
    trial = dates_from_record(block, "trial_dates")
    rental = dates_from_record(block, "rental_dates")
    for field, values in (("trial_dates", trial), ("rental_dates", rental)):
        error = validate_rental_dates(day, values) if values else None
        if error:
            raise ValueError(error.replace("rental_dates", field))
    if trial and rental and sorted(set(trial)) != sorted(set(rental)):
        raise ValueError("trial_dates и rental_dates содержат разные даты")
    dates = sorted(set(trial or rental))
    error = validate_rental_dates(day, dates)
    if error:
        raise ValueError(error)
    return dates


def _signature(block, dates):
    """Full booking semantics; old lesson_type and rendering fields are deliberately ignored."""
    day = _text(block, "day")
    if day not in WEB_EDITOR_DAY_SET:
        raise ValueError(f"некорректный день {day!r}")
    building = _text(block, "building")
    room = normalize_room_name(block.get("room"), building)
    if not building or not room:
        raise ValueError("нет здания или помещения")
    start, end = _minutes(block.get("start_time")), _minutes(block.get("end_time"))
    if end <= start:
        raise ValueError("конец не позже начала")
    duration = block.get("duration")
    if duration not in (None, ""):
        try:
            consistent = int(float(duration)) == end - start
        except (TypeError, ValueError):
            consistent = False
        if not consistent:
            raise ValueError(f"длительность {duration!r} не совпадает с временем")
    return (building, room, day, start, end, _text(block, "subject").casefold(),
            _text(block, "teacher"), _text(block, "students"), tuple(dates))


def _describe(block, layer, index):
    result = {"layer": layer, "index": index}
    for field in ("id", "lesson_type", "building", "room", "day", "start_time", "end_time",
                  "subject", "teacher", "students", "trial_dates", "rental_dates"):
        if field in block:
            result[field] = block[field]
    return result


def _converted(block, dates):
    record = {key: value for key, value in block.items() if key not in DATE_FIELDS}
    record.update(lesson_type="rental", rental_dates=list(dates))
    return record


def _created(block, dates, block_id):
    record = {"id": block_id}
    record.update((key, value) for key, value in block.items()
                  if key not in DATE_FIELDS + BASE_ONLY_FIELDS + ("id", "lesson_type"))
    record.update(lesson_type="rental", rental_dates=list(dates))
    return record


def _resolution_error(kind, resolution, ids=(), day=None):
    if resolution is None or resolution == "skip":
        return None
    if kind == "competing_ids" and isinstance(resolution, dict) and resolution.get("keep_id") in ids:
        return None
    if kind == "dates" and isinstance(resolution, dict) and isinstance(resolution.get("rental_dates"), list):
        return validate_rental_dates(day, resolution["rental_dates"])
    if kind == "dates_differ" and resolution in ("migrate", "drop_copies"):
        return None
    return f"недопустимое решение для {kind}"


def build_plan(base_state, individual_state, *, inputs, previous=None, calculation_date=None, new_id=None):
    """Return (plan, proposed state). Pure: reads nothing and writes nothing."""
    previous = previous or {}
    resolutions = {item["key"]: item.get("resolution") for item in previous.get("ambiguities", [])}
    pinned = {op["signature_key"]: op["id"] for op in previous.get("operations", {}).get("create", [])}
    new_id = new_id or (lambda: str(uuid.uuid4()))
    calculation_date = calculation_date or date.today()
    base_blocks = list(base_state.get("blocks") or [])
    individual_blocks = list(individual_state.get("blocks") or [])
    ops = {"convert": [], "remove_managed": [], "remove_base": [], "create": []}
    ambiguities = []

    def ambiguity(key, kind, message, records, options, ids=(), day=None):
        resolution = resolutions.get(key)
        item = {"key": key, "kind": kind, "message": message, "records": records,
                "options": options, "resolution": resolution}
        error = _resolution_error(kind, resolution, ids, day)
        if error:
            item["resolution_error"], resolution = error, None
        ambiguities.append(item)
        return resolution

    managed, loose = [], set()
    for index, block in enumerate(individual_blocks):
        if not isinstance(block, dict) or not _is_rental_record(block):
            continue
        lesson_type, key = _text(block, "lesson_type"), f"managed:{block.get('id') or index}"
        record = _describe(block, "individual", index)
        if lesson_type not in ("rental",) + LEGACY_TYPES:
            ambiguity(key, "unsupported_type", f"Vermietung с типом {lesson_type!r} не преобразуется "
                      "автоматически", [record], ["skip"])
            continue
        try:
            dates = _block_dates(block) if lesson_type != "rental" else sorted(set(block.get("rental_dates") or []))
        except ValueError as exc:
            try:
                loose.add(_signature(block, ())[:-1])
            except ValueError:
                pass
            resolution = ambiguity(key, "dates", f"Даты неоднозначны: {exc}", [record],
                                   [{"rental_dates": ["YYYY-MM-DD"]}, "skip"], day=_text(block, "day"))
            if not isinstance(resolution, dict):
                continue
            dates = sorted(set(resolution["rental_dates"]))
        try:
            signature = _signature(block, dates)
        except ValueError as exc:
            ambiguity(key, "invalid_record", f"Запись не проверяется: {exc}", [record], ["skip"])
            continue
        loose.add(signature[:-1])
        converted = _converted(block, dates) if lesson_type != "rental" else None
        managed.append({"index": index, "id": block.get("id"), "block": block, "lesson_type": lesson_type,
                        "converted": converted, "signature": signature, "record": record})

    base_groups = {}
    for index, block in enumerate(base_blocks):
        if not isinstance(block, dict) or not _is_rental_record(block):
            continue
        try:
            signature = _signature(block, _block_dates(block))
        except ValueError as exc:
            ambiguity(f"base:{index}:{_sha256(_canonical(block).encode())[:12]}", "invalid_base_record",
                      f"Запись базы не проверяется: {exc}", [_describe(block, "base", index)], ["skip"])
            continue
        base_groups.setdefault(signature, []).append((index, block))

    owners = {}
    by_signature = {}
    for item in managed:
        by_signature.setdefault(item["signature"], []).append(item)
    for signature, items in by_signature.items():
        if len(items) == 1:
            owners[signature] = items[0]
            continue
        ids = [item["id"] for item in items]
        records = [item["record"] for item in items] + [
            _describe(block, "base", index) for index, block in base_groups.get(signature, [])]
        resolution = ambiguity(f"managed-group:{_canonical(list(signature))}", "competing_ids",
                               "Несколько управляемых записей описывают одну бронь; выберите сохраняемый ID",
                               records, [{"keep_id": value} for value in ids] + ["skip"], ids=ids)
        owners[signature] = None
        if isinstance(resolution, dict):
            keep = next(item for item in items if item["id"] == resolution["keep_id"])
            owners[signature] = keep
            for item in items:
                if item is not keep:
                    item["removed"] = True
                    ops["remove_managed"].append({"index": item["index"], "id": item["id"],
                                                  "kept_id": keep["id"], "record": item["record"]})

    for item in managed:
        if item["converted"] is not None and owners.get(item["signature"]) is item:
            ops["convert"].append({"index": item["index"], "id": item["id"], "from_lesson_type": item["lesson_type"],
                                   "rental_dates": item["converted"]["rental_dates"],
                                   "record": _describe(item["converted"], "individual", item["index"])})

    for signature, copies in base_groups.items():
        indexes = [index for index, _block in copies]
        records = [_describe(block, "base", index) for index, block in copies]
        kept_id = None
        if signature in owners:
            if owners[signature] is None:
                continue  # covered by the competing_ids ambiguity
            kept_id = owners[signature]["id"]
        else:
            signature_key = _canonical(list(signature))
            resolution = "migrate"
            if signature[:-1] in loose:
                resolution = ambiguity(f"base-group:{signature_key}", "dates_differ",
                                       "Копии в базе совпадают с управляемой арендой во всём, кроме режима/дат",
                                       records, ["migrate", "drop_copies", "skip"])
            if resolution not in ("migrate", "drop_copies"):
                continue
            if resolution == "migrate":
                kept_id = pinned.get(signature_key) or new_id()
                record = _created(copies[0][1], signature[-1], kept_id)
                ops["create"].append({"id": kept_id, "signature_key": signature_key, "from_base_indexes": indexes,
                                      "record": record})
        for index, record in zip(indexes, records):
            ops["remove_base"].append({"index": index, "kept_id": kept_id, "record": record})
    ops["remove_base"].sort(key=lambda op: op["index"])

    converted = {op["index"]: next(i["converted"] for i in managed if i["index"] == op["index"])
                 for op in ops["convert"]}
    removed_managed = {op["index"] for op in ops["remove_managed"]}
    new_individual = [converted.get(index, block) for index, block in enumerate(individual_blocks)
                      if index not in removed_managed] + [op["record"] for op in ops["create"]]
    removed_base = {op["index"] for op in ops["remove_base"]}
    new_base = [block for index, block in enumerate(base_blocks) if index not in removed_base]
    proposed = {"base_blocks": new_base, "individual_blocks": new_individual,
                "base_changed": bool(removed_base),
                "individual_changed": bool(converted or removed_managed or ops["create"])}

    plan = {
        "format": PLAN_FORMAT, "format_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(), "calculation_date": calculation_date.isoformat(),
        "inputs": inputs, "changes": proposed["base_changed"] or proposed["individual_changed"],
        "counts": {"before": _counts(base_blocks, individual_blocks), "after": _counts(new_base, new_individual)},
        "kept_ids": sorted({op["kept_id"] for op in ops["remove_base"] + ops["remove_managed"] if op["kept_id"]}
                           | {op["id"] for op in ops["convert"]}),
        "operations": ops, "ambiguities": ambiguities,
        "unresolved": [item["key"] for item in ambiguities if item["resolution"] is None],
        "validation": {"problems": _problems(base_blocks, individual_blocks, new_base, new_individual,
                                             ops, ambiguities)},
        "room_conflicts": room_conflicts(new_base, new_individual, calculation_date),
    }
    return plan, proposed


def _counts(base_blocks, individual_blocks):
    dicts = [block for block in individual_blocks if isinstance(block, dict)]
    return {
        "base_blocks": len(base_blocks),
        "base_rental_records": sum(isinstance(b, dict) and _is_rental_record(b) for b in base_blocks),
        "individual_blocks": len(individual_blocks),
        "managed_rental": sum(_text(b, "lesson_type") == "rental" for b in dicts),
        "managed_legacy_vermietung": sum(_is_rental_record(b) and _text(b, "lesson_type") != "rental" for b in dicts),
    }


def _problems(old_base, old_individual, new_base, new_individual, ops, ambiguities):
    """Standard backup/restore validation plus the invariants of the touched records."""
    problems = []
    for validate, payload in ((validate_base_state, {"blocks": new_base}),
                              (validate_individual_state, {"blocks": new_individual})):
        try:
            validate(payload)
        except BackupValidationError as exc:
            problems.append(f"Штатная валидация: {exc}")
    held = {(r["layer"], r["index"]) for item in ambiguities for r in item["records"]}
    for index, block in enumerate(old_base):
        if isinstance(block, dict) and _is_rental_record(block) and ("base", index) not in held \
                and index not in {op["index"] for op in ops["remove_base"]}:
            problems.append(f"Аренда base[{index}] осталась без решения")
    if any(isinstance(b, dict) and _text(b, "lesson_type") == "rental" for b in new_base):
        problems.append("rental в базовом слое")
    remaining = [b for b in new_individual if isinstance(b, dict) and _is_rental_record(b)
                 and _text(b, "lesson_type") != "rental"]
    held_ids = {r.get("id") for item in ambiguities for r in item["records"] if r["layer"] == "individual"}
    problems += [f"Legacy-аренда {b.get('id')} не преобразована и не указана в неоднозначностях"
                 for b in remaining if b.get("id") not in held_ids]
    removed = {op["id"] for op in ops["remove_managed"]}
    expected_ids = [b.get("id") for b in old_individual if isinstance(b, dict) and b.get("id") not in removed]
    expected_ids += [op["id"] for op in ops["create"]]
    actual_ids = [b.get("id") for b in new_individual if isinstance(b, dict)]
    if sorted(map(str, actual_ids)) != sorted(map(str, expected_ids)) or len(set(actual_ids)) != len(actual_ids):
        problems.append("Набор управляемых ID изменился или содержит повторы")
    for old, new, label in ((old_base, new_base, "базе"), (old_individual, new_individual, "управляемом слое")):
        if [b for b in old if not (isinstance(b, dict) and _is_rental_record(b))] != \
                [b for b in new if not (isinstance(b, dict) and _is_rental_record(b))]:
            problems.append(f"Изменены записи, не являющиеся арендой, в {label}")
    return problems


def room_conflicts(base_blocks, individual_blocks, calculation_date):
    """Real room overlaps of pairs with a rental, by the phase-2 rules (rental_conflicts)."""
    from reader import ScheduleClass
    from rental_conflicts import fixed_conflict_type, is_rental

    events = []
    for layer, blocks in (("base", base_blocks), ("individual", individual_blocks)):
        for index, block in enumerate(blocks):
            try:
                start, end = _minutes(block.get("start_time")), _minutes(block.get("end_time"))
            except (AttributeError, ValueError):
                continue
            event = ScheduleClass(
                block.get("subject"), block.get("students"), block.get("teacher"), block.get("room"), [],
                block.get("building"), end - start, block.get("day"), block.get("start_time"), None,
                lesson_type=_text(block, "lesson_type"), trial_dates=block.get("trial_dates"),
                rental_dates=block.get("rental_dates"), block_id=block.get("id") or "")
            events.append((_describe(block, layer, index), event))
    conflicts = []
    for position, (first_record, first) in enumerate(events):
        for second_record, second in events[position + 1:]:
            if (is_rental(first) or is_rental(second)) and fixed_conflict_type(first, second, calculation_date):
                conflicts.append({"first": first_record, "second": second_record})
    return conflicts


def read_inputs(state_dir):
    raw, states = {}, {}
    for name in FILES:
        path = os.path.join(state_dir, name)
        try:
            with open(path, "rb") as source:
                raw[name] = source.read()
            states[name] = json.loads(raw[name].decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise RepairError(f"Не удалось прочитать {path}: {exc}") from exc
        if not isinstance(states[name], dict) or not isinstance(states[name].get("blocks"), list):
            raise RepairError(f"Некорректная структура {path}")
    inputs = {name: {"sha256": _sha256(raw[name]), "size": len(raw[name]),
                     "revision": states[name].get("published_at" if name == FILES[0] else "last_modified")}
              for name in FILES}
    return raw, states, inputs


def dry_run(state_dir, previous=None, calculation_date=None):
    _raw, states, inputs = read_inputs(state_dir)
    plan, _proposed = build_plan(states[FILES[0]], states[FILES[1]], inputs=inputs, previous=previous,
                                 calculation_date=calculation_date)
    plan["state_dir"] = os.path.abspath(state_dir)
    return plan


def _check_no_operator(state_dir):
    path = os.path.join(state_dir, "lock.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as source:
            holder = json.load(source).get("holder")
    except (OSError, ValueError, AttributeError) as exc:
        raise RepairError(f"Не удалось проверить блокировку редактирования: {exc}") from exc
    if holder:
        raise RepairError(f"Редактирование заблокировано пользователем {holder!r}. Дождитесь завершения "
                          "работы (или освободите блокировку в редакторе) и повторите.")


def _state_bytes(state, blocks, revision_field, revision, published_by=None):
    payload = dict(state)
    payload["blocks"] = blocks
    payload[revision_field] = revision
    if published_by is not None:
        payload["published_by"] = published_by
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _write(path, data):
    snapshot_guard._replace_file(path, data)


def _replace(operations):
    try:
        snapshot_guard.replace_files_with_rollback(operations)
    except snapshot_guard.SnapshotConflictError as exc:
        raise RepairError(f"Запись прервана: {exc}") from exc


def apply_plan(state_dir, plan, expected, backup_dir, published_by="rental_repair"):
    if plan.get("format") != PLAN_FORMAT:
        raise RepairError("Файл не является планом исправления аренды")
    for name in FILES:
        if expected.get(name) != plan["inputs"][name]["sha256"]:
            raise RepairError(f"Ожидаемый хеш {name} не совпадает с планом")
    if plan.get("unresolved") or plan["validation"]["problems"]:
        raise RepairError("План содержит нерешённые неоднозначности или ошибки проверки; примените только "
                          "проверенный dry-run без них.")
    state_dir = os.path.abspath(state_dir)
    with snapshot_guard.locked_editor_state(state_dir):
        snapshot_guard._check_no_restore(state_dir)
        _check_no_operator(state_dir)
        raw, states, inputs = read_inputs(state_dir)
        if any(inputs[name]["sha256"] != expected[name] for name in FILES):
            raise RepairError("Данные изменились после dry-run: план не применён. Выполните новый dry-run.")

        def no_new_id():
            raise RepairError("План не закрепляет ID новой записи")

        current, proposed = build_plan(states[FILES[0]], states[FILES[1]], inputs=inputs, previous=plan,
                                       calculation_date=date.fromisoformat(plan["calculation_date"]),
                                       new_id=no_new_id)
        same = [_canonical(current[key]) == _canonical(plan[key]) for key in ("operations", "ambiguities")]
        if not all(same) or current["unresolved"] or current["validation"]["problems"]:
            raise RepairError("Пересчёт не совпадает с планом: план изменён вручную или устарел.")
        if not current["changes"]:
            return {"changed": False, "revisions": {name: inputs[name]["revision"] for name in FILES}}

        revision = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        new_bytes = {
            FILES[0]: _state_bytes(states[FILES[0]], proposed["base_blocks"], "published_at", revision, published_by)
            if proposed["base_changed"] else raw[FILES[0]],
            FILES[1]: _state_bytes(states[FILES[1]], proposed["individual_blocks"], "last_modified", revision)
            if proposed["individual_changed"] else raw[FILES[1]],
        }
        manifest = _save_originals(backup_dir, state_dir, raw, new_bytes, plan)
        changed = [name for name in FILES if new_bytes[name] != raw[name]]
        try:
            _replace([(os.path.join(state_dir, name), new_bytes[name]) for name in changed])
        except RepairError:
            _set_status(backup_dir, manifest, "rolled_back")
            raise
        try:
            _verify_applied(state_dir, new_bytes)
        except Exception as exc:
            _replace([(os.path.join(state_dir, name), raw[name]) for name in changed])
            _set_status(backup_dir, manifest, "rolled_back")
            raise RepairError(f"Проверка после записи не прошла ({exc}); исходные файлы возвращены.") from exc
        _set_status(backup_dir, manifest, "applied")
    return {"changed": True, "files": changed, "revision": revision, "backup_dir": os.path.abspath(backup_dir)}


def _save_originals(backup_dir, state_dir, raw, new_bytes, plan):
    """Original bytes come first: the standard backup rejects the legacy layer it must preserve."""
    if os.path.exists(backup_dir) and os.listdir(backup_dir):
        raise RepairError(f"Каталог резервной копии не пуст: {backup_dir}")
    os.makedirs(os.path.join(backup_dir, "original"), exist_ok=True)
    for name in FILES:
        _write(os.path.join(backup_dir, "original", name), raw[name])
    _write(os.path.join(backup_dir, "plan.json"), json.dumps(plan, ensure_ascii=False, indent=2).encode("utf-8"))
    for name in FILES:
        with open(os.path.join(backup_dir, "original", name), "rb") as source:
            if _sha256(source.read()) != _sha256(raw[name]):
                raise RepairError(f"Резервная копия {name} не совпадает с исходником; запись не начата.")
    manifest = {
        "format": BACKUP_FORMAT, "format_version": 1, "state_dir": os.path.abspath(state_dir),
        "created_at": datetime.now(timezone.utc).isoformat(), "status": "prepared",
        "files": {name: {"original_sha256": _sha256(raw[name]), "original_size": len(raw[name]),
                         "modified": new_bytes[name] != raw[name], "applied_sha256": _sha256(new_bytes[name])}
                  for name in FILES},
    }
    _set_status(backup_dir, manifest, "prepared")
    return manifest


def _set_status(backup_dir, manifest, status):
    manifest["status"] = status
    _write(os.path.join(backup_dir, "manifest.json"),
           json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))


def _verify_applied(state_dir, new_bytes):
    states = {}
    for name in FILES:
        with open(os.path.join(state_dir, name), "rb") as source:
            data = source.read()
        if data != new_bytes[name]:
            raise RepairError(f"{name} не совпадает с подготовленными данными")
        states[name] = json.loads(data.decode("utf-8"))
    validate_base_state(states[FILES[0]])
    validate_individual_state(states[FILES[1]])


def restore(state_dir, backup_dir):
    with open(os.path.join(backup_dir, "manifest.json"), "r", encoding="utf-8") as source:
        manifest = json.load(source)
    if manifest.get("format") != BACKUP_FORMAT:
        raise RepairError("Каталог не является резервной копией исправления аренды")
    state_dir = os.path.abspath(state_dir)
    if os.path.normcase(state_dir) != os.path.normcase(manifest["state_dir"]):
        raise RepairError(f"Копия создана для {manifest['state_dir']}, а не для {state_dir}")
    originals = {}
    for name, info in manifest["files"].items():
        with open(os.path.join(backup_dir, "original", name), "rb") as source:
            originals[name] = source.read()
        if _sha256(originals[name]) != info["original_sha256"]:
            raise RepairError(f"Резервная копия {name} повреждена")
    with snapshot_guard.locked_editor_state(state_dir):
        snapshot_guard._check_no_restore(state_dir)
        _check_no_operator(state_dir)
        operations = []
        for name, info in manifest["files"].items():
            path = os.path.join(state_dir, name)
            with open(path, "rb") as source:
                current = _sha256(source.read())
            if current == info["original_sha256"]:
                continue
            if current != info["applied_sha256"]:
                raise RepairError(f"{name} изменён после применения: возврат поверх новых данных запрещён. "
                                  "Сначала сохраните и сверьте новые изменения.")
            operations.append((path, originals[name]))
        if operations:
            _replace(operations)
        for path, data in operations:
            with open(path, "rb") as source:
                if source.read() != data:
                    raise RepairError(f"После возврата {path} не совпадает с резервной копией")
        _set_status(backup_dir, manifest, "restored")
    return [os.path.basename(path) for path, _data in operations]


def _print_plan(plan, plan_path):
    print(f"Каталог состояния: {plan.get('state_dir')}")
    for name, info in plan["inputs"].items():
        print(f"  {name}: sha256={info['sha256']} revision={info['revision']}")
    print(f"Дата расчёта: {plan['calculation_date']}")
    print(f"До: {plan['counts']['before']}")
    print(f"После: {plan['counts']['after']}")
    ops = plan["operations"]
    print(f"Преобразовать в rental: {len(ops['convert'])}; удалить копий из базы: {len(ops['remove_base'])}; "
          f"создать из базы: {len(ops['create'])}; удалить управляемых дублей: {len(ops['remove_managed'])}")
    for op in ops["convert"]:
        r = op["record"]
        copies = sum(1 for item in ops["remove_base"] if item["kept_id"] == op["id"])
        print(f"  {op['id']} {op['from_lesson_type']}->rental {r.get('building')} {r.get('room')} {r.get('day')} "
              f"{r.get('start_time')}-{r.get('end_time')} {r.get('teacher')!r}/{r.get('students')!r} "
              f"dates={op['rental_dates'] or 'weekly'}; копий в базе: {copies}")
    for op in ops["create"]:
        print(f"  новый {op['id']} из base{op['from_base_indexes']}")
    for item in plan["ambiguities"]:
        print(f"НЕОДНОЗНАЧНОСТЬ {item['key']} [{item['kind']}]: {item['message']}; "
              f"решение={item['resolution']!r} {item.get('resolution_error', '')}")
        for record in item["records"]:
            print(f"    {record}")
    for conflict in plan["room_conflicts"]:
        print(f"КОНФЛИКТ ПОМЕЩЕНИЯ: {conflict['first']} <-> {conflict['second']}")
    for problem in plan["validation"]["problems"]:
        print(f"ОШИБКА ПРОВЕРКИ: {problem}")
    print(f"План: {plan_path}; изменения: {plan['changes']}; нерешено: {len(plan['unresolved'])}")
    if plan["changes"] and not plan["unresolved"] and not plan["validation"]["problems"]:
        base, ind = (plan["inputs"][name]["sha256"] for name in FILES)
        print(f"apply: --plan {plan_path} --expect-base {base} --expect-individual {ind} --backup-dir <новый каталог>")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Проверяемое исправление legacy-аренды (по умолчанию dry-run)")
    sub = parser.add_subparsers(dest="command")
    dry = sub.add_parser("dry-run")
    dry.add_argument("--state-dir", required=True)
    dry.add_argument("--out", required=True)
    dry.add_argument("--from-plan", help="перенести решения неоднозначностей и закреплённые ID")
    app = sub.add_parser("apply")
    app.add_argument("--state-dir", required=True)
    app.add_argument("--plan", required=True)
    app.add_argument("--expect-base", required=True)
    app.add_argument("--expect-individual", required=True)
    app.add_argument("--backup-dir", required=True)
    rst = sub.add_parser("restore")
    rst.add_argument("--state-dir", required=True)
    rst.add_argument("--backup-dir", required=True)
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0].startswith("--"):
        args_list.insert(0, "dry-run")
    args = parser.parse_args(args_list)
    try:
        if args.command == "apply":
            with open(args.plan, "r", encoding="utf-8") as source:
                plan = json.load(source)
            result = apply_plan(args.state_dir, plan, {FILES[0]: args.expect_base, FILES[1]: args.expect_individual},
                                args.backup_dir)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "restore":
            print(f"Возвращены исходные файлы: {restore(args.state_dir, args.backup_dir) or 'нет изменений'}")
        elif args.command == "dry-run":
            previous = None
            if args.from_plan:
                with open(args.from_plan, "r", encoding="utf-8") as source:
                    previous = json.load(source)
            plan = dry_run(args.state_dir, previous)
            with open(args.out, "w", encoding="utf-8") as target:
                json.dump(plan, target, ensure_ascii=False, indent=2)
            _print_plan(plan, args.out)
        else:
            parser.print_help()
            return 2
    except (RepairError, snapshot_guard.SnapshotConflictError, BackupValidationError) as exc:
        print(f"ОТКАЗ: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
