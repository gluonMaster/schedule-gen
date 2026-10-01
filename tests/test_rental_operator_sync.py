"""Phase 4: stale operator writes, lock ownership and guarded editor regeneration.

Everything runs on a temporary project root shared by Flask and the generator.
"""
import importlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gear_xls import base_schedule_manager, excel_exporter, integration, snapshot_guard, state_manager
from gear_xls.schedule_exchange import read_sync_metadata
from gear_xls.services.schedule_pipeline import SchedulePipeline, SchedulePipelineError

RENTAL = dict(building="Villa", day="Mo", room="0.06", subject="Vermietung", teacher="Kontakt",
              students="Verein", start_time="10:00", end_time="11:00", lesson_type="rental", rental_dates=[])
GROUP = dict(subject="Math", teacher="Teacher", students="1A", building="Villa", room="1.10", day="Mo",
             start_time="09:00", end_time="09:45", duration=45, lesson_type="group")


@pytest.fixture
def editor(tmp_path, monkeypatch):
    for name in ("gear_xls", "xlsx_initial", "visualiser"):
        (tmp_path / name).mkdir()
    (tmp_path / "gui.py").touch()
    (tmp_path / "gear_xls" / "server_routes.py").touch()
    monkeypatch.setenv("SCHEDGEN_PROJECT_ROOT", str(tmp_path))
    routes = importlib.import_module("gear_xls.server_routes")
    routes.app.config.update(TESTING=True)
    state_dir = tmp_path / "gear_xls" / "schedule_state"
    html = tmp_path / "gear_xls" / "html_output" / "schedule.html"
    html.parent.mkdir(parents=True)
    html.write_text("<html><head></head><body>generation 0</body></html>", encoding="utf-8")
    ind, base = state_dir / "individual_lessons.json", state_dir / "base_schedule.json"
    for module in (state_manager, routes.state_manager):
        monkeypatch.setattr(module, "INDIVIDUAL_LESSONS_PATH", str(ind))
        monkeypatch.setattr(module, "INDIVIDUAL_LOCK_PATH", str(ind) + ".lock")
        monkeypatch.setattr(module, "SCHEDULE_HTML_PATH", str(html))
        monkeypatch.setattr(module, "_today_local_date", lambda: date(2026, 10, 1))
    for module in (base_schedule_manager, sys.modules["base_schedule_manager"]):
        monkeypatch.setattr(module, "BASE_SCHEDULE_PATH", str(base))
        monkeypatch.setattr(module, "BASE_LOCK_PATH", str(base) + ".lock")
    monkeypatch.setattr(routes, "EXCEL_EXPORTS_DIR", str(tmp_path / "exports"))
    # Lock and restore state use the real managers on the temporary project root.
    return SimpleNamespace(routes=routes, root=tmp_path, state_dir=state_dir, html=html, ind=ind, base=base)


def client_for(editor, login, role):
    client = editor.routes.app.test_client()
    with client.session_transaction() as session:
        session.update(login=login, display_name=login, role=role)
    return client


def acquire(client):
    response = client.post("/api/lock/acquire")
    assert response.json["ok"], response.json
    return response.json["version"]


def release(client, version):
    assert client.post("/api/lock/release", json={"version": version}).json["ok"]


def page(client):
    return client.get("/api/schedule").json


def guarded(state, version, **payload):
    return {**payload, "expected_individual_revision": state["individual_revision"], "lock_version": version}


def create_rental(editor, login="organizer_one", **updates):
    client = client_for(editor, login, "organizer")
    version = acquire(client)
    response = client.post("/api/blocks", json=guarded(page(client), version, **{**RENTAL, **updates}))
    assert response.status_code == 200, response.json
    release(client, version)
    return response.json["block"]


def snapshot_files(editor):
    return [path.read_bytes() if path.exists() else None for path in (editor.html, editor.base, editor.ind)]


def export(editor, client, path, state=None, html_revision=None, records=None):
    state = state or page(client)
    records = records if records is not None else [GROUP] + [
        {**block, "block_id": block["id"], "duration": 60} for block in state["individual"]]
    form = {
        "schedule_data": json.dumps(records),
        "schedule_sync": json.dumps({
            "format_version": 1, "source_base_revision": state["base_revision"] or "",
            "source_individual_revision": state["individual_revision"] or "", "snapshot_scope": "full"}),
        "schedule_html_revision": html_revision if html_revision is not None else state["schedule_html_revision"],
    }
    response = client.post("/export_to_excel", data=form)
    if response.status_code == 200:
        path.write_bytes(response.data)
    return response


def generate(path):
    return integration.generate_editor_from_excel(str(path), SchedulePipeline(), spiski_data={})


