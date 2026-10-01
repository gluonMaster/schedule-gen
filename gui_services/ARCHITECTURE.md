# gui_services — Tkinter GUI Service Layer

## Purpose
Orchestrates all SchedGen subsystems through a Tkinter GUI.
Separates UI construction from business logic using a service-based architecture.

## Entry Point
`gui.py` (project root) → creates main `ApplicationInterface` → delegates everything to `gui_services/`

## Module Responsibilities

| File | Role | Lines |
|------|------|-------|
| `app_actions.py` | **Central business logic controller** | 702 |
| `process_manager.py` | Subprocess launch + monitoring + output capture | 225 |
| `ui_builder.py` | Tkinter component factory | 124 |
| `file_manager.py` | Cross-platform file operations | 74 |
| `logger.py` | Logging to Tkinter Text widget | 28 |
| `__init__.py` | Module exports | 18 |

## AppActions — Central Controller

`app_actions.py` is the most important file. It orchestrates all user actions.

### Constructor
```python
AppActions(process_manager: ProcessManager, log_callback=None)
```
`log_callback` is optional at construction time. `set_log_callback(fn)` binds it later once
the Tkinter log widget exists (avoiding a circular dependency during GUI setup).

### Instance state
| Attribute | Type | Purpose |
|-----------|------|---------|
| `program_directory` | str | Auto-detected project root (set in `__init__`) |
| `selected_xlsx_file` | str \| None | Path chosen via the "step 5" file picker |
| `lesson_type_filter` | str | Filter forwarded to visualiser CLI (`'all'` by default) |

### Action methods (mapped to GUI buttons)

| Method | Button | What it does |
|--------|--------|-------------|
| `select_directory()` | 1 | Opens a directory dialog; sets `program_directory` |
| `run_scheduler()` | 2 | Runs `main_sch.py` in an interactive terminal window |
| `open_optimized_schedule()` | 2.1 | Opens `visualiser/optimized_schedule.xlsx` |
| `run_gear_xls()` | 3 | Starts `gear_xls/main.py` in a new terminal |
| `run_flask_server()` | 3.1 | Writes `start_flask.bat` and launches Flask in a new terminal; guards against double-start |
| `open_web_app()` | 3.2 | Auto-starts Flask if not running, polls `localhost:5000` (5 s timeout), then opens browser |
| `run_visualiser()` | 4 | Runs `example_usage_enhanced.py --lesson-type <filter>`, streams logs to GUI, then copies outputs when enabled |
| `open_pdf_visualization()` | 4.1 | Opens `visualiser/enhanced_schedule_visualization.pdf` |
| `open_html_visualization()` | 4.2 | Opens `visualiser/enhanced_schedule_visualization.html` in browser |
| `select_xlsx_file()` | 5 | File-picker dialog; sets `selected_xlsx_file` |
| `convert_to_xlsm()` | 6 | Runs `convert_to_xlsm.py` in a terminal |
| `open_xlsm_file()` | 6.1 | Opens the `.xlsm` counterpart of `selected_xlsx_file` |
| `open_newpref()` | 7.0 | Creates `newpref.xlsx` via Excel COM, then opens it |
| `run_scheduler_newpref()` | 7 | Full orchestrated pipeline (see below) |

### set_lesson_type_filter()
```python
def set_lesson_type_filter(self, value: str)
```
Stores a lesson-type string (`'all'`, `'lecture'`, etc.) that is appended as
`--lesson-type <value>` to every visualiser invocation (`run_visualiser` and
the step-5 segment of `run_scheduler_newpref`).

## Full Orchestrated Pipeline — run_scheduler_newpref()

Triggered by button 7. Runs entirely in a background daemon thread.

```
Step 1  _find_latest_xlsx_file()
          → scans gear_xls/excel_exports/ for newest .xlsx

Step 2  _convert_xlsx_to_xlsm_with_macro()
          → opens file via Excel COM (win32com + pythoncom)
          → saves as .xlsm (FileFormat=52)
          → imports VBA module from gear_xls/Modul1.bas

Step 3  _run_excel_macro("CreateSchedulePlanning")
          → runs macro inside the .xlsm via Excel COM
          → macro writes xlsx_initial/newpref.xlsx

Step 4  ProcessManager.execute_command_capture()
          → runs main_sch.py with newpref.xlsx
          → stdout/stderr piped back into the GUI log widget line-by-line
          → checks returncode == 0 AND that optimized_schedule.xlsx mtime changed
          → on failure: shows error dialog, pipeline stops

Step 5  ProcessManager.execute_command_capture()
          → runs example_usage_enhanced.py --lesson-type <filter>
          → streams logs to GUI and waits for completion

Step 6  _copy_visualization_files()
          → reads config.json (copy_destination_path, auto_copy_enabled)
          → copies enhanced_schedule_visualization.{html,pdf} to destination
```

