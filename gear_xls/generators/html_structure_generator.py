#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор HTML структуры документа для расписания.
Отвечает за создание основной структуры HTML документа, head секции,
подключение стилей и JavaScript.
"""

import os
import uuid
import logging
from html_styles import get_css_styles
from html_javascript import get_javascript
from gear_xls.day_constants import WEB_EDITOR_DAYS

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('html_structure_generator')


class HTMLStructureGenerator:
    """
    Генератор HTML структуры документа.
    
    Отвечает за:
    - Создание DOCTYPE и базовой HTML структуры
    - Генерацию head секции с мета-тегами
    - Подключение CSS стилей и JavaScript
    - Создание панели управления с кнопками
    """
    
    def __init__(self, time_interval=5, border_width=0.5):
        """
        Инициализация генератора структуры.
        
        Args:
            time_interval (int): Интервал времени в минутах
            border_width (float): Толщина границ в пикселях
        """
        self.time_interval = time_interval
        self.border_width = border_width
        logger.debug(f"Инициализирован HTMLStructureGenerator: interval={time_interval}, border={border_width}")
    
    def generate_document_head(self, grid_start=9*60, spiski_data=None):
        """
        Генерирует head секцию HTML документа.

        Args:
            grid_start (int): Начало сетки в минутах (передаётся в JS как глобал gridStart)

        Returns:
            list: Список строк HTML для head секции
        """
        cellHeight = 15
        dayCellWidth = 100
        timeColWidth = 80
        headerHeight = 45
        days_order = list(WEB_EDITOR_DAYS)

        head_parts = [
            "<!DOCTYPE html>",
            "<html lang='ru'>",
            "<head>",
            '  <meta charset="UTF-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
            "  <title>Расписание занятий</title>"
        ]

        # Встроенные стили
        head_parts.append(get_css_styles(cellHeight, dayCellWidth, timeColWidth, self.border_width))

        # Встроенный JavaScript
        head_parts.append(get_javascript(cellHeight, dayCellWidth, headerHeight, days_order,
                                       self.time_interval, self.border_width, grid_start,
                                       spiski_data=spiski_data))

        head_parts.append("</head>")
        
        logger.debug("Сгенерирована head секция HTML документа")
        return head_parts
    
    def generate_control_panel(self):
        """
        Генерирует панель управления с кнопками.
        
        Returns:
            list: Список строк HTML для панели управления
        """
        days_order = list(WEB_EDITOR_DAYS)
        csrf_token = str(uuid.uuid4())
        
        panel_parts = [
            '<div class="sticky-buttons">',
            '<button id="menuButton" onclick="toggleMenu()">&#9776; Меню</button>',
            '<div id="menuDropdown">',
            '  <div class="menu-item" id="menuItemNewSchedule" onclick="handleNewSchedule()">Создать новое расписание</div>',
            '  <div class="menu-item" id="menuItemAddColumn" onclick="openAddColumnDialog()">Добавить колонку</div>',
            '  <div class="menu-item" id="menu-publish-item" style="display:none">Опубликовать расписание</div>',
            '</div>',
        ]
        
        # Кнопки показа/скрытия дней
        for day in days_order:
            panel_parts.append(f'<button class="toggle-day-button" data-day="{day}" onclick="toggleDay(this, \'{day}\')">+/- {day}</button>')
        
        # Кнопки управления
        panel_parts.extend([
            '<button id="exportToExcel">Экспорт в Excel</button>',
            f'<input type="hidden" id="csrf_token" value="{csrf_token}">',
            '</div>'
        ])
        
        logger.debug("Сгенерирована панель управления с кнопками")
        return panel_parts
    
    def generate_page_header(self):
        """
        Генерирует заголовок страницы.
        
        Returns:
            list: Список строк HTML для заголовка
        """
        return ["<h1>Расписание занятий</h1>"]
    
    def generate_building_header(self, building_name):
        """
        Генерирует заголовок для конкретного здания.
        
        Args:
            building_name (str): Название здания
            
        Returns:
            list: Список строк HTML для заголовка здания
        """
        return [f"<h2>Здание: {building_name}</h2>"]
    
    def generate_container_start(self, building_name, container_width):
        """
        Генерирует открывающий тег контейнера расписания.
        
        Args:
            building_name (str): Название здания
            container_width (int): Ширина контейнера в пикселях
            
        Returns:
            str: HTML строка для открытия контейнера
        """
        # Container width is viewport-bound via CSS so horizontal scrolling stays inside it.
        return f'<div class="schedule-container" data-building="{building_name}">'
    
    def generate_container_end(self):
        """
        Генерирует закрывающий тег контейнера расписания.
        
        Returns:
            str: HTML строка для закрытия контейнера
        """
        return "</div>"
    
    def generate_document_end(self):
        """
        Генерирует закрывающие теги документа.
        
        Returns:
            list: Список строк HTML для завершения документа
        """
        return ["</body>", "</html>"]
    
    def calculate_container_width(self, building_data, days_order, day_cell_width=100, time_col_width=80):
        """
        Рассчитывает ширину контейнера для здания.
        
        Args:
            building_data (dict): Данные здания
            days_order (list): Порядок дней недели
            day_cell_width (int): Ширина ячейки дня
            time_col_width (int): Ширина колонки времени
            
        Returns:
            int: Ширина контейнера в пикселях
        """
        total_cols = 0
        for day in days_order:
            total_cols += building_data.get('_max_cols', {}).get(day, 1)
        
        container_width = time_col_width + total_cols * day_cell_width
        logger.debug(f"Рассчитана ширина контейнера: {container_width}px для {total_cols} колонок")
        return container_width
    
    def get_generator_info(self):
        """
        Возвращает информацию о генераторе структуры.
        
        Returns:
            dict: Словарь с метаинформацией
        """
        return {
            'generator': 'HTMLStructureGenerator',
            'version': '1.0.0',
            'time_interval': self.time_interval,
            'border_width': self.border_width,
            'features': [
                'document_structure',
                'control_panel',
                'responsive_headers',
                'csrf_protection'
            ]
        }
    
