import importlib
import json
from datetime import date
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gear_xls import rooms_report
from gear_xls import state_manager


def _trial_block(block_id="trial-1", day="So", trial_dates=None):
    return {
        "id": block_id,
        "building": "Villa",
        "day": day,
        "room": "1.01",
        "subject": "Trial",
        "teacher": "Teacher",
        "students": "Student",
        "start_time": "10:00",
        "end_time": "11:00",
        "lesson_type": "trial",
        "trial_dates": trial_dates if trial_dates is not None else ["2026-05-24"],
    }


def _regular_block(block_id="lesson-1", day="Mo"):
    return {
        "id": block_id,
        "building": "Villa",
        "day": day,
        "room": "1.01",
        "subject": "Deutsch",
        "teacher": "Teacher",
        "students": "Student",
        "start_time": "10:00",
        "end_time": "11:00",
        "lesson_type": "individual",
    }


def _state(*blocks):
    return {"last_modified": "2026-05-01T00:00:00", "blocks": list(blocks)}


def _write_individual_file(path, blocks, last_modified="2026-05-01T00:00:00"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"last_modified": last_modified, "blocks": blocks}, ensure_ascii=False),
        encoding="utf-8",
    )


def _read_individual_file(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _prune(state, today):
    return state_manager._prune_expired_trial_blocks(state, today=date.fromisoformat(today))


@pytest.fixture()
def isolated_individual_files(tmp_path, monkeypatch):
    path = tmp_path / "individual_lessons.json"
    monkeypatch.setattr(state_manager, "INDIVIDUAL_LESSONS_PATH", str(path))
    monkeypatch.setattr(state_manager, "INDIVIDUAL_LOCK_PATH", str(path) + ".lock")
    monkeypatch.setattr(state_manager, "SCHEDULE_HTML_PATH", str(tmp_path / "missing_schedule.html"))
    monkeypatch.setattr(
        state_manager,
        "get_base_schedule",
        lambda: {"published_at": "2026-05-01T10:00:00", "blocks": []},
    )
    return path


def _set_today(monkeypatch, value):
    monkeypatch.setattr(state_manager, "_today_local_date", lambda: date.fromisoformat(value))


def test_expired_sunday_trial_is_pruned():
    regular = _regular_block()
    state = _state(_trial_block(trial_dates=["2026-05-24"]), regular)

    result = _prune(state, "2026-05-25")

    assert result == {"removed": 1, "removed_ids": ["trial-1"]}
    assert state["blocks"] == [regular]


def test_trial_with_today_date_is_not_pruned():
    trial = _trial_block(trial_dates=["2026-05-24"])
    state = _state(trial)

    result = _prune(state, "2026-05-24")

    assert result == {"removed": 0, "removed_ids": []}
    assert state["blocks"] == [trial]


def test_trial_with_future_max_date_is_not_pruned():
    trial = _trial_block(day="Fr", trial_dates=["2026-05-15", "2026-05-29"])
    state = _state(trial)

    result = _prune(state, "2026-05-22")

    assert result == {"removed": 0, "removed_ids": []}
    assert state["blocks"] == [trial]


def test_trial_expiration_uses_max_date_not_order():
    trial = _trial_block(day="Fr", trial_dates=["2026-05-29", "2026-05-15"])
    state = _state(trial)

    result = _prune(state, "2026-05-22")

    assert result == {"removed": 0, "removed_ids": []}
    assert state["blocks"] == [trial]


def test_invalid_trial_date_is_not_pruned():
    trial = _trial_block(trial_dates=["not-a-date"])
    state = _state(trial)

    result = _prune(state, "2026-05-25")

    assert result == {"removed": 0, "removed_ids": []}
    assert state["blocks"] == [trial]


def test_non_existing_calendar_date_is_not_pruned():
    trial = _trial_block(day="Mo", trial_dates=["2026-02-30"])
    state = _state(trial)

    result = _prune(state, "2026-05-25")

    assert result == {"removed": 0, "removed_ids": []}
    assert state["blocks"] == [trial]


def test_wrong_weekday_trial_date_is_not_pruned():
    trial = _trial_block(day="So", trial_dates=["2026-05-21"])
    state = _state(trial)

    result = _prune(state, "2026-05-22")

    assert result == {"removed": 0, "removed_ids": []}
    assert state["blocks"] == [trial]


def test_missing_or_empty_trial_dates_are_not_pruned():
    missing_dates = _trial_block(block_id="trial-missing")
    missing_dates.pop("trial_dates")
    empty_dates = _trial_block(block_id="trial-empty", trial_dates=[])
    state = _state(missing_dates, empty_dates)

    result = _prune(state, "2026-05-25")

    assert result == {"removed": 0, "removed_ids": []}
    assert state["blocks"] == [missing_dates, empty_dates]


def test_non_dict_entries_are_preserved():
    trial = _trial_block()
    state = _state("not-a-block", trial)

    result = _prune(state, "2026-05-25")

    assert result == {"removed": 1, "removed_ids": ["trial-1"]}
    assert state["blocks"] == ["not-a-block"]


def test_order_of_remaining_blocks_is_preserved():
    first = _regular_block(block_id="lesson-1", day="Mo")
    expired = _trial_block(block_id="trial-expired", trial_dates=["2026-05-24"])
    second = _regular_block(block_id="lesson-2", day="Di")
    future = _trial_block(block_id="trial-future", day="Fr", trial_dates=["2026-05-29"])
    third = _regular_block(block_id="lesson-3", day="Mi")
    state = _state(first, expired, second, future, third)

    result = _prune(state, "2026-05-25")

    assert result == {"removed": 1, "removed_ids": ["trial-expired"]}
    assert state["blocks"] == [first, second, future, third]


def test_get_individual_lessons_prunes_and_writes(isolated_individual_files, monkeypatch):
    _set_today(monkeypatch, "2026-05-25")
    regular = _regular_block()
    _write_individual_file(
        isolated_individual_files,
        [_trial_block(trial_dates=["2026-05-24"]), regular],
    )

    state = state_manager.get_individual_lessons()
    persisted = _read_individual_file(isolated_individual_files)

    assert state["blocks"] == [regular]
    assert persisted["blocks"] == [regular]
    assert persisted["last_modified"] != "2026-05-01T00:00:00"


def test_no_write_when_nothing_pruned(isolated_individual_files, monkeypatch):
    _set_today(monkeypatch, "2026-05-24")
    trial = _trial_block(trial_dates=["2026-05-24"])
    _write_individual_file(isolated_individual_files, [trial])
    before = isolated_individual_files.read_text(encoding="utf-8")

    state = state_manager.get_individual_lessons()

    assert state["blocks"] == [trial]
    assert isolated_individual_files.read_text(encoding="utf-8") == before


def test_empty_missing_state_does_not_create_file(isolated_individual_files, monkeypatch):
    _set_today(monkeypatch, "2026-05-25")

    state = state_manager.get_individual_lessons()

    assert state == {"last_modified": None, "blocks": []}
    assert not isolated_individual_files.exists()


def test_last_modified_none_with_blocks_can_be_pruned(isolated_individual_files, monkeypatch):
    _set_today(monkeypatch, "2026-05-25")
    _write_individual_file(
        isolated_individual_files,
        [_trial_block(trial_dates=["2026-05-24"])],
        last_modified=None,
    )

    state = state_manager.get_individual_lessons()
    persisted = _read_individual_file(isolated_individual_files)

    assert state["blocks"] == []
    assert persisted["blocks"] == []
    assert persisted["last_modified"]


def test_get_individual_revision_triggers_pruning_in_normal_mode(isolated_individual_files, monkeypatch):
    _set_today(monkeypatch, "2026-05-25")
    _write_individual_file(
        isolated_individual_files,
        [_trial_block(trial_dates=["2026-05-24"])],
    )

    revision = state_manager.get_individual_revision()
    persisted = _read_individual_file(isolated_individual_files)

    assert revision
    assert revision != "2026-05-01T00:00:00"
    assert persisted["blocks"] == []


def test_get_individual_revision_raw_does_not_prune(isolated_individual_files, monkeypatch):
    _set_today(monkeypatch, "2026-05-25")
    trial = _trial_block(trial_dates=["2026-05-24"])
    _write_individual_file(isolated_individual_files, [trial])
    before = isolated_individual_files.read_text(encoding="utf-8")

    revision = state_manager.get_individual_revision(prune_expired=False)

    assert revision == "2026-05-01T00:00:00"
    assert isolated_individual_files.read_text(encoding="utf-8") == before


def test_add_rejects_already_expired_trial_payload(isolated_individual_files, monkeypatch):
    _set_today(monkeypatch, "2026-05-25")
    _write_individual_file(isolated_individual_files, [])
    before = isolated_individual_files.read_text(encoding="utf-8")

    created, error = state_manager.add_block(
        _trial_block(trial_dates=["2026-05-24"]),
        "admin",
    )

    assert created is None
    assert error == "trial_dates must include today or a future date"
    assert isolated_individual_files.read_text(encoding="utf-8") == before


def test_update_rejects_already_expired_trial_payload(isolated_individual_files, monkeypatch):
    _set_today(monkeypatch, "2026-05-25")
    trial = _trial_block(trial_dates=["2026-05-31"])
    _write_individual_file(isolated_individual_files, [trial])
    before = isolated_individual_files.read_text(encoding="utf-8")

    updated, error = state_manager.update_block(
        "trial-1",
        {"trial_dates": ["2026-05-24"]},
        "admin",
    )

    assert updated is None
    assert error == "trial_dates must include today or a future date"
    assert isolated_individual_files.read_text(encoding="utf-8") == before


def test_mutation_reports_cleanup_removed_when_existing_expired_blocks_are_pruned(
    isolated_individual_files,
    monkeypatch,
):
    _set_today(monkeypatch, "2026-05-25")
    regular = _regular_block()
    _write_individual_file(
        isolated_individual_files,
        [_trial_block(trial_dates=["2026-05-24"]), regular],
    )

    result = state_manager.add_block(_regular_block(block_id="new-regular", day="Di"), "admin")
    created, error = result
    persisted = _read_individual_file(isolated_individual_files)

    assert error is None
    assert created["id"]
    assert result.individual_cleanup_removed == 1
    assert result.force_individual_refresh is True
    assert result.individual_revision
    assert [block["id"] for block in persisted["blocks"]] == ["lesson-1", created["id"]]


def _login_admin(client):
    with client.session_transaction() as session:
        session["login"] = "admin"
        session["display_name"] = "Admin"
        session["role"] = "admin"


def _configure_server_route_state(monkeypatch, tmp_path, today="2026-05-25"):
    server_routes = importlib.import_module("gear_xls.server_routes")
    server_routes.app.config.update(TESTING=True)
    route_state_manager = server_routes.state_manager
    path = tmp_path / "route_individual_lessons.json"
    monkeypatch.setattr(route_state_manager, "INDIVIDUAL_LESSONS_PATH", str(path))
    monkeypatch.setattr(route_state_manager, "INDIVIDUAL_LOCK_PATH", str(path) + ".lock")
    monkeypatch.setattr(route_state_manager, "SCHEDULE_HTML_PATH", str(tmp_path / "missing_schedule.html"))
    monkeypatch.setattr(
        route_state_manager,
        "get_base_schedule",
        lambda: {"published_at": "2026-05-01T10:00:00", "blocks": []},
    )
    monkeypatch.setattr(route_state_manager, "get_base_revision", lambda: "base-revision")
    monkeypatch.setattr(route_state_manager, "_today_local_date", lambda: date.fromisoformat(today))
    return server_routes, path


def test_mutation_api_response_reports_cleanup_removed(tmp_path, monkeypatch):
    server_routes, path = _configure_server_route_state(monkeypatch, tmp_path)
    _write_individual_file(
        path,
        [_trial_block(trial_dates=["2026-05-24"]), _regular_block()],
    )
    monkeypatch.setattr(
        server_routes.lock_manager,
        "get_lock_status",
        lambda: {"holder": "admin", "version": 1},
    )
    monkeypatch.setattr(
        server_routes.restore_manager,
        "get_restore_status",
        lambda: {"active": False, "recovery_required": False, "generation": 0},
    )

    with server_routes.app.test_client() as client:
        _login_admin(client)
        response = client.post("/api/blocks", json=_regular_block(block_id="new-regular", day="Di"))

    body = response.get_json()
    persisted = _read_individual_file(path)
    assert response.status_code == 200
    assert body["ok"] is True
    assert body["individual_cleanup_removed"] == 1
    assert body["force_individual_refresh"] is True
    assert body["individual_revision"]
    assert [block["id"] for block in persisted["blocks"]] == ["lesson-1", body["block"]["id"]]


def test_update_api_reports_when_target_was_pruned_by_cleanup(tmp_path, monkeypatch):
    server_routes, path = _configure_server_route_state(monkeypatch, tmp_path)
    _write_individual_file(path, [_trial_block(trial_dates=["2026-05-24"])])
    monkeypatch.setattr(
        server_routes.lock_manager,
        "get_lock_status",
        lambda: {"holder": "admin", "version": 1},
    )
    monkeypatch.setattr(
        server_routes.restore_manager,
        "get_restore_status",
        lambda: {"active": False, "recovery_required": False, "generation": 0},
    )

    with server_routes.app.test_client() as client:
        _login_admin(client)
        response = client.put("/api/blocks/trial-1", json={"subject": "Updated"})

    body = response.get_json()
    persisted = _read_individual_file(path)
    assert response.status_code == 404
    assert body["ok"] is False
    assert body["code"] == "EXPIRED_TRIAL_PRUNED"
    assert body["individual_cleanup_removed"] == 1
    assert body["force_individual_refresh"] is True
    assert body["individual_revision"]
    assert persisted["blocks"] == []


def test_status_does_not_prune_while_restore_active(tmp_path, monkeypatch):
    server_routes, path = _configure_server_route_state(monkeypatch, tmp_path)
    trial = _trial_block(trial_dates=["2026-05-24"])
    _write_individual_file(path, [trial])
    before = path.read_text(encoding="utf-8")
    monkeypatch.setattr(
        server_routes.lock_manager,
        "get_lock_status",
        lambda: {"holder": None, "version": 1, "acquired_at": None, "last_heartbeat": None},
    )
    monkeypatch.setattr(
        server_routes.restore_manager,
        "get_restore_status",
        lambda: {
            "active": True,
            "recovery_required": False,
            "generation": 7,
            "message": "Restore in progress",
        },
    )

    with server_routes.app.test_client() as client:
        _login_admin(client)
        response = client.get("/api/status")

    body = response.get_json()
    assert response.status_code == 200
    assert body["restore"]["active"] is True
    assert body["restore"]["generation"] == 7
    assert body["individual_revision"] == "2026-05-01T00:00:00"
    assert path.read_text(encoding="utf-8") == before


def test_status_prunes_in_normal_mode(tmp_path, monkeypatch):
    server_routes, path = _configure_server_route_state(monkeypatch, tmp_path)
    _write_individual_file(path, [_trial_block(trial_dates=["2026-05-24"])])
    monkeypatch.setattr(
        server_routes.lock_manager,
        "get_lock_status",
        lambda: {"holder": None, "version": 1, "acquired_at": None, "last_heartbeat": None},
    )
    monkeypatch.setattr(
        server_routes.restore_manager,
        "get_restore_status",
        lambda: {"active": False, "recovery_required": False, "generation": 0},
    )

    with server_routes.app.test_client() as client:
        _login_admin(client)
        response = client.get("/api/status")

    body = response.get_json()
    persisted = _read_individual_file(path)
    assert response.status_code == 200
    assert body["restore"]["active"] is False
    assert body["individual_revision"]
    assert body["individual_revision"] != "2026-05-01T00:00:00"
    assert persisted["blocks"] == []


def test_rooms_report_does_not_include_expired_trial_blocks(tmp_path, monkeypatch):
    base_path = tmp_path / "base_schedule.json"
    individual_path = tmp_path / "individual_lessons.json"
    base_path.write_text(
        json.dumps({"published_at": "2026-05-21T10:00:00", "blocks": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_individual_file(
        individual_path,
        [
            _trial_block(
                block_id="expired-trial",
                day="So",
                trial_dates=["2026-05-24"],
            ),
            _trial_block(
                block_id="today-trial",
                day="Mo",
                trial_dates=["2026-05-25"],
            ),
        ],
    )

    monkeypatch.setattr(rooms_report, "BASE_SCHEDULE_PATH", str(base_path))
    monkeypatch.setattr(rooms_report, "_load_configured_rooms", lambda: {"Villa": ["1.01"]})
    monkeypatch.setattr(state_manager, "INDIVIDUAL_LESSONS_PATH", str(individual_path))
    monkeypatch.setattr(state_manager, "INDIVIDUAL_LOCK_PATH", str(individual_path) + ".lock")
    monkeypatch.setattr(state_manager, "SCHEDULE_HTML_PATH", str(tmp_path / "missing_schedule.html"))
    monkeypatch.setattr(
        state_manager,
        "get_base_schedule",
        lambda: {"published_at": "2026-05-21T10:00:00", "blocks": []},
    )
    monkeypatch.setattr(state_manager, "_today_local_date", lambda: date.fromisoformat("2026-05-25"))

    data = rooms_report.compute_availability()
    sunday_slots = data["buildings"]["Villa"]["days"].get("So", {}).get("1.01", [])
    monday_slots = data["buildings"]["Villa"]["days"].get("Mo", {}).get("1.01", [])
    persisted = _read_individual_file(individual_path)

    assert sunday_slots == []
    assert len(monday_slots) == 1
    assert monday_slots[0]["subject"] == "Trial"
    assert monday_slots[0]["lesson_type"] == "trial"
    assert [block["id"] for block in persisted["blocks"]] == ["today-trial"]
