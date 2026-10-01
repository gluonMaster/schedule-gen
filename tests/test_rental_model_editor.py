"""Phase 1: managed rental API/model, publication boundaries and restore validation."""
import importlib
import json
import sys
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from gear_xls import backup_manager, base_schedule_manager, restore_manager, state_manager
from gear_xls.generators.html_block_generator import HTMLBlockGenerator


def rental(**updates):
    return {
        "building": "Villa", "day": "Mo", "room": "1.01",
        "subject": "Vermietung", "teacher": "", "students": "Organisation & Kontakt",
        "start_time": "10:00", "end_time": "11:00", "lesson_type": "rental",
        "rental_dates": [], "color": "#abcdef", "notes": "Keep this metadata",
        **updates,
    }


@pytest.fixture
def isolated_editor(tmp_path, monkeypatch):
    # Import-time logging/secret-key creation also stays outside the working copy.
    for name in ("gear_xls", "xlsx_initial", "visualiser"):
        (tmp_path / name).mkdir()
    (tmp_path / "gui.py").touch()
    (tmp_path / "gear_xls" / "server_routes.py").touch()
    monkeypatch.setenv("SCHEDGEN_PROJECT_ROOT", str(tmp_path))
    routes = importlib.import_module("gear_xls.server_routes")
    routes.app.config.update(TESTING=True)
    ind_path = tmp_path / "individual_lessons.json"
    base_path = tmp_path / "base_schedule.json"
    for module in (state_manager, routes.state_manager):
        monkeypatch.setattr(module, "INDIVIDUAL_LESSONS_PATH", str(ind_path))
        monkeypatch.setattr(module, "INDIVIDUAL_LOCK_PATH", str(ind_path) + ".lock")
        monkeypatch.setattr(module, "SCHEDULE_HTML_PATH", str(tmp_path / "missing.html"))
        monkeypatch.setattr(module, "_today_local_date", lambda: date(2026, 10, 1))
    for module in (base_schedule_manager, sys.modules["base_schedule_manager"]):
        monkeypatch.setattr(module, "BASE_SCHEDULE_PATH", str(base_path))
        monkeypatch.setattr(module, "BASE_LOCK_PATH", str(base_path) + ".lock")
    monkeypatch.setattr(routes.lock_manager, "get_lock_status", lambda: {"holder": "operator", "version": 1})
    monkeypatch.setattr(routes.restore_manager, "get_restore_status", lambda: {
        "active": False, "recovery_required": False, "generation": 0,
    })
    return routes, ind_path, base_path


def login(client, role):
    with client.session_transaction() as session:
        session.update(login="operator", display_name="Test", role=role)


def test_organizer_rental_lifecycle_and_publication_cycles(isolated_editor):
    routes, ind_path, base_path = isolated_editor
    with routes.app.test_client() as client:
        login(client, "organizer")
        created = client.post("/api/blocks", json=rental())
        assert created.status_code == 200
        block_id = created.json["block"]["id"]
        revision = None
        for dates, room, time in [(["2026-10-05"], "1.01", "10:00"), ([], "1.02", "11:00"), ([], "1.02", "11:30")]:
            updated = client.put(f"/api/blocks/{block_id}", json={
                "lesson_type": "rental", "subject": "Vermietung", "rental_dates": dates,
                "room": room, "start_time": time, "end_time": "12:30", "id": "obsolete-client-id",
            })
            assert updated.status_code == 200
            block = updated.json["block"]
            assert block["id"] == block_id and block["lesson_type"] == "rental"
            assert block["rental_dates"] == dates
            assert block["teacher"] == "" and block["students"] == "Organisation & Kontakt"
            assert block["notes"] == "Keep this metadata"
            login(client, "admin")
            group = rental(subject="Math", lesson_type="group", teacher="Teacher", rental_dates=None)
            group.pop("rental_dates")
            publication = client.post("/api/schedule/publish", json={
                "blocks": [group, {**block, "block_id": block_id, "source_layer": "individual"}],
                "expected_base_revision": revision,
            })
            assert publication.status_code == 200
            revision = publication.json["base_revision"]
            state = client.get("/api/schedule").json
            assert len(state["individual"]) == 1 and state["individual"][0]["id"] == block_id
            assert [b["subject"] for b in state["base"]] == ["Math"]
            login(client, "organizer")
        assert client.post("/api/schedule/publish", json={"blocks": []}).status_code == 403
        assert client.put(f"/api/blocks/{block_id}", json={"lesson_type": "group"}).status_code == 400
        assert client.delete(f"/api/blocks/{block_id}").status_code == 200
    assert json.loads(ind_path.read_text(encoding="utf-8"))["blocks"] == []
    assert len(json.loads(base_path.read_text(encoding="utf-8"))["blocks"]) == 1


