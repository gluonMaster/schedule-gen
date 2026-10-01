# gear_xls — Interactive Schedule Editor

## ⚠️ Breaking Changes (Multiuser / Auth layer — new major subsystem)

- **`auth.py` added** — bcrypt-based authentication. `authenticate(login, password)` checks `config/users.json`. `login_required` and `role_required(*roles)` Flask decorators guard all mutating routes. `get_or_create_secret_key()` generates and persists `config/secret_key.txt`. Roles: `admin`, `editor`, `viewer`.
- **`lock_manager.py` added** — optimistic file-based edit lock. Single holder per server instance; 30-minute heartbeat timeout. Operations: `acquire_lock`, `release_lock`, `heartbeat`, `force_release` (admin only). State persisted to `schedule_state/lock.json` via atomic `os.replace`.
- **`state_manager.py` added** — individual lessons CRUD with file locking. Wraps `base_schedule_manager` and exposes `add_block`, `update_block`, `delete_block`, `delete_column_blocks`, `get_base_revision`, `get_individual_revision`, `publish_base`. Persists to `schedule_state/individual_lessons.json`.
- **`base_schedule_manager.py` added** — manages the published "base" (group) schedule. `publish_base(blocks, published_by)` filters to `lesson_type == "group"` and writes to `schedule_state/base_schedule.json` atomically. `base_has_group_lessons_in_column` gates editor column-deletion.
- **`rooms_report.py` added** — computes room availability. `compute_availability()` merges base blocks (from JSON or fallback HTML parse) with individual lessons, derives occupied slots per building/day/room, and returns free windows plus grid bounds.
- **`rooms_routes.py` added** — Flask Blueprint `rooms_routes.bp`. Routes: `GET /rooms` (rooms availability page), `GET /api/rooms/availability`. Configured via `configure(login_required, current_user, rooms_report)`.
- **`server_routes.py` rewritten** — now a full multiuser Flask application. Added: `/login`, `/logout`, `/schedule` (serves HTML with injected auth globals), lock API (`/api/lock/status|acquire|release|heartbeat`, `DELETE /api/lock`), schedule API (`/api/status`, `/api/schedule`, `GET /api/individual_lessons`, `POST /api/schedule/publish`), block CRUD (`/api/blocks`, `/api/blocks/<id>` PUT/DELETE), column CRUD (`/api/columns` POST/DELETE), `/api/spiski/add`. Enforces CSRF same-origin check and JSON 401 for lock/API paths. Registers `rooms_routes.bp`.
- **`config/` directory added** — `users.json` (user accounts with bcrypt hashes), `secret_key.txt` (Flask session key, auto-generated).
- **`schedule_state/` directory added** — runtime state files: `base_schedule.json`, `individual_lessons.json`, `lock.json` (plus `.lock` files for inter-process locking).
- **`static/` directory added** — static assets served at `/static/<filename>`. Contains: `nav.css` (top nav bar), `auth_ui.js` (role-based UI gating, nav injection, `SchedGenAuthUI`), `lock_ui.js` (lock banner, heartbeat, `SchedGenLockUI`), `base_sync_ui.js` (base schedule publish/sync, `SchedGenBaseSyncUI`), `individual_ui.js` (individual lessons CRUD bridging DOM and API, `SchedGenIndividualUI`), `rooms_report.js` (client-side rooms availability table).
- **`scripts/` directory added** — admin utilities. `scripts/set_password.py <login> <password>` hashes and writes a password into `config/users.json`.
- **`requirements.txt` updated** — `bcrypt>=4.0` added.
- **`/schedule` route** — injects `window.CURRENT_USER`, `window.USER_ROLE`, `window.DISPLAY_NAME`, `window.PUBLISHED_BASE_AVAILABLE` and loads `auth_ui.js`, `base_sync_ui.js`, `lock_ui.js`, `individual_ui.js` before `</body>`.
- **`/export_to_excel` now requires `role=admin`** — guarded by `@role_required("admin")`.
- **`export_to_excel.js` updated** — calls `_refreshIndividualBeforeExport()` before collecting schedule data, so individual lesson layer is current before export.
- **`menu.js` updated** — `initMenu()` now adds a lesson-type filter section (Все / Только групповые / Только индивидуальные / Только наххильфе / Негрупповые) and a "Опубликовать расписание" item (visible to admin only, calls `window.publishSchedule()`). `openAddColumnDialog()` added — opens a modal to add a room column with building/day/room selects and room autocomplete from `spiskiData`.
- **`html_structure_generator.py` updated** — `generate_control_panel()` now emits `#menu-publish-item` (hidden by default) and `#menuItemAddColumn` in `#menuDropdown`.
- **`dropdown_widget.js` added** — reusable autocomplete widget (`createAutocompleteInput`). Supports keyboard navigation, blur-triggered "add new item?" confirmation, and fire-and-forget persistence via `POST /api/spiski/add`. Exports: `createAutocompleteInput`, `sortStringListInPlace`, `getRoomListForBuilding`, `addUniqueToList`, `addRoomToBuildingList`, `_persistSpiskiToServer`.

