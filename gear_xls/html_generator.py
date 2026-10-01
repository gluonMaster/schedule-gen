#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для генерации HTML-версии расписания с интерактивными возможностями.
РЕФАКТОРИНГ: Теперь является тонкой оберткой для новых специализированных генераторов.

Основная логика вынесена в пакет generators/:
- html_structure_generator - HTML структура документа
- html_table_generator - генерация таблиц расписания  
- html_block_generator - генерация блоков активностей
- html_coordinator - координация всех генераторов
"""

import os
import logging

# NOTE: Импорты генераторов сделаны отложенными для избежания циклических зависимостей

# Импортируем сервис цветов для обратной совместимости
try:
    from services.color_service import ColorService
except ImportError:
    # Fallback если ColorService недоступен
    ColorService = None

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('html_generator')


def generate_html_schedule(buildings, output_html="schedule.html", output_css="schedule.css", 
                          time_interval=5, borderWidth=0.5, spiski_data=None):
    """
    Генерирует HTML-страницу с интерактивным расписанием.
    
    РЕФАКТОРИНГ: Функция теперь является тонкой оберткой для HTMLCoordinator.
    Сохранена полная обратная совместимость с предыдущей версией.
    
    Args:
        buildings (dict): Структура расписания по зданиям
        output_html (str): Путь для сохранения HTML-файла
        output_css (str): Путь для сохранения CSS-файла (совместимость)
        time_interval (int): Интервал времени в минутах для отображения в сетке
        borderWidth (float): Толщина границы ячейки в пикселях
        
    Returns:
        str: Путь к созданному HTML файлу
    """
    logger.info(f"Генерация HTML-расписания через HTMLCoordinator: {output_html}")
    logger.info(f"Параметры: interval={time_interval}мин, border={borderWidth}px")
    
    try:
        # Валидация параметров
        if not validate_html_generation_params(buildings, time_interval, borderWidth):
            raise ValueError("Некорректные параметры генерации HTML")
        
        # Отложенный импорт координатора для избежания циклических зависимостей
        from generators.html_coordinator import HTMLCoordinator
        
        # Создание координатора с настройками
        coordinator = HTMLCoordinator(
            time_interval=time_interval,
            border_width=borderWidth
        )
        
        # Генерация полного расписания
        result_path = coordinator.generate_complete_schedule(buildings, output_html, output_css, spiski_data=spiski_data)
        
        # Сбор статистики генерации
        stats = coordinator.get_generation_statistics(buildings)
        logger.info(f"HTML генерация завершена: {stats['total_buildings']} зданий, "
                   f"{stats['total_blocks']} блоков")
        
        return result_path
        
    except Exception as e:
        logger.error(f"Ошибка при генерации HTML: {e}")
        import traceback
        traceback.print_exc()
        raise


# ========================================
# ОБЕРТКИ ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ  
# (Функции из старой версии)
# ========================================

def generate_schedule_table(data, days_order, timeColWidth, num_rows, grid_start, time_interval):
    """
    DEPRECATED: Используйте HTMLTableGenerator.generate_schedule_table()
    
    Обертка для обратной совместимости со старым API.
    """
    logger.warning("DEPRECATED: generate_schedule_table() устарел, используйте HTMLTableGenerator")
    
    from generators.html_table_generator import HTMLTableGenerator
    
    generator = HTMLTableGenerator(time_interval, timeColWidth)
    grid_end = grid_start + (num_rows - 1) * time_interval
    
    return generator.generate_schedule_table(data, days_order, grid_start, grid_end)


def generate_activity_blocks(data, days_order, dayCellWidth, cellHeight, headerHeight,
                           timeColWidth, grid_start, time_interval, borderWidth):
    """
    DEPRECATED: Используйте HTMLBlockGenerator.generate_activity_blocks()
    
    Обертка для обратной совместимости со старым API.
    """
    logger.warning("DEPRECATED: generate_activity_blocks() устарел, используйте HTMLBlockGenerator")
    
    from generators.html_block_generator import HTMLBlockGenerator
    
    generator = HTMLBlockGenerator(
        day_cell_width=dayCellWidth,
        cell_height=cellHeight,
        header_height=headerHeight,
        time_col_width=timeColWidth,
        time_interval=time_interval,
        border_width=borderWidth
    )
    
    return generator.generate_activity_blocks(data, days_order, grid_start)


# ========================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ЦВЕТАМИ
# (Обертки для ColorService - обратная совместимость)
# ========================================

def is_light_color(hex_color):
    """
    DEPRECATED: Используйте ColorService.is_light_color()
    
    Args:
        hex_color (str): Цвет в формате HEX
        
    Returns:
        bool: True если цвет светлый
    """
    logger.warning("DEPRECATED: is_light_color() устарел, используйте ColorService.is_light_color()")
    
    try:
        # Отложенный импорт для избежания циклических зависимостей
        from services.color_service import ColorService
        return ColorService.is_light_color(hex_color)
    except ImportError:
        # Fallback реализация
        if not hex_color or not hex_color.startswith('#') or len(hex_color) != 7:
            return True
        try:
            r = int(hex_color[1:3], 16) / 255.0
            g = int(hex_color[3:5], 16) / 255.0
            b = int(hex_color[5:7], 16) / 255.0
            brightness = 0.299 * r + 0.587 * g + 0.114 * b
            return brightness > 0.55
        except ValueError:
            return True


def get_contrast_text_color(hex_color):
    """
    DEPRECATED: Используйте ColorService.get_contrast_text_color()
    
    Args:
        hex_color (str): Цвет фона в формате HEX
        
    Returns:
        str: Контрастный цвет текста
    """
    logger.warning("DEPRECATED: get_contrast_text_color() устарел, используйте ColorService.get_contrast_text_color()")
    
    try:
        # Отложенный импорт для избежания циклических зависимостей
        from services.color_service import ColorService
        return ColorService.get_contrast_text_color(hex_color)
    except ImportError:
        # Fallback реализация
        return '#000000' if is_light_color(hex_color) else '#FFFFFF'


# ========================================
# ВАЛИДАЦИЯ И УТИЛИТЫ
# ========================================

def validate_html_generation_params(buildings, time_interval, borderWidth):
    """
    Валидирует параметры для генерации HTML.
    
    Args:
        buildings (dict): Структура расписания
        time_interval (int): Интервал времени
        borderWidth (float): Толщина границ
        
    Returns:
        bool: True если параметры валидны
    """
    if not buildings or not isinstance(buildings, dict):
        logger.error("Некорректная структура buildings")
        return False
        
    if not isinstance(time_interval, int) or time_interval <= 0:
        logger.error(f"Некорректный time_interval: {time_interval}")
        return False
        
    if not isinstance(borderWidth, (int, float)) or borderWidth < 0:
        logger.error(f"Некорректный borderWidth: {borderWidth}")
        return False
        
    return True


def get_html_generator_info():
    """
    Возвращает информацию о HTML генераторе.
    
    Returns:
        dict: Словарь с метаинформацией
    """
    try:
        # Отложенный импорт для избежания циклических зависимостей
        from generators.html_coordinator import HTMLCoordinator
        
        # Создаем временный координатор для получения информации
        coordinator = HTMLCoordinator()
        coordinator_info = coordinator.get_coordinator_info()
    except ImportError:
        coordinator_info = {'error': 'HTMLCoordinator недоступен'}
    
    return {
        'version': '2.1.0',  # Увеличена версия после рефакторинга
        'refactored': True,
        'architecture': 'modular_generators',
        'main_coordinator': coordinator_info,
        'backward_compatibility': True,
        'deprecated_functions': [
            'generate_schedule_table',
            'generate_activity_blocks', 
            'is_light_color',
            'get_contrast_text_color'
        ],
        'new_modules': [
            'generators.html_coordinator',
            'generators.html_structure_generator',
            'generators.html_table_generator', 
            'generators.html_block_generator'
        ]
    }


# ========================================
# ТЕСТИРОВАНИЕ И ОТЛАДКА
# ========================================

def test_generator_integration():
    """
    Тестирует интеграцию всех генераторов.
    Полезно для проверки работоспособности после рефакторинга.
    """
    logger.info("=== Тест интеграции HTML генераторов ===")
    
    try:
        # Отложенный импорт для избежания циклических зависимостей
        from generators.html_coordinator import HTMLCoordinator
        
        # Создаем координатор
        coordinator = HTMLCoordinator(time_interval=5, border_width=0.5)
        
        # Получаем информацию о всех компонентах
        info = coordinator.get_coordinator_info()
        
        print(f"Координатор: {info['coordinator']} v{info['version']}")
        print(f"Генераторы:")
        for gen_name, gen_info in info['generators'].items():
            print(f"  - {gen_info['generator']} v{gen_info['version']}")
        
        print(f"Настройки: интервал={info['time_interval']}мин, границы={info['border_width']}px")
        print("✅ Все генераторы инициализированы успешно")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка интеграции: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Тест функциональности при прямом запуске
    print("=== HTML Generator - Refactored Version ===")
    
    # Тестируем интеграцию
    test_generator_integration()
    
    # Показываем информацию о генераторе
    print("\n=== Информация о генераторе ===")
    info = get_html_generator_info()
    for key, value in info.items():
        if isinstance(value, dict):
            print(f"{key}:")
            for sub_key, sub_value in value.items():
                print(f"  {sub_key}: {sub_value}")
        elif isinstance(value, list):
            print(f"{key}: {', '.join(value)}")
        else:
            print(f"{key}: {value}")
    
    print("\n✅ Рефакторинг html_generator.py завершен успешно!")