@pytest.mark.parametrize("role", ["admin", "editor", "organizer", "viewer", "unknown"])
def test_managed_api_denies_group_and_unknown_type(isolated_editor, role):
    routes, _, _ = isolated_editor
    with routes.app.test_client() as client:
        login(client, role)
        for kind in ("group", "unknown"):
            assert client.post("/api/blocks", json=rental(lesson_type=kind)).status_code in (400, 403)
    assert state_manager._validate_block(rental(), "unknown") == "Forbidden lesson_type"


@pytest.mark.parametrize("role", ["admin", "editor"])
def test_admin_editor_can_work_with_rental(isolated_editor, role):
    routes, _, _ = isolated_editor
    with routes.app.test_client() as client:
        login(client, role)
        response = client.post("/api/blocks", json=rental(subject=""))
        assert response.status_code == 200
        assert response.json["block"]["subject"] == "Vermietung"
        assert client.delete("/api/blocks/" + response.json["block"]["id"]).status_code == 200


def test_organizer_cannot_take_over_teaching_block(isolated_editor):
    routes, _, _ = isolated_editor
    with routes.app.test_client() as client:
        login(client, "admin")
        response = client.post("/api/blocks", json=rental(lesson_type="individual", subject="Deutsch"))
        block_id = response.json["block"]["id"]
        login(client, "organizer")
        assert client.put(f"/api/blocks/{block_id}", json={"lesson_type": "rental"}).status_code == 400
        assert client.delete(f"/api/blocks/{block_id}").status_code == 403


@pytest.mark.parametrize("extra", [
    {"block_id": "managed-id"}, {"source_layer": "individual"},
    {"subject": " VERMietung "}, {"rental_dates_json": "[]"},
])
def test_base_rejects_managed_block_mislabeled_group(isolated_editor, extra):
    routes, _, base_path = isolated_editor
    with routes.app.test_client() as client:
        login(client, "admin")
        payload = rental(lesson_type="group", subject="Room booking", **extra) if "subject" not in extra else rental(lesson_type="group", **extra)
        payload.pop("rental_dates")
        response = client.post("/api/schedule/publish", json={"blocks": [payload], "expected_base_revision": None})
        assert response.status_code == 400 and response.json["code"] == "MANAGED_BLOCK_IN_BASE"
    assert not base_path.exists()


def test_base_rejects_known_managed_id_without_origin(isolated_editor):
    routes, _, _ = isolated_editor
    with routes.app.test_client() as client:
        login(client, "admin")
        block = client.post("/api/blocks", json=rental(subject="Custom booking")).json["block"]
        block["lesson_type"] = "group"
        block.pop("rental_dates")
        response = client.post("/api/schedule/publish", json={"blocks": [block], "expected_base_revision": None})
        assert response.status_code == 400 and response.json["code"] == "MANAGED_BLOCK_IN_BASE"


@pytest.mark.parametrize("updates,error", [
    ({"rental_dates": ["2026-10-12", "2026-10-05", "2026-10-05"]}, None),
    ({"day": "So", "rental_dates": ["2026-10-04"]}, None),
    ({"day": "So", "rental_dates": []}, "Sunday"),
    ({"rental_dates": "2026-10-05"}, "list"),
    ({"rental_dates": ["2026-02-30"]}, "invalid date"),
    ({"rental_dates": ["2026-10-04"]}, "not matching"),
    ({"rental_dates": ["20261005"]}, "YYYY-MM-DD"),
    ({"start_time": "25:00"}, "invalid"),
    ({"end_time": "09:00"}, "after"),
    ({"teacher": []}, "string"),
])
def test_rental_validation(updates, error):
    block = rental(**updates)
    actual = state_manager._validate_block(block, "organizer")
    assert actual is None if error is None else error in actual
    if error is None:
        assert block["rental_dates"] == sorted(set(updates["rental_dates"]))


def test_rental_and_exact_legacy_trial_are_retained_on_read(isolated_editor):
    _, ind_path, _ = isolated_editor
    blocks = [rental(id="dated-rental", rental_dates=["2026-09-28"]),
              rental(id="legacy", lesson_type="trial", subject=" VERMietung ", trial_dates=["2026-09-28"]),
              rental(id="ordinary", lesson_type="trial", subject="Trial", trial_dates=["2026-09-28"])]
    ind_path.write_text(json.dumps({"last_modified": "old", "blocks": blocks}), encoding="utf-8")
    retained = state_manager.get_individual_lessons()["blocks"]
    assert retained == blocks[:2]
    before = ind_path.read_bytes()
    assert state_manager.get_individual_lessons()["blocks"] == retained
    assert ind_path.read_bytes() == before
    ordinary = rental(lesson_type="trial", subject="Trial", trial_dates=["2026-10-05"])
    assert state_manager._validate_block(ordinary, "organizer") is None
    assert "rental_dates" not in ordinary
    assert state_manager._validate_block(rental(lesson_type="trial", trial_dates=[]), "organizer")


