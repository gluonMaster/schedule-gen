# Карта проекта `SchedGen_PreRelease`

Репозиторий объединяет несколько почти независимых подсистем вокруг одного цикла работы с расписанием:

1) **Оптимизация (OR-Tools / CP-SAT)**: входной Excel формата *Plannung* → вычисление расписания → выходной Excel формата *Schedule*
2) **Визуализация**: выходной Excel (*Schedule*) → PDF/HTML/экспорты по учителям и группам
3) **Редактирование в браузере (gear_xls)**: Excel (*Schedule*) → интерактивный HTML (drag&drop) → мультипользовательское редактирование → экспорт обратно в Excel (*Schedule*)
4) **GUI-обвязка**: кнопки, которые запускают пункты 1–3 и вспомогательные операции (включая цикл "newpref")

Ниже — "что где лежит", точки входа и основные контракты данных.

---

## 1) Директории верхнего уровня

### `xlsx_initial/`
Исходные Excel-файлы для оптимизатора.
- `xlsx_initial/schedule_planning.xlsx` — основной вход для оптимизации (лист `Plannung`)
- `xlsx_initial/newpref.xlsx` — альтернативный вход (генерируется из экспортов gear_xls через макрос)

### `gear_xls/`
Генератор интерактивного HTML-расписания, мультипользовательский Flask-сервер и обратный экспорт в Excel.
- Вход: Excel с листом `Schedule` (колонки по позиции A..I, заголовки не критичны для парсера)
- Выход: `gear_xls/html_output/schedule.html` и экспортируемые Excel в `gear_xls/excel_exports/`

Подкаталоги:
- `gear_xls/services/` — "пайплайн" Excel → структура → HTML
- `gear_xls/generators/` — модульная генерация HTML (координатор + генераторы структуры/таблиц/блоков)
- `gear_xls/js_modules/` — JS-модули для интерактивности/экспорта (27 файлов). Добавлены в Phase 6:
  - `menu.js` — hamburger-меню: `initMenu()`, `toggleMenu()`, `closeMenu()`, `handleNewSchedule()`, `openAddColumnDialog()`. Реализует dropdown, фильтр типов занятий, "Опубликовать расписание" (admin), Escape/outside-click, confirmation modal и пересоздание расписания (Villa: 16 кабинетов, Kolibri: 7 кабинетов).
  - `column_delete.js` (212 строк) — удаление колонок: `initColumnDeleteButtons()`, `removeColumn(building, day, colIndex)`. MutationObserver навешивает кнопки "×" на `<th>`; после удаления перемапирует `data-col` и `data-col-index` через `oldIndexToRoom`.
  - `dropdown_widget.js` — переиспользуемый autocomplete-виджет (`createAutocompleteInput`): клавиатурная навигация, подтверждение нового значения, персистентность через `POST /api/spiski/add`.
  Добавлены в Phase 7:
  - `block_content_sync.js` — синхронизация содержимого блока после drag-drop и resize: `syncBlockContent(block)` читает `data-day`/`data-col-index`/`data-start-row`/`data-row-span`, извлекает кабинет из заголовка колонки (`extractRoomFromDayHeader`), вычисляет время из `gridStart + startRow * timeInterval` и перестраивает innerHTML блока в формате 5 строк `subject/teacher/students/room/time`. Экспортируется как `window.syncBlockContent`. Вызывается из `block_drop_service.js`, `block_positioning.js`, `block_resize.js`.
  - `block_resize.js` — вертикальное изменение размера блоков уроков перетаскиванием нижнего края: `initBlockResize()` регистрирует обработчики событий на уровне document (фаза capture для mousedown), `window.isResizing` — геттер активного состояния resize. Зона захвата — нижние 6 px блока (`RESIZE_ZONE_PX`). Координирует с `DragDropService.setPreventDrag()` для предотвращения одновременного drag. Вызывается из `app_initialization.js`.
- `gear_xls/static/` — статические ресурсы мультипользовательского UI (инъектируются сервером в ответ `/schedule`):
  - `auth_ui.js` — ролевое управление UI (admin/editor/viewer), навигационная панель, `SchedGenAuthUI`
  - `lock_ui.js` — баннер блокировки редактирования, heartbeat, принудительный сброс, `SchedGenLockUI`
  - `base_sync_ui.js` — публикация базового расписания, синхронизация ревизий, `SchedGenBaseSyncUI`, `window.publishSchedule`
  - `individual_ui.js` — CRUD индивидуальных занятий через REST API, перехват DOM-событий, `SchedGenIndividualUI`
  - `rooms_report.js` — клиентская часть страницы аудиторий
  - `nav.css` — стили навигационной панели
