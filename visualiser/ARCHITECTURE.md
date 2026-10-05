# visualiser — PDF/HTML Schedule Visualization

## Purpose
Generates high-quality PDF and HTML visualizations of the optimized schedule.
Produces whole-school view plus per-teacher and per-group exports.

## Entry Points

| File | Purpose |
|------|---------|
| `schedule_visualizer_enhanced.py` | Enhanced visualization — main entry (use this) |
| `schedule_visualizer_main.py` | Basic visualization — legacy entry |
| `example_usage_enhanced.py` | Usage example (47 lines, good reference) |

## Data Pipeline
```
Excel (Schedule sheet, English headers required)
  ↓
data_processor.py  (loads + validates Excel, builds internal data model)
  ↓
config_manager.py  (reads JSON/INI config, sets layout parameters)
  ↓
color_manager.py  (assigns RGB colors per subject/group via HSV)
  ↓
enhanced_layout_manager.py  (calculates positions, dimensions — A3 layout)
  ↓
enhanced_layout_drawing.py  (ReportLab canvas operations)
  ↓
enhanced_layout_rendering.py  (renders individual lesson blocks)
  ↓
enhanced_export_manager.py  (orchestrates all exports)
  ├── PDF output (ReportLab)
  ├── enhanced_export_manager_html.py  → HTML output (492 lines)
  └── enhanced_export_manager_extra.py → PNG, ICS calendar exports
  ↓
group_exporter.py   → per-group PDF/HTML files
teacher_exporter.py → per-teacher PDF/HTML files
```

## Key Modules

| File | Role | Lines |
|------|------|-------|
| `data_processor.py` | Excel loading, validation, internal model | 138 |
| `config_manager.py` | JSON/INI config: layout, colors, paths | 242 |
| `color_manager.py` | RGB/HSV color system for subjects/groups | 147 |
| `enhanced_layout_manager.py` | A3 layout: column widths, row heights, margins | 126 |
| `enhanced_layout_drawing.py` | ReportLab canvas: lines, cells, headers | 163 |
| `enhanced_layout_rendering.py` | Block rendering: text wrapping, colors | 127 |
| `enhanced_export_manager.py` | Export orchestrator: PDF + HTML + extra | 74 |
| `enhanced_export_manager_html.py` | HTML schedule generation | 492 |
| `enhanced_export_manager_extra.py` | PNG export (Pillow) + ICS calendar | 207 |
| `group_exporter.py` | Per-group schedule PDF | 133 |
| `teacher_exporter.py` | Per-teacher schedule PDF | 133 |

## Configuration
Via project-root `config.json`:
```json
{
  "copy_destination_path": "",
  "auto_copy_enabled": true,
  "academic_year": {
    "period": "2025-2026",
    "color": "#2E7D32"
  }
}
```
When `auto_copy_enabled` is true, copies output files to OneDrive automatically.
The `academic_year` section is displayed by the root GUI to distinguish parallel instances.
See the root `README.md` and `config.example.json` for configuration.

## Output Files
All outputs written to `visualiser/`:
- `enhanced_schedule_visualization.pdf` — main A3 schedule (all teachers)
- `enhanced_schedule_visualization.html` — interactive HTML version
- `teacher_schedules/` — per-teacher PDFs and HTML
- `group_schedules/` — per-group PDFs and HTML

## Input Contract
Expects Excel Schedule sheet with **English headers**:
```
subject, group, teacher, room, building, day, start_time, end_time,
duration, pause_before, pause_after
```
Day values: `Mo, Di, Mi, Do, Fr, Sa`

⚠️ gear_xls exports use Russian headers — incompatible without translation.

## Dependencies
- ReportLab (PDF generation — core dependency)
- pandas, openpyxl (Excel I/O)
- Pillow (PNG export, optional)
- icalendar (ICS export, optional)

## vs. visualiserTV/
`visualiserTV/` is adapted for TV/large-display rendering:

| Aspect | visualiser/ | visualiserTV/ |
|--------|-------------|---------------|
| Canvas size | A3 (297×420mm) | 2325×2171px (weekdays) + A4 portrait (weekends) |
| Layout manager | 126 lines | 351 lines — adaptive sizing |
| Drawing | 163 lines | 255 lines — weekday/weekend split |
| Rendering | 127 lines | 169 lines — larger fonts/spacing |

Both subsystems share the same data pipeline and config system.