## ⚠️ Breaking Changes (Phase 7 — drag-drop interactivity: block content sync + vertical resize)

- **`block_content_sync.js` added** — new plain-function module. `syncBlockContent(block)` reads `data-day`/`data-col-index`/`data-start-row`/`data-row-span`, derives room from column header via `extractRoomFromDayHeader`, computes time from `gridStart + startRow * timeInterval`, and rebuilds block innerHTML preserving the 5-line structure (subject/teacher/students/room/time). Exported as `window.syncBlockContent`. Must load after `column_helpers` (in `base_module_names`) and before `block_positioning`.
- **`block_resize.js` added** — new module. `initBlockResize()` registers document-level event listeners (mousemove, mouseup; mousedown in capture phase to prevent drag interference). `window.isResizing` getter exposes live resize state. Resize zone is the bottom 6 px of a block (`RESIZE_ZONE_PX = 6`). Uses `DragDropService.setPreventDrag()` to suppress drag during resize. Calls `syncBlockContent` and `ConflictDetector.highlightConflicts()` on mouseup only if the span actually changed. Must load after `block_content_sync` and before `app_initialization`.
- **`html_styles.py` updated (347 → 357 lines)** — two new CSS blocks added: `.activity-block.resizing` (dashed bottom border, opacity 0.85 while resize is active) and `.activity-block[data-resize-hover]` (ns-resize cursor when pointer is within the resize zone).
- **`html_javascript.py` updated** — `block_content_sync` and `block_resize` added to `add_blocks_module_names` in the correct dependency order; both injected in the full JS f-string template with matching comments.
- **`block_drop_service.js` updated** — `syncBlockContent(block)` called after `updateActivityPositions()` in both `processBlockDrop` and `fallbackProcessBlockDrop`, so block text (room + time) reflects new position immediately on drop.
- **`block_positioning.js` updated** — `syncBlockContent(block)` called at end of `positionNewBlock()`, so newly created or repositioned blocks always display correct room and time.
- **`app_initialization.js` updated** — `initBlockResize()` called with `typeof` guard after `initColumnDeleteButtons()`.
- **5-line block innerHTML invariant** — `syncBlockContent` enforces and relies on the structure `subject<br>teacher<br>students<br>room<br>time`. This is the authoritative contract for block content after any positional change.
- **`editing_update.js` intentionally NOT updated** — user-typed room and time values must not be overwritten by `syncBlockContent` on save; the edit flow owns those fields directly.

## ⚠️ Breaking Changes (Phase 6 — hamburger menu + column deletion)

- **`menu.js` added (278 lines)** — new module implementing a hamburger-menu dropdown, a confirmation modal, and a "Create New Schedule" flow. Exports: `initMenu()`, `toggleMenu()`, `closeMenu()`, `handleNewSchedule()`.
- **`column_delete.js` added (212 lines)** — new module implementing column-header delete buttons (hidden by default, visible on `<th>:hover`) and the column-removal logic. Exports: `initColumnDeleteButtons()`, `removeColumn(building, day, colIndex)`. Uses a `MutationObserver` to attach buttons to newly-added headers.
- **`generate_control_panel()` updated** — `html_structure_generator.py` now renders `#menuButton` (hamburger) as the first child of `.sticky-buttons`, immediately followed by `#menuDropdown` with a "Новое расписание" item.
- **`html_styles.py` updated (205 → 347 lines)** — five new CSS blocks added: `#menuButton`, `#menuDropdown`, `.col-delete-btn` (with `::before { content: '×' }`), `.menu-modal-overlay`, and nested `.menu-modal` sub-elements.
- **`app_initialization.js` updated** — `initMenu()` and `initColumnDeleteButtons()` called (with `typeof` guards) after `initExcelExport()`.
- **`html_javascript.py` updated** — `column_delete` registered in `base_module_names` after `column_helpers`; `menu` registered after `export_to_excel`. Both injected in the full JS template in dependency order.
- **z-index hierarchy** (full stack, lowest to highest):
  - `.time-cell` sticky column: 3
  - `thead th` sticky header: 4
  - `.col-delete-btn` in header: 5
  - `.sticky-buttons` toolbar: 9999
  - `#menuDropdown`: 10001
  - `.menu-modal-overlay` confirmation modal: 10100
  - notification toast: 10200

## ⚠️ Breaking Changes (Phase 5 — cell-anchor positioning refactor)

