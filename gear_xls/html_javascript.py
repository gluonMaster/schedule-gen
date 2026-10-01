"""
Модуль для генерации JavaScript-кода для интерактивной работы с HTML-расписанием.
Использует модульный подход для организации кода.
"""
import os
import json

def get_javascript(cellHeight, dayCellWidth, headerHeight, days_order, time_interval, borderWidth=1, grid_start=9*60, spiski_data=None):
    """
    Возвращает строку с JavaScript-кодом для интерактивности HTML-расписания.

    Args:
        cellHeight (int): Высота ячейки в пикселях
        dayCellWidth (int): Ширина ячейки дня в пикселях
        headerHeight (float): Высота заголовка в пикселях
        days_order (list): Список дней недели
        time_interval (int): Интервал времени в минутах
        borderWidth (int): Толщина границы ячейки в пикселях
        grid_start (int): Начало сетки в минутах (например, 9*60 = 540 для 09:00)

    Returns:
        str: JavaScript-код
    """
    # Путь к директории с JS модулями
    js_dir = os.path.join(os.path.dirname(__file__), 'js_modules')
    
    # Emit the Python day model into JavaScript so runtime modules share one order.
    days_order_json = json.dumps(list(days_order), ensure_ascii=False)

    # Инициализация JavaScript с переменными
    js_variables = f"""
        var gridCellHeight = {cellHeight};
        var dayCellWidth = {dayCellWidth};
        var headerHeight = {headerHeight};
        var daysOrder = {days_order_json};
        window.daysOrder = daysOrder;
        var timeInterval = {time_interval};
        window.timeInterval = timeInterval;
        var borderWidth = {float(borderWidth)};
        var gridStart = {int(grid_start)};
        window.gridStart = gridStart;

        // Глобальные переменные для отслеживания состояния
        window.editDialogOpen = false;
        window.draggedBlock = null;

        // Храним измеренную ширину колонки времени
        var measuredTimeColWidth = 0;
    """

    # Serialize spiski data to JS global.
    # Use json.dumps to safely escape all string values.
    if spiski_data and isinstance(spiski_data, dict):
        _subjects_json  = json.dumps(spiski_data.get('subjects', []),      ensure_ascii=False)
        _groups_json    = json.dumps(spiski_data.get('groups', []),         ensure_ascii=False)
        _teachers_json  = json.dumps(spiski_data.get('teachers', []),       ensure_ascii=False)
        _rooms_v_json   = json.dumps(spiski_data.get('rooms_Villa', []),    ensure_ascii=False)
        _rooms_k_json   = json.dumps(spiski_data.get('rooms_Kolibri', []), ensure_ascii=False)
    else:
        _subjects_json = '[]'
        _groups_json   = '[]'
        _teachers_json = '[]'
        _rooms_v_json  = '[]'
        _rooms_k_json  = '[]'

    js_spiski = (
        f'var spiskiData = {{\n'
        f'    "subjects": {_subjects_json},\n'
        f'    "groups": {_groups_json},\n'
        f'    "teachers": {_teachers_json},\n'
        f'    "rooms_Villa": {_rooms_v_json},\n'
        f'    "rooms_Kolibri": {_rooms_k_json}\n'
        f'}};\n'
        f'window.spiskiData = spiskiData;'
    )
    
    # Список названий модулей для загрузки (обновленный порядок)
    # ВАЖНО: services должны загружаться первыми, так как используются другими модулями
    base_module_names = [
        'services/building_service',      # НОВЫЙ СЕРВИС - загружается первым
        'services/drag_drop_service',     # НОВЫЙ СЕРВИС для drag&drop функциональности
        'services/grid_snap_service',     # НОВЫЙ СЕРВИС для привязки к сетке
        'services/block_drop_service',    # НОВЫЙ СЕРВИС для обработки завершения перетаскивания
        'core',
        'position',
        'drag_drop_refactored',           # Обновленный модуль drag_drop
        'column_helpers',  # Модуль для работы с колонками в разных зданиях
        'column_delete',   # Модуль удаления колонок и кнопок удаления
        'color_utils',     # Модуль для работы с цветами
        'adaptive_text_color',  # Модуль для адаптивного изменения цвета текста
        'export_to_excel', # Модуль для экспорта расписания в Excel
        'menu'             # Модуль меню и создания нового расписания
    ]
    
    # Список названий модулей для добавления блоков
    add_blocks_module_names = [
        'dropdown_widget',          # NEW: must load before block_creation_dialog and editing_update
        'add_blocks_main',
        'block_creation_dialog',
        'block_utils',
        'lesson_type_filter',
        'compact_rows',
        'cell_hover_hint',
        'block_content_sync',   # NEW: must be after column_helpers (extractRoomFromDayHeader, in base_module_names)
        'conflict_detector',    # depends on block_utils
        'block_positioning',    # calls syncBlockContent after positionNewBlock
        'block_event_handlers',
        'quick_add_mode',
        'editing_update',
        'delete_blocks',
        'delete_blocks_observer',
        'block_resize',         # NEW: must be after block_content_sync, position.js, drag_drop_service
        'app_initialization'    # last: calls initBlockResize()
    ]
    
    # Загружаем содержимое модулей
    js_modules = {}
    
    # Загружаем содержимое базовых модулей
    for module_name in base_module_names:
        # Обрабатываем путь для модулей в подпапках (например, services/building_service)
        if '/' in module_name:
            module_path = os.path.join(js_dir, f"{module_name}.js")
        else:
            module_path = os.path.join(js_dir, f"{module_name}.js")
            
        try:
            with open(module_path, 'r', encoding='utf-8') as f:
                js_modules[module_name] = f.read()
                print(f"Loaded JS module: {module_name}")  # Для отладки
        except FileNotFoundError:
            # Если файл не найден, добавляем заглушку с предупреждением
            js_modules[module_name] = f"// ВНИМАНИЕ: Модуль {module_name}.js не найден по пути {module_path}"
            print(f"WARNING: JS module not found: {module_path}")
    
    # Загружаем содержимое модулей добавления блоков
    for module_name in add_blocks_module_names:
        module_path = os.path.join(js_dir, f"{module_name}.js")
        try:
            with open(module_path, 'r', encoding='utf-8') as f:
                js_modules[module_name] = f.read()
                print(f"Loaded JS module: {module_name}")  # Для отладки
        except FileNotFoundError:
            # Если файл не найден, добавляем заглушку
            js_modules[module_name] = f"// ВНИМАНИЕ: Модуль {module_name}.js не найден по пути {module_path}"
            print(f"WARNING: JS module not found: {module_path}")
    
    # Формируем полный JavaScript-код
    full_js = f"""
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            {js_variables}

            // Данные списков (предметы, группы, преподаватели, кабинеты)
            {js_spiski}
              // === НОВЫЕ СЕРВИСЫ ДЛЯ DRAG&DROP ФУНКЦИОНАЛЬНОСТИ ===
            {js_modules.get('services/building_service', '')}
            
            {js_modules.get('services/drag_drop_service', '')}
            
            {js_modules.get('services/grid_snap_service', '')}
            
            {js_modules.get('services/block_drop_service', '')}
            
            // Подключение основных модулей
            {js_modules.get('core', '')}
            
            {js_modules.get('position', '')}
            
            {js_modules.get('drag_drop_refactored', '')}
            
            {js_modules.get('column_helpers', '')}

            {js_modules.get('column_delete', '')}
            
            // Подключение модулей для работы с цветами
            {js_modules.get('color_utils', '')}
            
            {js_modules.get('adaptive_text_color', '')}
            
            // Подключение модуля экспорта в Excel
            {js_modules.get('export_to_excel', '')}

            // Подключение модуля меню и управления колонками
            {js_modules.get('menu', '')}
            
            // Подключение модулей для работы с блоками
            // Виджет автодополнения (загружается первым среди блочных модулей)
            {js_modules.get('dropdown_widget', '')}

            {js_modules.get('add_blocks_main', '')}

            {js_modules.get('block_creation_dialog', '')}

            {js_modules.get('block_utils', '')}

            {js_modules.get('lesson_type_filter', '')}

            {js_modules.get('compact_rows', '')}

            {js_modules.get('cell_hover_hint', '')}

            // Синхронизация текста блока после перемещения
            {js_modules.get('block_content_sync', '')}

            {js_modules.get('conflict_detector', '')}

            {js_modules.get('block_positioning', '')}

            {js_modules.get('block_event_handlers', '')}

            {js_modules.get('quick_add_mode', '')}
            
            // Подключение обновленного модуля редактирования с поддержкой зданий
            {js_modules.get('editing_update', '')}
            
            // Подключение модулей для удаления блоков
            {js_modules.get('delete_blocks', '')}
            
            {js_modules.get('delete_blocks_observer', '')}

            // Вертикальный ресайз блоков
            {js_modules.get('block_resize', '')}

            // Подключение модуля инициализации приложения
            {js_modules.get('app_initialization', '')}
            
            // Инициализация приложения
            initializeApplication();
        }});
    </script>"""
    
    return full_js
