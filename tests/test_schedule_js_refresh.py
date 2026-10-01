"""Phase 6: one-time refresh of the embedded editor script in an existing schedule.html."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gear_xls.html_javascript import get_javascript
from gear_xls.scripts import refresh_schedule_js as refresh
from gear_xls.scripts.rental_repair import RepairError

SPISKI = {"subjects": ["Vermietung"], "groups": ["3D"], "teachers": ["ol1"],
          "rooms_Villa": ["0.06"], "rooms_Kolibri": ["2.2"]}
HEAD = "<!DOCTYPE html>\n<html lang='ru'>\n<head>\n<style>.activity-block{}</style>\n    \n\n    "
BODY = ("\n</head>\n<body>\n<div class='activity-block' data-lesson-type='group' data-room='0.06'>"
        "<strong>Kunst</strong><br>ol2<br><br>0.06<br>10:00-11:00</div>\n</body>\n</html>\n")


def page(script):
    return (HEAD + script[script.index("<script>"):].rstrip() + BODY).replace("\n", "\r\n").encode("utf-8")


def current_script():
    return get_javascript(15, 100, 45, ["Mo", "Di", "So"], 5, 0.5, 540, spiski_data=SPISKI)


def old_page():
    exporter = (ROOT / "gear_xls" / "js_modules" / "export_to_excel.js").read_text(encoding="utf-8")
    script = current_script()
    assert exporter in script
    return page(script.replace(exporter, "function exportOld() { /* July exporter */ }"))


def test_only_embedded_script_is_replaced_and_refresh_is_idempotent():
    raw = old_page()
    new_bytes, report = refresh.prepare(raw)

    assert new_bytes == page(current_script())  # what the generator gives for this page and its spiski
    assert raw.startswith(HEAD.replace("\n", "\r\n").encode()) and new_bytes.endswith(BODY.replace("\n", "\r\n").encode())
    assert report["layout"] == {"cell_height": 15, "day_cell_width": 100, "header_height": 45,
                                "days_order": ["Mo", "Di", "So"], "time_interval": 5, "border_width": 0.5,
                                "grid_start": 540}
    assert all(not m["old"] and m["new"] for m in report["exporter_markers"].values())
    assert report["changed"] and refresh.prepare(new_bytes)[1]["changed"] is False
    with pytest.raises(RepairError):
        refresh.prepare(page(current_script()).replace(b"window.spiskiData = spiskiData;", b""))


def test_apply_requires_free_lock_and_expected_hash_and_keeps_original(tmp_path):
    html = tmp_path / "schedule.html"
    state = tmp_path / "schedule_state"
    state.mkdir()
    raw = old_page()
    html.write_bytes(raw)
    lock = state / "lock.json"
    lock.write_text(json.dumps({"holder": "organizer_one", "version": 7}), encoding="utf-8")
    sha = refresh._sha256(raw)

    with pytest.raises(RepairError, match="organizer_one"):
        refresh.apply(str(html), str(state), sha, str(tmp_path / "backup"))
    lock.write_text(json.dumps({"holder": None, "version": 8}), encoding="utf-8")
    with pytest.raises(RepairError, match="изменён"):
        refresh.apply(str(html), str(state), "0" * 64, str(tmp_path / "backup"))
    assert html.read_bytes() == raw and not (tmp_path / "backup").exists()

    report = refresh.apply(str(html), str(state), sha, str(tmp_path / "backup"))
    assert html.read_bytes() == page(current_script()) and report["new_html_sha256"] == refresh._sha256(html.read_bytes())
    assert (tmp_path / "backup" / "original" / "schedule.html").read_bytes() == raw
    manifest = json.loads((tmp_path / "backup" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "applied" and manifest["report"]["html_sha256"] == sha
    assert refresh.apply(str(html), str(state), report["new_html_sha256"], str(tmp_path / "again"))["changed"] is False
    assert not (tmp_path / "again").exists()