- **`settings_panel.js` removed** — the compensation settings panel (gear icon, bottom-right corner) has been deleted entirely. No compensation system remains.
- **Compensation system fully removed** — `horizontalCompensation`, `compensationK`, `compensationB`, and all `Math.pow` compensation formulas are gone. `data-original-top` and `data-compensated` attributes are no longer set; any legacy occurrences are stripped with `removeAttribute`.
- **`position.js` rewritten** — `updateActivityPositions()` now positions blocks by calling `getBoundingClientRect()` on anchor cells (`td[data-row][data-col]`) instead of summing `<th>` widths. Two new backward-compat helpers added: `deriveStartRowFromBlock()` and `deriveRowSpanFromBlock()`.
- **New block data attributes** — every `.activity-block` div now carries `data-start-row` and `data-row-span`. These are emitted by `html_block_generator.py` at generation time and kept up-to-date by all drag/drop/add/resize code paths.
- **`gridStart` JS global added** — `html_javascript.py` now accepts a `grid_start` parameter and emits `var gridStart = N;` (minutes since midnight) before all module code. Propagation chain: `html_coordinator.py → html_structure_generator.py → html_javascript.py`.

---

## Purpose
Web-based drag-and-drop schedule editor. Multiuser: authenticated users view or edit the schedule in a browser. Admins publish a base (group) schedule; editors manage individual lessons. Changes are exported back to Excel.

## Entry Points
- `gear_xls/main.py` — Tkinter file selector dialog → launches Flask server → opens browser (single-user / admin mode)
- `gear_xls/server_routes.py` — Flask application; can be run standalone (`python server_routes.py`) for multiuser server mode

## Authentication Model

```
/login  →  authenticate(login, password)  [auth.py, config/users.json]
  ↓
Flask session (login, display_name, role)
  ↓
login_required decorator  →  all protected routes
role_required("admin")    →  /export_to_excel, /api/schedule/publish, DELETE /api/lock
role_required("admin","editor","organizer") → lock acquisition and non-group editing flows
```

Roles:
- `viewer` — read-only; cannot acquire lock, cannot edit
- `organizer` — can acquire lock, manage only `trial`, add columns, delete only empty or trial-only columns
- `editor` — can acquire lock, manage `individual`/`nachhilfe`/`trial`, add columns, delete columns without group blocks; cannot publish
- `admin` — full access including publish, force-release lock, Excel export

## Edit-Lock Model

Only one user may edit at a time. The lock is file-backed (`schedule_state/lock.json`).

```
POST /api/lock/acquire  →  lock_manager.acquire_lock(login)
  ↓ heartbeat every 60s via lock_ui.js
POST /api/lock/heartbeat
  ↓ auto-expires after 30 min without heartbeat
POST /api/lock/release  →  lock_manager.release_lock(login, version)
DELETE /api/lock         →  lock_manager.force_release(login)  [admin only]
```

## Data Pipeline
```
Excel (Schedule sheet, English headers)
  ↓
excel_parser.py  (ScheduleExcelParser)
  reads columns A-I: subject, group, teacher, room, building, day, start_time, end_time, duration
  ↓
schedule_structure.py  (ScheduleStructure)
  hierarchical model: days → teachers → lessons
  ↓
services/schedule_pipeline.py  (pipeline orchestration)
  ↓
html_generator.py  → generators/html_coordinator.py
  ├── html_structure_generator.py  (document skeleton, CSS includes)
  │     calls get_javascript(..., grid_start=N) → emits var gridStart = N
  ├── html_table_generator.py      (time grid, day columns, row labels)
  │     emits td[data-row][data-col] on every grid cell
  └── html_block_generator.py      (lesson block elements with data-start-row, data-row-span)
  ↓
HTML file written to html_output/schedule.html
  ↓
/schedule route (server_routes.py)
  injects window.CURRENT_USER/USER_ROLE/DISPLAY_NAME/PUBLISHED_BASE_AVAILABLE
  appends auth_ui.js, base_sync_ui.js, lock_ui.js, individual_ui.js
  ↓
  [User edits: drag, resize, add, delete blocks, delete/add columns, create new schedule]
  [Individual lessons: synced via /api/schedule ↔ state_manager ↔ schedule_state/]
  [Base schedule: published via POST /api/schedule/publish, rendered by base_sync_ui.js]
  ↓
POST /export_to_excel  (admin only)
  ↓
excel_exporter.py  (ScheduleExcelExporter)
  ↓
Excel (Schedule sheet, ⚠️ Russian headers — see Critical Issue)
```

## Key Modules