def test_stale_full_form_is_rejected_and_reread_save_passes(editor):
    created = create_rental(editor)
    organizer_one, admin_one = client_for(editor, "organizer_one", "organizer"), client_for(editor, "admin_one", "admin")
    admin_one_page = page(admin_one)  # admin_one opened the editor before organizer_one moved the rental.
    version = acquire(organizer_one)
    moved = organizer_one.put(f"/api/blocks/{created['id']}", json=guarded(page(organizer_one), version, **{**created, "room": "0.08"}))
    assert moved.status_code == 200
    release(organizer_one, version)

    version = acquire(admin_one)
    stale_form = {**created, "start_time": "12:00", "end_time": "13:00"}  # new time, old room 0.06
    response = admin_one.put(f"/api/blocks/{created['id']}", json=guarded(admin_one_page, version, **stale_form))
    assert response.status_code == 409 and response.json["code"] == "INDIVIDUAL_REVISION_CONFLICT"
    assert response.json["force_individual_refresh"] is True
    fresh = page(admin_one)
    assert response.json["individual_revision"] == fresh["individual_revision"]
    [block] = fresh["individual"]
    assert (block["room"], block["start_time"]) == ("0.08", "10:00")

    retry = admin_one.put(f"/api/blocks/{created['id']}",
                     json=guarded(fresh, version, **{**block, "start_time": "12:00", "end_time": "13:00"}))
    assert retry.status_code == 200
    [block] = page(admin_one)["individual"]
    assert (block["id"], block["lesson_type"], block["room"], block["start_time"]) == (
        created["id"], "rental", "0.08", "12:00")


def test_each_managed_write_requires_markers_and_current_revision(editor):
    client = client_for(editor, "admin_one", "admin")
    stale = page(client)
    version = acquire(client)
    rental = client.post("/api/blocks", json=guarded(page(client), version, **RENTAL)).json["block"]
    trial = client.post("/api/blocks", json=guarded(page(client), version, **{
        **RENTAL, "subject": "Probe", "lesson_type": "trial", "room": "0.07", "trial_dates": ["2026-10-05"]})).json["block"]
    current = page(client)
    before = editor.ind.read_bytes()
    for method, url, payload in [
        ("post", "/api/blocks", RENTAL),
        ("put", f"/api/blocks/{rental['id']}", {"room": "0.09"}),
        ("delete", f"/api/blocks/{rental['id']}", {}),
        ("post", f"/api/blocks/{trial['id']}/convert", {}),
        ("delete", "/api/columns", {"building": "Villa", "day": "Mo", "room": "0.06"}),
    ]:
        call = getattr(client, method)
        assert call(url, json=guarded(stale, version, **payload)).status_code == 409
        missing = call(url, json={**payload, "lock_version": version})
        assert (missing.status_code, missing.json["code"]) == (400, "EXPECTED_INDIVIDUAL_REVISION_REQUIRED")
        missing = call(url, json={**payload, "expected_individual_revision": current["individual_revision"]})
        assert (missing.status_code, missing.json["code"]) == (400, "LOCK_VERSION_REQUIRED")
    assert editor.ind.read_bytes() == before


def test_old_lock_owner_and_late_request_before_generation_are_rejected(editor, monkeypatch):
    created = create_rental(editor)
    organizer_one = client_for(editor, "organizer_one", "organizer")
    old_version = acquire(organizer_one)
    release(organizer_one, old_version)
    new_version = acquire(organizer_one)  # the same login in a new tab
    current = page(organizer_one)
    stale_tab = organizer_one.put(f"/api/blocks/{created['id']}", json=guarded(current, old_version, room="0.07"))
    assert (stale_tab.status_code, stale_tab.json["code"]) == (403, "STALE_LOCK")
    release(organizer_one, new_version)

    admin_one = client_for(editor, "admin_one", "admin")
    admin_one_version = acquire(admin_one)
    late_owner = organizer_one.put(f"/api/blocks/{created['id']}", json=guarded(current, new_version, room="0.07"))
    assert (late_owner.status_code, late_owner.json["code"]) == (403, "NO_LOCK")

    # admin_one's request passes the route lock check, then a fresh generation is applied.
    state = page(admin_one)
    snapshot = {"format_version": 1, "source_base_revision": "", "snapshot_scope": "full",
                "source_individual_revision": state["individual_revision"]}
    original = editor.routes._require_lock

    def check_then_generate(login):
        error = original(login)
        integration.reset_web_editor_state(state["individual"], sync_metadata=snapshot)
        return error

    monkeypatch.setattr(editor.routes, "_require_lock", check_then_generate)
    late = admin_one.put(f"/api/blocks/{created['id']}", json=guarded(state, admin_one_version, room="0.09"))
    monkeypatch.setattr(editor.routes, "_require_lock", original)
    assert late.status_code == 409
    after = page(admin_one)
    assert after["individual"] == state["individual"] and after["individual_revision"] != state["individual_revision"]
    lock = admin_one.get("/api/lock/status").json
    assert (lock["holder"], lock["version"]) == ("admin_one", admin_one_version)  # generation kept the active lock


