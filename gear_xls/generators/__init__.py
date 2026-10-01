#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Пакет генераторов HTML для системы расписания.

Модули:
- html_structure_generator - генерация HTML структуры документа
- html_table_generator - генерация таблиц расписания
- html_block_generator - генерация блоков активностей
- html_coordinator - координация всех генераторов
"""

__version__ = '1.0.0'
__author__ = 'Schedule Generator Team'

# Пытаемся сделать прямые импорты, если возможно
try:
    from .html_coordinator import HTMLCoordinator as _HTMLCoordinator
    from .html_structure_generator import HTMLStructureGenerator as _HTMLStructureGenerator
    from .html_table_generator import HTMLTableGenerator as _HTMLTableGenerator
    from .html_block_generator import HTMLBlockGenerator as _HTMLBlockGenerator
    
    # Если прямые импорты работают, используем их
    HTMLCoordinator = _HTMLCoordinator
    HTMLStructureGenerator = _HTMLStructureGenerator
    HTMLTableGenerator = _HTMLTableGenerator
    HTMLBlockGenerator = _HTMLBlockGenerator
    
    def get_html_coordinator():
        """Возвращает класс HTMLCoordinator."""
        return _HTMLCoordinator
    
    def get_structure_generator():
        """Возвращает класс HTMLStructureGenerator."""
        return _HTMLStructureGenerator
    
    def get_table_generator():
        """Возвращает класс HTMLTableGenerator."""
        return _HTMLTableGenerator
    
    def get_block_generator():
        """Возвращает класс HTMLBlockGenerator."""
        return _HTMLBlockGenerator

except ImportError:
    # Если прямые импорты не работают (циклические зависимости),
    # используем отложенные импорты
    
    def get_html_coordinator():
        """Возвращает класс HTMLCoordinator."""
        from .html_coordinator import HTMLCoordinator
        return HTMLCoordinator
    
    def get_structure_generator():
        """Возвращает класс HTMLStructureGenerator."""
        from .html_structure_generator import HTMLStructureGenerator
        return HTMLStructureGenerator
    
    def get_table_generator():
        """Возвращает класс HTMLTableGenerator."""
        from .html_table_generator import HTMLTableGenerator
        return HTMLTableGenerator
    
    def get_block_generator():
        """Возвращает класс HTMLBlockGenerator."""
        from .html_block_generator import HTMLBlockGenerator
        return HTMLBlockGenerator
    
    # Создаем wrapper классы/функции для обратной совместимости
    def HTMLCoordinator(*args, **kwargs):
        """Создает экземпляр HTMLCoordinator."""
        CoordinatorClass = get_html_coordinator()
        return CoordinatorClass(*args, **kwargs)
    
    def HTMLStructureGenerator(*args, **kwargs):
        """Создает экземпляр HTMLStructureGenerator."""
        GeneratorClass = get_structure_generator()
        return GeneratorClass(*args, **kwargs)
    
    def HTMLTableGenerator(*args, **kwargs):
        """Создает экземпляр HTMLTableGenerator."""
        GeneratorClass = get_table_generator()
        return GeneratorClass(*args, **kwargs)
    
    def HTMLBlockGenerator(*args, **kwargs):
        """Создает экземпляр HTMLBlockGenerator."""
        GeneratorClass = get_block_generator()
        return GeneratorClass(*args, **kwargs)

# Основная функция для обратной совместимости
def generate_html_schedule(buildings, output_html="schedule.html", output_css="schedule.css", 
                          time_interval=5, borderWidth=0.5):
    """
    Генерирует HTML-страницу с интерактивным расписанием.
    
    Функция-обертка для обратной совместимости, использует HTMLCoordinator.
    
    Args:
        buildings (dict): Структура расписания по зданиям
        output_html (str): Путь для сохранения HTML-файла
        output_css (str): Путь для сохранения CSS-файла (если необходимо)
        time_interval (int): Интервал времени в минутах для отображения в сетке
        borderWidth (float): Толщина границы ячейки в пикселях
    """
    coordinator_class = get_html_coordinator()
    coordinator = coordinator_class(time_interval=time_interval, border_width=borderWidth)
    return coordinator.generate_complete_schedule(buildings, output_html, output_css)

# Экспортируемые элементы
__all__ = [
    'HTMLCoordinator',
    'HTMLStructureGenerator', 
    'HTMLTableGenerator',
    'HTMLBlockGenerator',
    'get_html_coordinator',
    'get_structure_generator', 
    'get_table_generator',
    'get_block_generator',
    'generate_html_schedule'
]