def test_backup_restore_rental_dates_id_and_group_rejection():
    for block in (rental(id="weekly"), rental(id="dated", day="So", rental_dates=["2026-10-04"])):
        data = {"last_modified": "old", "blocks": [block]}
        backup_manager.validate_individual_state(data)
        restored = restore_manager._normalize_individual_state(data, restore_revision="restored")
        assert restored["blocks"] == [block]
        assert restored["last_modified"] == "restored"
    with pytest.raises(backup_manager.BackupValidationError):
        backup_manager.validate_individual_state({"blocks": [rental(id="bad", lesson_type="group")]})
    with pytest.raises(backup_manager.BackupValidationError):
        backup_manager.validate_individual_state({"blocks": [rental(id="bad", day="So")]})


@pytest.mark.parametrize("raw_dates,valid", [('["2026-10-04"]', True), ('[]', False), ('broken', False)])
def test_export_validation_accepts_only_dated_sunday_rental(raw_dates, valid):
    from gear_xls.excel_exporter import ExcelExportValidationError, validate_schedule_data_for_export
    block = rental(day="So", rental_dates_json=raw_dates)
    if valid:
        validate_schedule_data_for_export([block])
    else:
        with pytest.raises(ExcelExportValidationError):
            validate_schedule_data_for_export([block])


@pytest.mark.parametrize("teacher,students", [("", "Org"), ("Contact", ""), ("", "")])
def test_generated_block_preserves_empty_positions_dates_and_id(teacher, students):
    interval = rental(id="stable-id", teacher=teacher, students=students, rental_dates=["2026-10-05"])
    interval.update(start=600, end=660, col=0)
    html = HTMLBlockGenerator()._generate_single_block(interval, 0, 540)
    assert "data-block-id='stable-id'" in html
    assert "data-source-layer='individual'" in html
    attrs, body = html.split(">", 1)
    parsed = state_manager._parse_embedded_individual_block(attrs, body.rsplit("</div>", 1)[0])
    assert parsed["id"] == "stable-id" and parsed["lesson_type"] == "rental"
    assert (parsed["teacher"], parsed["students"], parsed["room"]) == (teacher, students, "1.01")
    assert parsed["rental_dates"] == ["2026-10-05"]


def test_generator_and_route_deliver_updated_editor_code(isolated_editor, tmp_path, monkeypatch):
    from gear_xls.html_javascript import get_javascript
    routes, _, _ = isolated_editor
    js = get_javascript(15, 100, 45, ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"], 5)
    for name in ("block_creation_dialog", "editing_update", "lesson_type_filter", "export_to_excel", "block_content_sync", "conflict_detector"):
        assert (PROJECT_ROOT / "gear_xls" / "js_modules" / f"{name}.js").read_text(encoding="utf-8") in js
    html_path = tmp_path / "test-schedule.html"
    html_path.write_text("<html><head></head><body></body></html>", encoding="utf-8")
    monkeypatch.setattr(routes, "get_schedule_html_path", lambda: str(html_path))
    monkeypatch.setattr(routes, "get_static_dir", lambda: str(PROJECT_ROOT / "gear_xls" / "static"))
    monkeypatch.setattr(routes, "get_js_modules_dir", lambda: str(PROJECT_ROOT / "gear_xls" / "js_modules"))
    with routes.app.test_client() as client:
        login(client, "organizer")
        html = client.get("/schedule").get_data(as_text=True)
        for url, file in [
            ("/static/individual_ui.js", "static/individual_ui.js"),
            ("/static/base_sync_ui.js", "static/base_sync_ui.js"),
            ("/static/auth_ui.js", "static/auth_ui.js"),
            ("/js_modules/trial_ui.js", "js_modules/trial_ui.js"),
            ("/js_modules/conflict_detector.js", "js_modules/conflict_detector.js"),
        ]:
            version = "20261001_rental2" if "conflict_detector" in url else "20261001_rental1"
            assert f'{url}?v={version}' in html
            response = client.get(url + "?v=" + version)
            assert response.status_code == 200
            assert response.data == (PROJECT_ROOT / "gear_xls" / file).read_bytes()