def test_export_is_labeled_only_with_server_confirmed_snapshot(editor, tmp_path):
    create_rental(editor)
    admin_one = client_for(editor, "admin_one", "admin")
    state = page(admin_one)
    path = tmp_path / "export.xlsx"
    assert export(editor, admin_one, path, state).status_code == 200
    book = openpyxl.load_workbook(path)
    assert read_sync_metadata(book)["source_individual_revision"] == state["individual_revision"]
    book.close()
    for stale in (
        {"state": {**state, "individual_revision": "older"}},
        {"state": {**state, "base_revision": "older"}},
        {"html_revision": "old-page"},
        {"records": [GROUP]},  # payload lost the managed rental
    ):
        response = export(editor, admin_one, tmp_path / "stale.xlsx", **{"state": state, **stale})
        assert (response.status_code, response.json["code"]) == (409, "EXPORT_SNAPSHOT_STALE")
    assert not (tmp_path / "stale.xlsx").exists()


def test_generation_refuses_changed_source_and_applies_fresh_snapshot_once(editor, tmp_path):
    first = create_rental(editor)
    admin_one = client_for(editor, "admin_one", "admin")
    old_export = tmp_path / "old.xlsx"
    assert export(editor, admin_one, old_export).status_code == 200
    later = create_rental(editor, room="0.08")  # added after the export
    before = snapshot_files(editor)
    with pytest.raises(SchedulePipelineError, match="После экспорта изменилось"):
        generate(old_export)
    assert snapshot_files(editor) == before

    fresh_export = tmp_path / "fresh.xlsx"
    assert export(editor, admin_one, fresh_export).status_code == 200
    result = generate(fresh_export)
    assert os.path.normcase(result["html_file"]) == os.path.normcase(str(editor.html))
    html = editor.html.read_text(encoding="utf-8")
    assert "generation 0" not in html and "Math" in html and "data-lesson-type='rental'" not in html
    state = page(admin_one)
    assert {block["id"]: block["lesson_type"] for block in state["individual"]} == {
        first["id"]: "rental", later["id"]: "rental"}
    assert state["base_revision"] is None
    assert state["schedule_html_revision"] != snapshot_guard.schedule_html_revision(before[0])
    applied = snapshot_files(editor)
    with pytest.raises(SchedulePipelineError, match="После экспорта изменилось"):
        generate(fresh_export)
    assert snapshot_files(editor) == applied


def test_legacy_file_and_failed_write_leave_previous_state(editor, tmp_path, monkeypatch):
    create_rental(editor)
    admin_one = client_for(editor, "admin_one", "admin")
    legacy = tmp_path / "legacy.xlsx"
    excel_exporter.create_excel_from_html_data([GROUP], legacy)
    before = snapshot_files(editor)
    with pytest.raises(SchedulePipelineError, match="первичного импорта"):
        generate(legacy)
    assert snapshot_files(editor) == before

    fresh = tmp_path / "fresh.xlsx"
    assert export(editor, admin_one, fresh).status_code == 200
    writes = []
    real_replace = snapshot_guard._replace_file

    def fail_second_write(path, data):
        writes.append(path)
        if len(writes) == 2:
            raise OSError("disk full")
        real_replace(path, data)

    monkeypatch.setattr(snapshot_guard, "_replace_file", fail_second_write)
    with pytest.raises(SchedulePipelineError, match="восстановлены"):
        generate(fresh)
    assert os.path.normcase(writes[0]) == os.path.normcase(str(editor.html))
    assert snapshot_files(editor) == before


def test_guarded_write_with_trial_cleanup_and_stale_publication(editor):
    editor.state_dir.mkdir(parents=True)
    expired = {**RENTAL, "id": "expired", "lesson_type": "trial", "subject": "Probe", "trial_dates": ["2026-09-28"]}
    editor.ind.write_text(json.dumps({"last_modified": "rev-0", "blocks": [
        expired, {**RENTAL, "id": "rent", "rental_dates": ["2026-09-28"]}]}), encoding="utf-8")
    admin_one = client_for(editor, "admin_one", "admin")
    version = acquire(admin_one)
    response = admin_one.put("/api/blocks/rent", json={
        "room": "0.08", "expected_individual_revision": "rev-0", "lock_version": version})
    assert response.status_code == 200
    assert response.json["force_individual_refresh"] is True and response.json["individual_cleanup_removed"] == 1
    stored = json.loads(editor.ind.read_text(encoding="utf-8"))
    assert response.json["individual_revision"] == stored["last_modified"] != "rev-0"
    [rental] = stored["blocks"]
    assert (rental["id"], rental["lesson_type"], rental["room"], rental["rental_dates"]) == (
        "rent", "rental", "0.08", ["2026-09-28"])

    html_revision = page(admin_one)["schedule_html_revision"]
    publish = {"blocks": [GROUP], "lock_version": version, "expected_html_revision": html_revision}
    stale_base = admin_one.post("/api/schedule/publish", json={**publish, "expected_base_revision": "older"})
    assert (stale_base.status_code, stale_base.json["code"]) == (409, "BASE_REVISION_CONFLICT")
    stale_page = admin_one.post("/api/schedule/publish", json={
        **publish, "expected_base_revision": None, "expected_html_revision": "old-page"})
    assert (stale_page.status_code, stale_page.json["code"]) == (409, "SCHEDULE_HTML_CHANGED")
    assert not editor.base.exists()
