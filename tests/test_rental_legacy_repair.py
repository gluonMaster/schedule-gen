"""Phase 5: dry-run/apply/restore of legacy Vermietung records on temporary state copies."""
import json
import os
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gear_xls import snapshot_guard
from gear_xls.backup_manager import BackupValidationError, validate_base_state, validate_individual_state
from gear_xls.scripts import rental_repair as repair

BASE, IND = repair.FILES
BASE_REVISION, IND_REVISION = "2026-09-29T13:28:31.980161", "2026-09-24T08:48:38.779836"
TODAY = date(2026, 10, 1)
LESSON = dict(subject="Math", students="1A", teacher="ol2", room="1.10", room_display="1.10", building="Villa",
              day="Mo", start_time="16:00", end_time="17:00", duration=60, color="#fff", lesson_type="group")


def legacy(block_id, room="0.06", day="Sa", start="14:30", end="17:30", lesson_type="group", **extra):
    return dict(building="Villa", day=day, room=room, subject="Vermietung", teacher="ol6",
                students="Serbische Schule", lesson_type=lesson_type, start_time=start, end_time=end,
                start_row=66, row_span=36, color="rgb(255, 251, 211)", col_index=3, id=block_id, **extra)


def base_copy(block):
    copy = {key: block[key] for key in ("subject", "students", "teacher", "room", "building", "day",
                                         "start_time", "end_time", "color")}
    start, end = (int(block[key][:2]) * 60 + int(block[key][3:]) for key in ("start_time", "end_time"))
    copy.update(room_display=block["room"], duration=end - start, lesson_type="group")
    return copy