If any step fails the pipeline stops immediately and shows an error messagebox.

## Windows COM Automation

`_convert_xlsx_to_xlsm_with_macro()` and `_run_excel_macro()` use:
- `win32com.client.Dispatch("Excel.Application")` — creates a hidden Excel instance
- `pythoncom.CoInitialize()` / `CoUninitialize()` — required for COM in non-main threads
- `VBProject.VBComponents.Import(module_path)` — injects VBA from `Modul1.bas`

These methods are Windows-only and will fail on macOS/Linux.

## Subprocess Architecture

Three subprocess execution modes are used:

```
AppActions
  ├── ProcessManager.execute_in_terminal(cmds, dir)
  │     Opens a visible cmd/Terminal window; user sees output.
  │     Used by: run_scheduler, run_gear_xls, convert_to_xlsm
  │
  ├── ProcessManager.start_new_terminal_with_commands(dir)
  │     Writes start_flask.bat then opens it in a new cmd window.
  │     Used by: run_flask_server
  │
  ├── ProcessManager.execute_command_capture(cmds, dir, log_cb)
  │     Headless Popen with stdout/stderr piped; reader thread feeds
  │     log_cb line-by-line. Returns (process, reader_thread).
  │     Used by: run_visualiser and run_scheduler_newpref steps 4-5
  │
  └── ProcessManager.execute_command_and_wait(cmds, dir)
        Headless Popen, no output capture; caller calls .wait().
        Currently retained for compatibility; not used by AppActions.
```

All long-running operations are dispatched via `threading.Thread(daemon=True)`
so the Tkinter event loop is never blocked.

## UI Structure

```
gui.py (ApplicationInterface)
  ↓
UIBuilder (ui_builder.py)
  constructs:
  ├── Main window + frame
  ├── Info labels (working directory, academic year badge)
  ├── Action buttons (single, double-row, triple-row layouts)
  ├── Log Text widget (receives Logger output)
  └── Status bar
```

All Tkinter widget creation is delegated to `UIBuilder`.
`AppActions` only calls `UIBuilder.build_*()` — never creates widgets directly.

## Logger
`logger.py` — thin wrapper that writes timestamped messages to a Tkinter `Text` widget
and updates the status bar. Not related to Python's `logging` module.
`AppActions` receives it as a plain callable (`log_callback`) rather than a typed reference,
so the Logger can be swapped for a simple `print` fallback during early init.

## File Manager
`file_manager.py` — cross-platform file operations:
- `get_file_path(base, *parts)` — safe `os.path.join` wrapper
- `open_file` / `open_web_file` — OS-aware file/browser open
- `select_directory` / `select_xlsx_file` — Tkinter dialog wrappers
- `check_directory_exists` — existence check

## Configuration (config.json)
`AppActions._load_config()` / `_save_config()` read/write a JSON file in `program_directory`:
```json
{
    "copy_destination_path": "",
    "auto_copy_enabled": false,
    "academic_year": {
        "period": "2025-2026",
        "color": "#2E7D32"
    }
}
```
If the file is absent a default is created automatically. `academic_year` is displayed
in the GUI information panel and appended to the window title.

## Data Flow (GUI perspective)
```
User triggers button 7 → run_scheduler_newpref() (background thread)
  │
  ├─ Excel COM: latest export → .xlsm + VBA macro → newpref.xlsx
  │
  ├─ ProcessManager.execute_command_capture
  │     main_sch.py xlsx_initial/newpref.xlsx
  │       → visualiser/optimized_schedule.xlsx
  │       → log lines streamed to GUI widget
  │
  ├─ ProcessManager.execute_command_capture
  │     example_usage_enhanced.py --lesson-type <filter>
  │       → log lines streamed to GUI widget
  │       → visualiser/enhanced_schedule_visualization.{html,pdf}
  │
  └─ FileManager.copy → configured destination (OneDrive etc.)

Independent actions (buttons 2, 3, 4):
  run_scheduler()   → main_sch.py in interactive terminal
  run_gear_xls()    → gear_xls/main.py in interactive terminal
  run_visualiser()  → example_usage_enhanced.py with GUI logs, then configured copy
```

## Error Handling Pattern
```python
# Inline subprocess result check (run_scheduler_newpref):
scheduler_ok = (returncode == 0) and output_updated
if not scheduler_ok:
    messagebox.showerror("Ошибка оптимизации — изменения не применены", reason)
    return   # pipeline stops; no further steps run

# File operations:
try:
    result = ProcessManager.execute_in_terminal(...)
except FileNotFoundError:
    self.log_action("Executable not found: ...")
```

All errors go through `log_action` → displayed in the GUI text widget.
No silent failures.

## See Also
- `MIGRATION.md` — migration notes from previous architecture
- `README.md` — quick reference for service usage