| File | Role | Lines |
|------|------|-------|
| `main.py` | Entry: Tkinter file picker, server startup | 250 |
| `integration.py` | High-level: file load → HTML → server | 285 |
| `excel_parser.py` | Reads Schedule sheet (positional cols A–I) | 189 |
| `schedule_structure.py` | Hierarchical schedule data model | 169 |
| `html_generator.py` | HTML generation facade | 313 |
| `html_styles.py` | CSS generation; includes menu, col-delete, modal, and resize styles | 357 |
| `html_javascript.py` | JS module orchestration/injection; accepts `grid_start` param, emits `var gridStart = N`; loads `column_delete`, `menu`, `block_content_sync`, and `block_resize` modules | 198 |
| `server_routes.py` | Flask multiuser application; auth, lock, schedule, block CRUD, rooms, spiski routes | ~655 |
| `auth.py` | bcrypt auth, `login_required`/`role_required` decorators, session key management | 102 |
| `lock_manager.py` | File-backed edit lock; acquire/release/heartbeat/force_release | 170 |
| `state_manager.py` | Individual lessons CRUD + base schedule façade | ~226 |
| `base_schedule_manager.py` | Published base schedule persistence; atomic JSON writes | 156 |
| `rooms_report.py` | Room availability computation; merges base + individual blocks | 191 |
| `rooms_routes.py` | Flask Blueprint: `/rooms` page + `/api/rooms/availability` | 121 |
| `excel_exporter.py` | Writes edited schedule back to Excel | 284 |
| `convert_to_xlsm.py` | Converts .xlsx → .xlsm + injects VBA macro | 167 |
| `utils.py` | Shared utilities | 301 |

### generators/ (modular HTML generation)
| File | Role | Lines |
|------|------|-------|
| `html_coordinator.py` | Orchestrates all generators; determines `grid_start`/`grid_end` from building data | 274 |
| `html_structure_generator.py` | Document structure, meta, script tags; `generate_control_panel()` renders `#menuButton` + `#menuDropdown` (with "Новое расписание", "Добавить колонку", "Опубликовать расписание" items); passes `grid_start` to `get_javascript()` | 214 |
| `html_table_generator.py` | Time grid, day headers, row structure; emits `td[data-row][data-col]` on every cell | 236 |
| `html_block_generator.py` | Lesson block `<div>` elements; emits `data-start-row` and `data-row-span` on every block | 361 |

### services/ (Python)
| File | Role | Lines |
|------|------|-------|
| `schedule_pipeline.py` | Excel → Structure → HTML pipeline | 174 |
| `color_service.py` | Color assignment per subject/group | 378 |

### config/
| File | Role |
|------|------|
| `config/users.json` | User accounts: `login`, `display_name`, `role`, `password_hash` (bcrypt) |
| `config/secret_key.txt` | Flask session secret key (auto-generated on first run) |

### schedule_state/
| File | Role |
|------|------|
| `schedule_state/base_schedule.json` | Published base (group) schedule: `published_at`, `published_by`, `blocks[]` |
| `schedule_state/individual_lessons.json` | Individual/nachhilfe blocks: `last_modified`, `blocks[]` with `id` (UUID) |
| `schedule_state/lock.json` | Edit lock state: `holder`, `version`, `acquired_at`, `last_heartbeat`, etc. |

### scripts/
| File | Role |
|------|------|
| `scripts/set_password.py` | CLI admin tool: hashes a new password and writes it to `config/users.json` |

### static/ (served at `/static/<filename>`)
| File | Role |
|------|------|
| `static/nav.css` | Top navigation bar styles (`#schedgen-nav`) |
| `static/auth_ui.js` | Role-based UI gating, nav bar injection, `SchedGenAuthUI` object, editor event guards, read-only block info modal |
| `static/lock_ui.js` | Lock banner (`#schedgen-lock-banner`), acquire/release/heartbeat, forced-release handling, `SchedGenLockUI` object |
| `static/base_sync_ui.js` | Base schedule publish (`window.publishSchedule`), revision polling, DOM rendering of base blocks, `SchedGenBaseSyncUI` object |
| `static/individual_ui.js` | Individual lessons CRUD via API, DOM intercept of create/edit/delete/column events, `SchedGenIndividualUI` object, `window.refreshIndividualLayer` |
| `static/rooms_report.js` | Client-side rooms availability table rendering; fetches `/api/rooms/availability` |

## JavaScript Modules (js_modules/, 27 files)