- `gear_xls/config/` — учётные записи (`users.json` с bcrypt-хэшами) и секрет Flask-сессии (`secret_key.txt`)
- `gear_xls/schedule_state/` — runtime JSON-состояние: блокировка (`lock.json`), базовое расписание (`base_schedule.json`), индивидуальные занятия (`individual_lessons.json`)
- `gear_xls/scripts/` — утилиты администратора: `set_password.py` для обновления паролей в `users.json`
- `gear_xls/html_output/` — генерируемый HTML (артефакт)
- `gear_xls/excel_exports/` — Excel-экспорты из веб-интерфейса (артефакт)
- `gear_xls/pdfs/` — PDF-артефакты (если включены соответствующие шаги)

**Роли пользователей:**
- `admin` — полный доступ: редактирование, публикация базового расписания, экспорт в Excel, принудительный сброс блокировки
- `editor` — может захватить блокировку, создавать/редактировать/удалять индивидуальные и nachhilfe занятия; не может трогать групповые блоки и публиковать
- `viewer` — только просмотр

### `visualiser/`
"Продуктовая" визуализация расписания из Excel в PDF/HTML и пакетные экспорты.
- Вход: `visualiser/optimized_schedule.xlsx` (лист `Schedule` с **англ.** колонками: `subject, group, teacher, room, building, day, start_time, end_time, duration`)
- Выход: `visualiser/enhanced_schedule_visualization.pdf` + `visualiser/enhanced_schedule_visualization.html`
  и подпапки `visualiser/teacher_schedules/`, `visualiser/group_schedules/`

### `visualiserTV/`
Почти тождественный `visualiser/`, но "заточен" под телевизор/экран (PDF с заданными размерами холста).

### `gui_services/`
Сервисные модули для GUI-обвязки (Tkinter) — разнесено по слоям: UI, файлы, процессы, действия, лог.

### `dist/`
Скомпилированный артефакт `ScheduleGenerator.exe` (судя по коду — сборка через PyInstaller; конфиги сборки в репозитории не найдены).

### Прочие "артефактные" директории
- `excel_exports/` (в корне) — сейчас пустая; выглядит как место под выходные экспорты
- `__pycache__/` — кэш Python

---

## 2) Основные точки входа (что запускать)

### GUI "главное окно"
- `gui.py` — основной "редактор/лаунчер" (Tkinter) с кнопками под шаги оптимизации/визуализации/gear_xls/newpref.
  - использует `gui_services/*`

### Оптимизация расписания (OR-Tools)
- `main_sch.py` — CLI для запуска оптимизатора:
  - читает `Plannung` через `reader.py`
  - запускает модель `scheduler_base.py`
  - пишет Excel в `visualiser/optimized_schedule.xlsx` (по умолчанию) через `output_utils.py`

### Web-редактор расписания (HTML)
- `gear_xls/main.py` — GUI для выбора Excel-файла (*Schedule*) и генерации интерактивной HTML-версии (single-user / admin-режим)
- `gear_xls/server_routes.py` — полноценный мультипользовательский Flask-сервер: аутентификация (`/login`, `/logout`), просмотр расписания (`/schedule`), REST API блоков/колонок/блокировки/публикации, аудитории (`/rooms`), экспорт в Excel (только admin). Можно запустить напрямую: `python gear_xls/server_routes.py`
- `start_flask.bat` — батник, запускающий `gear_xls/server_routes.py` (путь внутри батника захардкожен)

### Визуализация в PDF/HTML
- `visualiser/example_usage_enhanced.py` — типовой запуск "enhanced" визуализатора
- `visualiserTV/schedule_visualizer_main.py` / `visualiserTV/example_usage_enhanced.py` — аналогично для TV-варианта

---

## 3) Контракты данных (Excel форматы) — самое важное

### 3.1 Вход оптимизатора: лист `Plannung` (14-строчные секции)
Файл: `xlsx_initial/schedule_planning.xlsx` или `xlsx_initial/newpref.xlsx`
Чтение: `reader.py:ScheduleReader.read_excel()`

Ключевые моменты:
- лист должен называться `Plannung` (поиск по `lower() == "plannung"`)
- каждая "секция занятия" занимает 14 строк
- в секции используются колонки **B/C/D**:
  - `B` — основное занятие; `C/D` — "связанные" занятия (цепочка B→C→D)