def write_state(path, base, individual, holder=None):
    path.mkdir(parents=True)
    for name, payload in ((BASE, {"published_at": BASE_REVISION, "published_by": "admin_one", "blocks": base}),
                          (IND, {"last_modified": IND_REVISION, "blocks": individual}),
                          ("lock.json", {"holder": holder, "version": 3})):
        (path / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def raw(state):
    return {name: (state / name).read_bytes() for name in repair.FILES}


def blocks(state, name):
    return json.loads((state / name).read_text(encoding="utf-8"))["blocks"]


def dry_run(state, previous=None):
    return json.loads(json.dumps(repair.dry_run(str(state), previous, TODAY)))  # as saved in the plan file


def apply(state, plan, backup):
    expected = {name: plan["inputs"][name]["sha256"] for name in repair.FILES}
    return repair.apply_plan(str(state), plan, expected, str(backup))


def test_three_base_copies_and_legacy_group_become_one_rental_with_original_id(tmp_path):
    rental = legacy("rent-1")
    state = write_state(tmp_path / "state", [base_copy(rental), LESSON, base_copy(rental), base_copy(rental)], [rental])
    before = raw(state)

    plan = dry_run(state)

    assert raw(state) == before
    assert [(op["id"], op["from_lesson_type"]) for op in plan["operations"]["convert"]] == [("rent-1", "group")]
    assert [(op["index"], op["kept_id"]) for op in plan["operations"]["remove_base"]] == [
        (0, "rent-1"), (2, "rent-1"), (3, "rent-1")]
    assert plan["counts"]["before"]["base_rental_records"] == 3 and plan["counts"]["after"]["base_rental_records"] == 0
    assert plan["kept_ids"] == ["rent-1"] and not plan["ambiguities"] and not plan["validation"]["problems"]
    assert plan["inputs"][IND]["revision"] == IND_REVISION

    result = apply(state, plan, tmp_path / "backup")

    assert result["changed"] and result["files"] == [BASE, IND]
    assert blocks(state, IND) == [{**rental, "lesson_type": "rental", "rental_dates": []}]
    assert blocks(state, BASE) == [LESSON]
    base, individual = (json.loads((state / name).read_text(encoding="utf-8")) for name in (BASE, IND))
    assert base["published_at"] != BASE_REVISION and individual["last_modified"] != IND_REVISION
    validate_base_state(base)
    validate_individual_state(individual)


def test_separate_rooms_and_dates_stay_separate_and_ambiguities_need_a_decision(tmp_path):
    room_a, room_b = legacy("a", room="0.06"), legacy("b", room="0.08")  # same renter, same time
    first = legacy("d1", room="1.06", day="Mo", start="10:00", end="11:00", lesson_type="trial",
                   trial_dates=["2026-10-05"])
    second = legacy("d2", room="1.06", day="Mo", start="10:00", end="11:00", lesson_type="trial",
                    trial_dates=["2026-10-12"])
    twin_1, twin_2 = (legacy(name, room="2.09", day="Di", start="18:00", end="19:00") for name in ("twin-1", "twin-2"))
    unclear = legacy("unclear", room="2.10", day="Mi", start="18:00", end="19:00", lesson_type="trial",
                     trial_dates=["2026-10-07"], rental_dates=["2026-10-14"])
    state = write_state(tmp_path / "state", [base_copy(room_a), base_copy(twin_1)],
                        [room_a, room_b, first, second, twin_1, twin_2, unclear])
    before = raw(state)

    plan = dry_run(state)

    assert {op["id"]: op["rental_dates"] for op in plan["operations"]["convert"]} == {
        "a": [], "b": [], "d1": ["2026-10-05"], "d2": ["2026-10-12"]}
    assert [op["kept_id"] for op in plan["operations"]["remove_base"]] == ["a"]
    assert sorted(item["kind"] for item in plan["ambiguities"]) == ["competing_ids", "dates"]
    competing = next(item for item in plan["ambiguities"] if item["kind"] == "competing_ids")
    assert [(r["layer"], r.get("id")) for r in competing["records"]] == [
        ("individual", "twin-1"), ("individual", "twin-2"), ("base", None)]
    assert len(plan["unresolved"]) == 2
    with pytest.raises(repair.RepairError, match="нерешённые"):
        apply(state, plan, tmp_path / "refused")
    assert raw(state) == before

    for item in plan["ambiguities"]:
        item["resolution"] = ({"keep_id": "twin-1"} if item["kind"] == "competing_ids"
                              else {"rental_dates": ["2026-10-14"]})
    resolved = dry_run(state, plan)

    assert not resolved["unresolved"] and not resolved["validation"]["problems"]
    assert [op["id"] for op in resolved["operations"]["remove_managed"]] == ["twin-2"]
    assert sorted({op["kept_id"] for op in resolved["operations"]["remove_base"]}) == ["a", "twin-1"]
    assert resolved["room_conflicts"] == []
    apply(state, resolved, tmp_path / "backup")
    result = {block["id"]: block for block in blocks(state, IND)}
    assert list(result) == ["a", "b", "d1", "d2", "twin-1", "unclear"]
    assert all(block["lesson_type"] == "rental" and "trial_dates" not in block for block in result.values())
    assert result["unclear"]["rental_dates"] == ["2026-10-14"] and result["d2"]["rental_dates"] == ["2026-10-12"]
    assert blocks(state, BASE) == []


def test_base_only_rental_moves_once_with_plan_id_and_lessons_stay_untouched(tmp_path):
    chor = base_copy(legacy("ignored", room="0.01", day="Mo", start="19:00", end="21:00"))
    chor.update(teacher="ol2", students="Chor")
    overlapping = dict(LESSON, room="0.01", room_display="0.01", start_time="20:00", end_time="21:00",
                       duration=60, notes="keep")  # same name as the renter, same room: a real conflict
    individual_lesson = dict(id="ind-1", building="Villa", day="Di", room="1.10", subject="Ind. Russisch",
                             teacher="ol2", students="Schott", lesson_type="individual", start_time="14:00",
                             end_time="15:00", notes="x", created_by="organizer_one")
    state = write_state(tmp_path / "state", [chor, LESSON, dict(chor), dict(LESSON), overlapping],
                        [individual_lesson])

    plan = dry_run(state)
    create = plan["operations"]["create"]
    assert len(create) == 1 and create[0]["from_base_indexes"] == [0, 2]
    new_id = create[0]["id"]
    assert dry_run(state, plan)["operations"]["create"][0]["id"] == new_id
    assert [(c["first"]["layer"], c["first"]["index"], c["second"].get("id"))
            for c in plan["room_conflicts"]] == [("base", 2, new_id)]

    apply(state, plan, tmp_path / "backup")

    assert blocks(state, BASE) == [LESSON, LESSON, overlapping]
    created = {key: chor[key] for key in ("subject", "students", "teacher", "room", "building", "day",
                                          "start_time", "end_time", "color")}
    assert blocks(state, IND) == [individual_lesson, {"id": new_id, **created, "lesson_type": "rental",
                                                      "rental_dates": []}]

    after = dry_run(state)
    assert not after["changes"] and not any(after["operations"].values()) and not after["ambiguities"]
    assert len(after["room_conflicts"]) == 1  # reported, never "fixed" by deleting a booking
    before = raw(state)
    assert apply(state, after, tmp_path / "noop")["changed"] is False
    assert raw(state) == before and not (tmp_path / "noop").exists()
    with pytest.raises(repair.RepairError, match="изменились"):
        apply(state, plan, tmp_path / "stale")
    assert raw(state) == before


def test_stale_source_operator_lock_failed_write_and_restore_of_legacy_bytes(tmp_path, monkeypatch):
    rental = legacy("rent-1")
    state = write_state(tmp_path / "state", [base_copy(rental), LESSON, base_copy(rental)], [rental])
    original = raw(state)
    with pytest.raises(BackupValidationError):
        validate_individual_state(json.loads(original[IND]))  # the standard backup cannot save this layer
    plan = dry_run(state)

    (state / "lock.json").write_text(json.dumps({"holder": "organizer_one", "version": 4}), encoding="utf-8")
    with pytest.raises(repair.RepairError, match="organizer_one"):
        apply(state, plan, tmp_path / "locked")
    (state / "lock.json").write_text(json.dumps({"holder": None, "version": 5}), encoding="utf-8")

    changed = json.loads(original[IND])
    changed["blocks"][0]["students"] = "Serbische Schule e.V."
    (state / IND).write_text(json.dumps(changed, ensure_ascii=False, indent=2), encoding="utf-8")
    with pytest.raises(repair.RepairError, match="изменились"):
        apply(state, plan, tmp_path / "stale")
    (state / IND).write_bytes(original[IND])
    assert raw(state) == original

    real_replace = snapshot_guard._replace_file

    def fail_individual_state_write(path, data):
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(str(state / IND)):
            raise OSError("disk full")
        real_replace(path, data)

    monkeypatch.setattr(snapshot_guard, "_replace_file", fail_individual_state_write)
    with pytest.raises(repair.RepairError, match="прервана"):
        apply(state, plan, tmp_path / "failed")
    assert raw(state) == original
    assert json.loads((tmp_path / "failed" / "manifest.json").read_text(encoding="utf-8"))["status"] == "rolled_back"
    monkeypatch.setattr(snapshot_guard, "_replace_file", real_replace)

    backup = tmp_path / "backup"
    apply(state, plan, backup)
    applied = raw(state)
    assert {name: (backup / "original" / name).read_bytes() for name in repair.FILES} == original

    (state / IND).write_bytes(applied[IND].replace(b"Serbische Schule", b"Serbische Schule 2"))
    with pytest.raises(repair.RepairError, match="изменён после применения"):
        repair.restore(str(state), str(backup))
    (state / IND).write_bytes(applied[IND])

    assert repair.restore(str(state), str(backup)) == [BASE, IND]
    assert raw(state) == original
    assert json.loads(original[IND])["blocks"][0]["lesson_type"] == "group"
    assert json.loads((backup / "manifest.json").read_text(encoding="utf-8"))["status"] == "restored"