### Root modules
| File | Role |
|------|------|
| `core.js` | App state, globals (`toggleDay` calls `updateActivityPositions` after show/hide) |
| `position.js` | **Cell-anchor positioning**: `updateActivityPositions()` uses `getBoundingClientRect()` on `td[data-row][data-col]` anchor cells; backward-compat helpers `deriveStartRowFromBlock()` and `deriveRowSpanFromBlock()` |
| `drag_drop_refactored.js` | Top-level drag-and-drop controller |
| `block_positioning.js` | `positionNewBlock()` sets `data-start-row`/`data-row-span`, calls `updateActivityPositions()`, then calls `syncBlockContent(block)` to update room/time text; strips any legacy `data-original-top`/`data-compensated` attributes |
| `block_content_sync.js` | **NEW (Phase 7)** Shared utility — `syncBlockContent(block)` reads `data-day`/`data-col-index`/`data-start-row`/`data-row-span`, derives room from column header via `extractRoomFromDayHeader`, computes `HH:MM-HH:MM` time from `gridStart + startRow * timeInterval`, and rebuilds block innerHTML as `subject<br>teacher<br>students<br>room<br>time` (5-line invariant). Falls back gracefully (keeps old text) if column header or grid data is unavailable. Exported as `window.syncBlockContent`. |
| `block_resize.js` | **NEW (Phase 7)** Vertical resize of lesson blocks by dragging the bottom edge. `initBlockResize()` registers three document-level handlers (mousemove, mouseup, mousedown in capture phase). `window.isResizing` is a read-only getter. Resize zone: bottom 6 px (`RESIZE_ZONE_PX`). Clamping: minimum rowSpan = 1; maximum: `startRow + rowSpan <= maxRow`. On mouseup: calls `syncBlockContent` and `ConflictDetector.highlightConflicts()` only if span changed. Coordinates with `DragDropService.setPreventDrag()` to prevent simultaneous drag. |
| `block_event_handlers.js` | Click, double-click handlers |
| `block_utils.js` | Block data extraction |
| `block_creation_dialog.js` | Dialog for new lesson creation |
| `add_blocks_main.js` | UI for adding new lessons |
| `quick_add_mode.js` | Rapid lesson entry mode |
| `editing_update.js` | Edit-in-place updates. **Does NOT call `syncBlockContent`** — user-typed room/time must not be overwritten on save. |
| `delete_blocks.js` | Block deletion logic |
| `delete_blocks_observer.js` | MutationObserver for deletion tracking |
| `save_export.js` | Save state, trigger export |
| `export_to_excel.js` | Client-side Excel export; calls `_refreshIndividualBeforeExport()` before collecting data; primary time source is block text; fallback uses `gridStart + startRow * timeInterval` from `data-start-row`/`data-row-span` |
| `dropdown_widget.js` | **NEW** Reusable autocomplete-dropdown widget (`createAutocompleteInput`); supports custom-value confirmation and server persistence via `/api/spiski/add`. Exports: `createAutocompleteInput`, `sortStringListInPlace`, `getRoomListForBuilding`, `addUniqueToList`, `addRoomToBuildingList`, `_persistSpiskiToServer`. |
| `column_helpers.js` | Column management across multiple buildings; provides `extractRoomFromDayHeader()` used by `block_content_sync.js` |
| `column_delete.js` | **NEW (Phase 6)** Column-header delete buttons and removal logic. `initColumnDeleteButtons()` attaches `.col-delete-btn` buttons to all existing `<th>` elements and uses a `MutationObserver` to attach them to newly-added headers. `removeColumn(building, day, colIndex)` removes the column `<th>` and all matching `<td>` cells, remaps `data-col` and `data-col-index` on surviving elements using a pre-removal `oldIndexToRoom` map, updates container width, and calls `updateActivityPositions()`. The "×" symbol is rendered via CSS `::before`, not as a DOM text node, to avoid corrupting `extractRoomFromDayHeader()` parsing. |
| `conflict_detector.js` | Detects and highlights scheduling conflicts |
| `color_utils.js` | Color manipulation |
| `adaptive_text_color.js` | Contrast-aware text color |
| `menu.js` | **NEW (Phase 6, extended in multiuser)** Hamburger menu dropdown and schedule management. `initMenu()` registers outside-click and Escape handlers (idempotent via `_menuInitialized` flag) and injects lesson-type filter items and "Опубликовать расписание" (admin-only). `toggleMenu()` / `closeMenu()` operate on `#menuDropdown`. `handleNewSchedule()` shows a confirmation before calling `_doCreateNewSchedule()`. `openAddColumnDialog(prefillBuilding?, prefillDay?)` opens a modal with room autocomplete. Room config constants: `BUILDING_ROOMS = { Villa: [...16 rooms], Kolibri: [...7 rooms] }`. |
| `app_initialization.js` | Bootstrap on page load; calls `initMenu()`, `initColumnDeleteButtons()`, and `initBlockResize()` (all with `typeof` guards) after `initExcelExport()` |

### services/ sub-modules
| File | Role |
|------|------|
| `services/building_service.js` | Building/room management |
| `services/drag_drop_service.js` | Drag-and-drop of lesson blocks; exposes `DragDropService.setPreventDrag(bool)` and `DragDropService.isDragging()` used by `block_resize.js` |
| `services/grid_snap_service.js` | Snapping to time grid; `snapToClosestCell()` sets `data-start-row` during drag |
| `services/block_drop_service.js` | Drop target logic, collision detection; `updateBlockPositionData()` sets `data-start-row` on drop, strips `data-original-top`/`data-compensated`; calls `syncBlockContent(block)` after `updateActivityPositions()` in both `processBlockDrop` and `fallbackProcessBlockDrop` |

