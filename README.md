# ScheduleGen

Schedule planning and editing tools for an educational center: a Python / OR-Tools optimizer, an Excel exchange format, a Flask schedule editor, and printable schedule visualizations.

This repository contains the current development source. It is a Windows-oriented application assembled around a real administrative workflow, not a packaged service or a finished general-purpose scheduling product. The public examples are synthetic; operational workbooks, people, account data, generated schedules and deployment settings are excluded.

## What is implemented

- Timetable optimization with teacher, group and room constraints, linked lessons, fixed starts and time windows.
- Import and export of Excel planning data, including identity and snapshot metadata for editor round trips.
- A browser editor with authentication, roles, edit locks and stale-update checks.
- Individual and tutoring lessons, trial dates, and rental room bookings with separate permissions and conflict rules.
- PDF / HTML visualization, teacher and group schedules, and a Windows desktop control panel.

The editor and optimizer have different responsibilities. Group teaching blocks are generated from planning data; the managed editor supports individual, tutoring, trial and rental records according to the user's role. UI labels and much of the existing module documentation are Russian or German.

## Setup

Use Windows with Python 3.13 or newer, including Tcl/Tk. The production-oriented source targets Python 3.13 syntax. The publication checks used Python 3.14; this is not a compatibility certification for every Python or dependency version.

From the repository directory, in PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The [dependency manifest](requirements.txt) lists direct runtime dependencies inferred from the imports. Versions are not locked. The Excel COM workflows require desktop Microsoft Excel and `pywin32`; reading and writing the synthetic `.xlsx` example uses `openpyxl` without Excel.

Optional raster, calendar and legacy HTML-to-PDF exports use [requirements-export.txt](requirements-export.txt). PDF-to-image conversion additionally needs Poppler; the legacy `pdfkit` route needs wkhtmltopdf. Those external programs are not installed by pip or required for the optimizer example.

## A small synthetic optimizer example

The example generator writes two fictional lessons using the same 14-row `Plannung` sections read by the application. It contains no names or data copied from a working schedule.

```powershell
.\.venv\Scripts\python.exe examples/create_demo_workbook.py
.\.venv\Scripts\python.exe main_sch.py examples/generated/demo_planning.xlsx --output examples/generated/demo_schedule.xlsx --time-limit 10 --time-interval 5
```

The [generator](examples/create_demo_workbook.py) documents the cells in this minimal input format. It covers the optimizer's basic teaching input; the existing exchange tests cover rental and snapshot metadata. It is not a replacement for a complete operational workbook or VBA template.

## Local configuration and editor

Copy [config.example.json](config.example.json) to `config.json` if you need desktop settings. Automatic copying of generated files is disabled in the public defaults. Set an explicit destination before enabling it.

For an isolated editor instance, copy [server.example.json](examples/server.example.json) to `gear_xls/config/server.json` and [users.example.json](examples/users.example.json) to `gear_xls/config/users.json`. Create the directory first. The server example binds only to `127.0.0.1:5055`. The user example contains a disabled account with an empty password hash; it grants no working login until you set a hash locally.

To set the example account's password without placing it in a command argument, run the following in the virtual environment's Python interpreter, from the repository root:

```python
from getpass import getpass
import json
from pathlib import Path
import bcrypt

path = Path("gear_xls/config/users.json")
data = json.loads(path.read_text(encoding="utf-8"))
data["users"][0]["password_hash"] = bcrypt.hashpw(
    getpass("Local demo password: ").encode(), bcrypt.gensalt()
).decode()
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
```

The editor also needs generated schedule HTML and state. Starting `gear_xls/server_routes.py` alone does not provide a populated demo. The desktop entry point is `gui.py`; the existing Excel-to-editor pipeline is documented in [PROJECT_MAP.md](PROJECT_MAP.md). Use a separate local test copy when exploring those workflows. The server writes local state, logs and a generated session key; it is intended for a controlled local workflow, and internet deployment has not been reviewed here.

## Source map

| Area | Entry points |
| --- | --- |
| Optimizer and input | `main_sch.py`, `reader.py`, `scheduler_base.py`, constraint modules |
| Desktop workflow | `gui.py`, `gui_services/`, `server_tray.py` |
| Browser editor / state | `gear_xls/server_routes.py`, `gear_xls/state_manager.py`, `gear_xls/static/`, `gear_xls/js_modules/` |
| Excel exchange | `gear_xls/schedule_exchange.py`, `gear_xls/excel_parser.py`, `gear_xls/excel_exporter.py` |
| Visualization | `visualiser/`, `visualiserTV/` |
| VBA integration source | `xlsx_initial/PlanningMacros.bas`, `gear_xls/Modul1.bas` |

## Checks and limitations

Install `requirements-dev.txt` for the existing Python tests. Run tests in a disposable copy; selected editor tests create synthetic state in temporary directories, but this does not make every legacy script an isolated test.

```powershell
python -m pytest -q tests/test_rental_conflicts_dates.py tests/test_rental_excel_roundtrip.py tests/test_rental_model_editor.py tests/test_rental_operator_sync.py tests/test_schedule_js_refresh.py tests/test_server_log_policy.py
```

The current publication preparation checks the source, synthetic exchange/editor cases and the small optimizer example. It does not certify the full desktop workflow, VBA execution, Excel COM, optional export tools, performance on real schedules, or production deployment. No operational database, workbook, user account, password or server address is included.