- `reader.py` проставляет связи: `linked_classes`, `previous_class`, `next_class`

### 3.2 Выход оптимизатора: лист `Schedule` (табличный формат)
Файл по умолчанию: `visualiser/optimized_schedule.xlsx`
Генерация: `output_utils.export_to_excel()`

Колонки (английские имена):
`subject, group, teacher, room, building, day, start_time, end_time, duration, pause_before, pause_after`

Также создаются листы:
- `T_<teacher>` — по преподавателям
- `G_<group>` — по группам
- `R_<room>` — по кабинетам

### 3.3 Web-редактор: лист `Schedule` (позиционный формат A..I)
Чтение: `gear_xls/excel_parser.py` (берет значения по колонкам, не по именам)

Экспорт из веба:
- `gear_xls/excel_exporter.py` пишет `Schedule` с русскими заголовками ("Занятие", "Группа", …), но порядок колонок соответствует A..I.

Важное следствие:
- `visualiser/` **ожидает английские имена колонок** (см. `visualiser/data_processor.py`), поэтому Excel, экспортированный из `gear_xls`, может не подходить для визуализатора без нормализации заголовков.

### 3.4 Цикл "newpref.xlsx" (возврат к формату `Plannung`)
Идея: из Excel-экспорта web-редактора (*Schedule*) сделать новый вход оптимизатора (*Plannung*).

Реализация:
- `gear_xls/convert_to_xlsm.py` (или аналогичный код в `gui_services/app_actions.py`) конвертирует `.xlsx` → `.xlsm` и добавляет VBA-модуль `gear_xls/Modul1.bas`
- макрос `CreateSchedulePlanning` создает `xlsx_initial/newpref.xlsx` (лист `Plannung`) из листа `Schedule`

---

## 4) "Ядро оптимизатора" (модули в корне)

Ориентир по ответственности:
- `reader.py` — парсинг `Plannung` → `ScheduleClass` (+ построение связей B→C→D)
- `scheduler_base.py` — класс `ScheduleOptimizer`: слоты времени, сбор ресурсов, сборка модели, `solve()`
- `model_variables.py` — создание переменных CP-SAT (день/старт/кабинет), поддержка "временных окон"
- `constraints.py` — агрегатор ограничений (ре-экспорт)
  - `linked_constraints.py` — ограничения для связанных занятий (цепочки)
  - `resource_constraints.py` — конфликты ресурсов (teacher/room/group) + пред-проверки
  - `time_conflict_constraints.py` / `time_constraint_utils.py` — логика "не пересекаться по времени", спец-случаи для окон/фиксированных
- `objective.py` — целевая функция (перемещения/окна) + доп.веса из `timewindow_adapter.py`
- `timewindow_adapter.py` / `sequential_scheduling*.py` — эвристики/адаптеры под временные окна и последовательное размещение
- `output_utils.py` — экспорт решения в Excel

Старые/параллельные визуализаторы (в корне):
- `schedule_visualizer.py` / `visualisation.py` — matplotlib-визуализации (похоже, историческое/вспомогательное)

---

## 5) Как примерно устроен "сквозной" сценарий

1) **Оптимизация**: `main_sch.py` берет `xlsx_initial/schedule_planning.xlsx` → пишет `visualiser/optimized_schedule.xlsx`
2) **Визуализация**: `visualiser/example_usage_enhanced.py` берет `optimized_schedule.xlsx` → делает PDF/HTML/экспорты
3) **Правки**: `gear_xls/main.py` берет Excel с листом `Schedule` → делает интерактивный HTML; `gear_xls/server_routes.py` обслуживает мультипользовательское редактирование и позволяет экспортить правки в новый Excel (только admin)
4) **Возврат в оптимизатор** (опционально): экспорт gear_xls → `.xlsm` + макрос → `xlsx_initial/newpref.xlsx` → снова `main_sch.py`

GUI (`gui.py`) пытается "склеить" это кнопками, но под капотом в основном просто запускает соответствующие скрипты.

---

## 6) Конфиги и "технические" файлы

- `config.json` — настройки автокопирования артефактов визуализации (см. `CONFIG_README.md`)
- `CONFIG_README.md` — описание `config.json`
- `DEPLOYMENT_GUIDE.md` — как переносить `ScheduleGenerator.exe` и нужные папки
- `gear_xls/config/users.json` — учётные записи пользователей web-редактора (bcrypt-хэши паролей)
- `gear_xls/scripts/set_password.py` — CLI-утилита для обновления паролей в `users.json`