## JS Module Load Order

Modules are concatenated inside a single `DOMContentLoaded` listener. The order enforced by `html_javascript.py` is:

```
services/building_service  → services/drag_drop_service  → services/grid_snap_service
  → services/block_drop_service  → core  → position  → drag_drop_refactored
  → column_helpers  → column_delete  → save_export  → color_utils
  → adaptive_text_color  → export_to_excel  → dropdown_widget  → menu
  → add_blocks_main  → block_creation_dialog  → block_utils
  → block_content_sync  → conflict_detector  → block_positioning
  → block_event_handlers  → quick_add_mode  → editing_update
  → delete_blocks  → delete_blocks_observer
  → block_resize  → app_initialization
  → initializeApplication()
```

Load order constraints:
- `column_delete` must load before `menu` because `_doCreateNewSchedule()` in `menu.js` triggers a full table rebuild which fires the `MutationObserver` registered by `initColumnDeleteButtons()`.
- `dropdown_widget` must load before `menu` (menu's `openAddColumnDialog` calls `createAutocompleteInput`) and before `block_creation_dialog` and `editing_update`.
- `block_content_sync` must load after `column_helpers` (provides `extractRoomFromDayHeader`) and before `block_positioning` (which calls `syncBlockContent`).
- `block_resize` must load after `block_content_sync` (calls `syncBlockContent` on mouseup), `position.js` (calls `updateActivityPositions`), and `services/drag_drop_service` (calls `DragDropService.setPreventDrag`); must load before `app_initialization` (calls `initBlockResize`).

## Static Assets Load Order

Injected by `/schedule` route into the served HTML (after `</body>`):
```
static/auth_ui.js          (SchedGenAuthUI — must load first)
  → static/base_sync_ui.js  (SchedGenBaseSyncUI — depends on SchedGenAuthUI)
  → static/lock_ui.js       (SchedGenLockUI — depends on SchedGenAuthUI, SchedGenBaseSyncUI)
  → static/individual_ui.js (SchedGenIndividualUI — depends on all three above)
```

`static/nav.css` is injected into `<head>` (before `</head>`).
`static/auth_ui.js` and `static/rooms_report.js` are referenced from `rooms_routes.py` template directly.

## JS Globals

The following variables are emitted by `html_javascript.py` inside `DOMContentLoaded` before any module code runs:

| Variable | Type | Source | Description |
|----------|------|--------|-------------|
| `gridCellHeight` | number | `html_javascript.py` | Height of one time-grid cell in pixels |
| `dayCellWidth` | number | `html_javascript.py` | Width of one day column in pixels |
| `headerHeight` | number | `html_javascript.py` | Height of the table header in pixels |
| `daysOrder` | array | `html_javascript.py` | Ordered list of active day codes |
| `timeInterval` | number | `html_javascript.py` | Minutes per grid row |
| `borderWidth` | number | `html_javascript.py` | Cell border width in pixels |
| `gridStart` | number | `html_javascript.py` (via `grid_start` param) | Grid start time in minutes since midnight (e.g. 540 = 09:00) |
| `measuredTimeColWidth` | number | `html_javascript.py` | Measured width of time column (set at runtime) |
| `editDialogOpen` | boolean | `html_javascript.py` | Global dialog state guard |
| `draggedBlock` | element\|null | `html_javascript.py` | Currently dragged block reference |
| `spiskiData` | object | `html_javascript.py` | Autocomplete lists: `subjects`, `groups`, `teachers`, `rooms_Villa`, `rooms_Kolibri` |

Injected by `/schedule` route (not from `html_javascript.py`):

| Variable | Type | Description |
|----------|------|-------------|
| `window.CURRENT_USER` | string | Login of the authenticated user |
| `window.USER_ROLE` | string | `"admin"`, `"editor"`, or `"viewer"` |
| `window.DISPLAY_NAME` | string | Human-readable display name |
| `window.PUBLISHED_BASE_AVAILABLE` | boolean | Whether a published base schedule exists |

`gridStart` propagation chain:
```
html_coordinator.py._determine_grid_bounds()
  → grid_start value
  → html_coordinator.py.generate_complete_schedule()
  → html_structure_generator.py.generate_document_head(grid_start=N)
  → html_javascript.py.get_javascript(..., grid_start=N)
  → emits: var gridStart = N;
```

## Block Data Attributes

Every `.activity-block` div carries the following data attributes. All are set at generation time by `html_block_generator.py` and kept current by JS on every drag, drop, add, or resize operation.

| Attribute | Set by (Python) | Kept current by (JS) | Meaning |
|-----------|-----------------|----------------------|---------|
| `data-day` | `html_block_generator.py` | drag/drop services, `editing_update.js` | Day code (e.g. `Mo`) |
| `data-col-index` | `html_block_generator.py` | `block_drop_service.js`, `grid_snap_service.js`, `column_delete.js` (remap after deletion) | 0-based column index within the day |
| `data-building` | `html_block_generator.py` | — | Building identifier |
| `data-start-row` | `html_block_generator.py` | `block_positioning.js`, `block_drop_service.js`, `grid_snap_service.js`, `position.js` (backward-compat fallback) | 0-based row index from `gridStart` (= `(startMinutes - gridStart) / timeInterval`) |
| `data-row-span` | `html_block_generator.py` | `block_positioning.js`, `block_resize.js`, `position.js` (backward-compat fallback) | Number of grid rows spanned (= `durationMinutes / timeInterval`) |
| `data-lesson-type` | `html_block_generator.py`, `base_sync_ui.js`, `individual_ui.js` | — | `"group"`, `"individual"`, or `"nachhilfe"` |
| `data-block-id` | `individual_ui.js` (server-assigned UUID) | — | Present only on individual/nachhilfe blocks; used for API CRUD |

`data-start-row` and `data-row-span` are the single source of truth for `updateActivityPositions()`. If either is absent on a legacy HTML file, `deriveStartRowFromBlock()` / `deriveRowSpanFromBlock()` compute the values from the block's time text and write them back.

## Block innerHTML Invariant (Phase 7)

Every `.activity-block` must contain exactly 5 `<br>`-separated lines:

```
subject<br>teacher<br>students<br>room<br>time
```

Where `time` is formatted as `HH:MM-HH:MM`. This structure is:
- **Written** by `html_block_generator.py` at generation time and by `createNewBlock()` in `block_positioning.js`.
- **Written** by `base_sync_ui.js` `renderBaseBlock()` and `individual_ui.js` `renderIndividualBlock()` when rendering server-side blocks.
- **Enforced** by `syncBlockContent(block)` after every drag/drop and after `positionNewBlock()`.
- **Read** by `export_to_excel.js` (primary time/room source for Excel export).
- **Preserved** by `editing_update.js` (user edits overwrite individual lines in-place without going through `syncBlockContent`).

## Positioning Architecture (Phase 5)

`updateActivityPositions()` in `position.js` uses a cell-anchor approach:

1. For each `.activity-block`, read `data-start-row`, `data-row-span`, `data-day`, `data-col-index`.
2. Query the anchor cell: `td.day-{day}[data-col="{col}"][data-row="{startRow}"]`.
3. Call `getBoundingClientRect()` on the anchor cell and on the end-boundary cell (`data-row = startRow + rowSpan`).
4. Convert viewport-relative coordinates to container-relative (accounting for scroll, border).
5. Set `block.style.left/top/width/height` directly.

This replaces the previous approach of summing `<th>` widths and applying polynomial compensation formulas. No compensation constants (`compensationK`, `compensationB`) exist in the codebase.

## Resize Architecture (Phase 7)

`block_resize.js` uses document-level event delegation:

1. `mousemove` — when not resizing: sets/clears `data-resize-hover` attribute on the block under the cursor if the pointer is within `RESIZE_ZONE_PX` (6 px) of its bottom edge. Suppressed if `DragDropService.isDragging()` is true.
2. `mousedown` (capture phase) — if pointer is in resize zone: records `resizeStartY`, `resizeOrigSpan`, `resizeStartRow`; sets `isResizing = true`; adds `.resizing` CSS class; calls `DragDropService.setPreventDrag(true)`. `stopPropagation()` + `preventDefault()` prevent the drag handler from seeing this event.
3. `mouseup` — if `isResizing`: removes `.resizing` class; if span changed, calls `syncBlockContent` and `ConflictDetector.highlightConflicts()`; calls `DragDropService.setPreventDrag(false)`; resets state.

## UI Layout — Control Panel

`.sticky-buttons` (fixed toolbar, z-index 9999) child order:
1. `#menuButton` — hamburger `&#9776; Меню` button; `onclick="toggleMenu()"`
2. `#menuDropdown` — dropdown panel (z-index 10001); items:
   - `.menu-item#menuItemNewSchedule` → `handleNewSchedule()`
   - `.menu-item#menuItemAddColumn` → `openAddColumnDialog()`
   - `.menu-item#menu-publish-item` → `publishSchedule()` (hidden for non-admin; shown by `base_sync_ui.js`)
   - lesson-type filter separator + items (injected by `initMenu()`)
3. Six `.toggle-day-button` elements (Mo–Sa)
4. `#saveIntermediate`, `#saveSchedule`, `#exportToExcel` buttons
5. `#csrf_token` hidden input

## CSS Classes — Phase 6 and Phase 7

| Selector | Purpose | z-index |
|----------|---------|---------|
| `#menuButton` | Hamburger menu trigger, grey background | — (in sticky-buttons at 9999) |
| `#menuDropdown` | Dropdown panel, `display:none` / `.open → display:block` | 10001 |
| `.menu-item` | Individual dropdown items with hover highlight | — |
| `.col-delete-btn` | Absolute-positioned delete button inside `<th>`, hidden by default, shown on `th:hover` | 5 |
| `.col-delete-btn::before` | Renders `×` symbol via CSS content property (avoids polluting header text) | — |
| `.menu-modal-overlay` | Full-screen semi-transparent backdrop for confirmation modal, `display:none` / `.open → display:flex` | 10100 |
| `.menu-modal` | White card inside overlay, contains confirm/cancel buttons | — |
| `.activity-block.resizing` | Dashed bottom border (`2px dashed #1976d2`), opacity 0.85, applied while resize drag is active | — |
| `.activity-block[data-resize-hover]` | `cursor: ns-resize` when pointer is near the bottom resize zone | — |

## Flask API Routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET/POST | `/login` | — | Login form |
| POST | `/logout` | session | Clear session, redirect to `/login` |
| GET | `/schedule` | `login_required` | Serve schedule HTML with injected auth globals |
| GET | `/rooms` | `login_required` | Room availability page |
| GET | `/api/rooms/availability` | `login_required` | JSON room availability data |
| GET | `/api/lock/status` | `login_required` | Current lock state |
| POST | `/api/lock/acquire` | `admin`/`editor` | Acquire edit lock |
| POST | `/api/lock/release` | `login_required` | Release own lock (requires `version`) |
| POST | `/api/lock/heartbeat` | `login_required` | Refresh heartbeat timestamp |
| DELETE | `/api/lock` | `admin` | Force-release any holder's lock |
| GET | `/api/status` | `login_required` | Lock + base/individual revision summary |
| GET | `/api/schedule` | `login_required` | Base blocks + individual blocks + revisions |
| POST | `/api/schedule/publish` | `admin` | Publish base schedule (filters to `lesson_type=group`) |
| GET | `/api/individual_lessons` | `login_required` | Current individual lesson state |
| POST | `/api/blocks` | `admin`/`editor`/`organizer` + lock | Create non-group block; organizer is limited to `trial` |
| PUT | `/api/blocks/<id>` | `admin`/`editor`/`organizer` + lock | Update non-group block; organizer is limited to `trial` |
| DELETE | `/api/blocks/<id>` | `admin`/`editor`/`organizer` + lock | Delete non-group block; organizer is limited to `trial` |
| POST | `/api/columns` | `admin`/`editor`/`organizer` + lock | Register column add (returns ok) |
| DELETE | `/api/columns` | `admin`/`editor`/`organizer` + lock | Delete column blocks; editor blocked by group lessons, organizer blocked by any non-trial content |
| POST | `/api/spiski/add` | `login_required` | Append item to a spiski file; natural-sort preserved |
| POST | `/export_to_excel` | `admin` | Export schedule to Excel file |
| POST | `/save_intermediate` | `admin` | Save intermediate HTML via Tkinter save dialog |

## CSRF Protection

All mutating requests (`POST`, `PUT`, `DELETE`, `PATCH`) except `/login` are checked for `Origin` header matching the server's own scheme+host. Requests without an `Origin` header (same-origin `sendBeacon` / form submit) are allowed through. Cross-origin requests receive HTTP 403 `{"error":"Forbidden","code":"CSRF_FAILED"}`.

## ⚠️ Critical Contract Issue

| Direction | Headers |
|-----------|---------|
| **Input** (from Schedule sheet) | **English**: `subject, group, teacher, room, building, day, start_time, end_time, duration, pause_before, pause_after` |
| **Output** (exported back to Excel) | **Russian**: uses Russian column names |

This incompatibility means gear_xls exports cannot be directly fed into `visualiser/` without header translation.
**Do not silently "fix" this** — it may affect downstream processing. See PROJECT_MAP.md for full context.

## Dependencies
- Flask, flask-cors (web server)
- bcrypt (password hashing)
- pandas, openpyxl (Excel I/O)
- pdfkit (HTML → PDF, requires wkhtmltopdf installed separately)
- win32com (VBA macro injection — Windows only)
- webbrowser (standard library, opens browser)

## Artifacts
- `gear_xls/html_output/` — generated HTML files (gitignored)
- `gear_xls/excel_exports/` — exported Excel files (gitignored)
- `gear_xls/pdfs/` — generated PDFs (gitignored)
- `gear_xls/schedule_state/` — runtime JSON state (lock, base schedule, individual lessons)
- `gear_xls/config/` — user accounts and secret key (should not be committed to public repos)
- `gear_xls/Modul1.bas` — VBA macro source for Plannung generation
