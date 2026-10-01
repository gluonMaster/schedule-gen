"""One-time refresh of the embedded editor JavaScript in an existing schedule.html.

    dry-run --project-root ROOT                                   (default; reads files only)
    apply   --project-root ROOT --expect-html SHA --backup-dir NEW_DIR

The working page is generated from Excel, but its content comes from the JSON layers, which must not
be replaced. Only the single <script> block produced by html_javascript.get_javascript() is rebuilt
from this checkout's js_modules; the layout values and spiski data are taken from that same block,
and every byte before and after it stays unchanged. Apply runs under the phase-4 file locks
(snapshot_guard), refuses an active restore or operator lock, saves the original bytes first and
verifies the written file.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (PROJECT_ROOT, os.path.join(PROJECT_ROOT, "gear_xls")):
    if path not in sys.path:
        sys.path.insert(0, path)

from gear_xls import snapshot_guard  # noqa: E402
from gear_xls.html_javascript import get_javascript  # noqa: E402
from gear_xls.runtime_paths import get_schedule_html_path, get_schedule_state_dir  # noqa: E402
from gear_xls.scripts.rental_repair import RepairError, _check_no_operator  # noqa: E402

BACKUP_FORMAT = "schedgen.schedule_js_refresh_backup"
SCRIPT_START = "<script>\n        document.addEventListener('DOMContentLoaded', function() {"
SCRIPT_END = "initializeApplication();\n        });\n    </script>"
SPISKI_RE = re.compile(r"var spiskiData = \{.*?\};\s*window\.spiskiData = spiskiData;", re.S)
NUMBER = r"(-?\d+(?:\.\d+)?)"
LAYOUT_RE = {
    "cell_height": re.compile(r"var gridCellHeight = " + NUMBER + ";"),
    "day_cell_width": re.compile(r"var dayCellWidth = " + NUMBER + ";"),
    "header_height": re.compile(r"var headerHeight = " + NUMBER + ";"),
    "days_order": re.compile(r"var daysOrder = (\[[^\]\n]*\]);"),
    "time_interval": re.compile(r"var timeInterval = " + NUMBER + ";"),
    "border_width": re.compile(r"var borderWidth = " + NUMBER + ";"),
    "grid_start": re.compile(r"var gridStart = " + NUMBER + ";"),
}
# Present only in the exporter that carries the snapshot provenance of phases 3-4.
EXPORTER_MARKERS = ("schedule_sync=", "getAppliedBaseRevision", "includeHidden: true")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _number(text):
    return float(text) if "." in text else int(text)


def _layout(script):
    head = script[:script.find("var spiskiData")]
    values = {}
    for name, pattern in LAYOUT_RE.items():
        found = pattern.findall(head)
        if len(found) != 1:
            raise RepairError(f"Встроенный скрипт: параметр {name} найден {len(found)} раз; структура не распознана.")
        values[name] = json.loads(found[0]) if name == "days_order" else _number(found[0])
    return values


def prepare(raw):
    """New page bytes and a report; only the embedded script block may differ from raw."""
    text = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    if newline == "\r\n" and text.count("\r") != text.count("\r\n"):
        raise RepairError("Смешанные переводы строк в schedule.html; структура не распознана.")
    norm = text.replace("\r\n", "\n")
    if norm.count(SCRIPT_START) != 1:
        raise RepairError("Встроенный скрипт редактора не найден однозначно.")
    start = norm.index(SCRIPT_START)
    end = norm.find("</script>", start) + len("</script>")
    old_script = norm[start:end]
    if not old_script.endswith(SCRIPT_END):
        raise RepairError("Конец встроенного скрипта не распознан.")
    old_spiski = SPISKI_RE.findall(old_script)
    if len(old_spiski) != 1:
        raise RepairError("Данные списков во встроенном скрипте не распознаны.")
    layout = _layout(old_script)

    with contextlib.redirect_stdout(io.StringIO()):
        generated = get_javascript(layout["cell_height"], layout["day_cell_width"], layout["header_height"],
                                   layout["days_order"], layout["time_interval"], layout["border_width"],
                                   layout["grid_start"], spiski_data=None)
    if "не найден по пути" in generated:
        raise RepairError("Не найден один из js_modules; страница не изменена.")
    new_script = generated[generated.index("<script>"):].rstrip()
    new_script = SPISKI_RE.sub(lambda _match: old_spiski[0], new_script, count=1)
    if not new_script.startswith(SCRIPT_START) or not new_script.endswith(SCRIPT_END) \
            or new_script.count("</script>") != 1:
        raise RepairError("Сгенерированный скрипт не соответствует ожидаемой структуре.")

    new_bytes = (norm[:start] + new_script + norm[end:]).replace("\n", newline).encode("utf-8")
    prefix = (norm[:start]).replace("\n", newline).encode("utf-8")
    suffix = (norm[end:]).replace("\n", newline).encode("utf-8")
    if not (raw.startswith(prefix) and raw.endswith(suffix) and new_bytes.startswith(prefix)
            and new_bytes.endswith(suffix)):
        raise RepairError("Части страницы вне скрипта изменились бы; страница не изменена.")
    report = {
        "html_sha256": _sha256(raw), "new_html_sha256": _sha256(new_bytes),
        "html_revision": snapshot_guard.schedule_html_revision(raw),
        "new_html_revision": snapshot_guard.schedule_html_revision(new_bytes),
        "changed": new_bytes != raw, "layout": layout,
        "script_chars": {"old": len(old_script), "new": len(new_script)},
        "unchanged_bytes": {"prefix": len(prefix), "suffix": len(suffix)},
        "exporter_markers": {marker: {"old": marker in old_script, "new": marker in new_script}
                             for marker in EXPORTER_MARKERS},
    }
    if not all(item["new"] for item in report["exporter_markers"].values()):
        raise RepairError("В сгенерированном скрипте нет актуального экспортёра; страница не изменена.")
    return new_bytes, report


def dry_run(html_path):
    with open(html_path, "rb") as source:
        return prepare(source.read())[1]


def apply(html_path, state_dir, expected_sha, backup_dir):
    state_dir = os.path.abspath(state_dir)
    with snapshot_guard.locked_editor_state(state_dir):
        snapshot_guard._check_no_restore(state_dir)
        _check_no_operator(state_dir)
        with open(html_path, "rb") as source:
            raw = source.read()
        if _sha256(raw) != expected_sha:
            raise RepairError(f"schedule.html изменён: sha256 {_sha256(raw)} вместо ожидаемого {expected_sha}.")
        new_bytes, report = prepare(raw)
        if not report["changed"]:
            return report
        if os.path.exists(backup_dir) and os.listdir(backup_dir):
            raise RepairError(f"Каталог резервной копии не пуст: {backup_dir}")
        original = os.path.join(backup_dir, "original", "schedule.html")
        os.makedirs(os.path.dirname(original), exist_ok=True)
        snapshot_guard._replace_file(original, raw)
        with open(original, "rb") as source:
            if source.read() != raw:
                raise RepairError("Резервная копия schedule.html не совпадает с исходником; запись не начата.")
        manifest = dict(format=BACKUP_FORMAT, format_version=1, html_path=os.path.abspath(html_path),
                        created_at=datetime.now(timezone.utc).isoformat(), status="prepared", report=report)
        manifest_path = os.path.join(backup_dir, "manifest.json")
        snapshot_guard._replace_file(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        try:
            snapshot_guard.replace_files_with_rollback([(html_path, new_bytes)])
        except snapshot_guard.SnapshotConflictError as exc:
            raise RepairError(f"Запись прервана: {exc}") from exc
        with open(html_path, "rb") as source:
            if source.read() != new_bytes:
                raise RepairError("Записанный schedule.html не совпадает с подготовленным.")
        manifest["status"] = "applied"
        snapshot_guard._replace_file(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Однократное обновление встроенного JS schedule.html (по умолчанию dry-run)")
    sub = parser.add_subparsers(dest="command")
    dry = sub.add_parser("dry-run")
    dry.add_argument("--project-root", required=True)
    app = sub.add_parser("apply")
    app.add_argument("--project-root", required=True)
    app.add_argument("--expect-html", required=True)
    app.add_argument("--backup-dir", required=True)
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0].startswith("--"):
        args_list.insert(0, "dry-run")
    args = parser.parse_args(args_list)
    if args.command not in ("dry-run", "apply"):
        parser.print_help()
        return 2
    root = os.path.abspath(args.project_root)
    try:
        if os.path.normcase(root) != os.path.normcase(PROJECT_ROOT):
            raise RepairError(f"Инструмент из {PROJECT_ROOT} обновляет только свою страницу, а не {root}.")
        html_path = get_schedule_html_path(root)
        if args.command == "apply":
            report = apply(html_path, get_schedule_state_dir(root), args.expect_html, args.backup_dir)
        else:
            report = dry_run(html_path)
    except (RepairError, snapshot_guard.SnapshotConflictError, OSError, UnicodeDecodeError) as exc:
        print(f"ОТКАЗ: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.command == "dry-run" and report["changed"]:
        print(f"apply: --project-root {root} --expect-html {report['html_sha256']} --backup-dir <новый каталог>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
