#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор HTML таблиц для расписания.
Отвечает за создание сетки расписания с временными метками,
заголовками дней недели и кабинетами.
"""

import logging
from html import escape as html_escape

try:
    from ..utils import minutes_to_time
except ImportError:
    from utils import minutes_to_time

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('html_table_generator')


class HTMLTableGenerator:
    """
    Генератор HTML таблиц расписания.
    
    Отвечает за:
    - Создание сетки расписания с временными интервалами
    - Генерацию заголовков с днями недели и кабинетами
    - Создание ячеек таблицы с правильными атрибутами
    """
    
    def __init__(self, time_interval=5, time_col_width=80):
        """
        Инициализация генератора таблиц.
        
        Args:
            time_interval (int): Интервал времени в минутах
            time_col_width (int): Ширина колонки времени в пикселях
        """
        self.time_interval = time_interval
        self.time_col_width = time_col_width
        logger.debug(f"Инициализирован HTMLTableGenerator: interval={time_interval}, time_col_width={time_col_width}")
    
    def generate_schedule_table(self, building_data, days_order, grid_start, grid_end):
        """
        Генерирует полную HTML таблицу-сетку расписания для здания.
        
        Args:
            building_data (dict): Данные расписания для конкретного здания
            days_order (list): Порядок дней недели
            grid_start (int): Начальное время сетки в минутах
            grid_end (int): Конечное время сетки в минутах
            
        Returns:
            str: HTML-код таблицы расписания
        """
        num_rows = ((grid_end - grid_start) // self.time_interval) + 1
        
        table_parts = [
            '<table class="schedule-grid">',
            self._generate_table_header(building_data, days_order),
            self._generate_table_body(building_data, days_order, grid_start, num_rows),
            '</table>'
        ]
        
        logger.debug(f"Сгенерирована таблица расписания: {num_rows} строк, {len(days_order)} дней")
        return "\n".join(table_parts)
    
    def _generate_table_header(self, building_data, days_order):
        """
        Генерирует заголовок таблицы с днями и кабинетами.
        
        Args:
            building_data (dict): Данные здания
            days_order (list): Порядок дней недели
            
        Returns:
            str: HTML код заголовка таблицы
        """
        header_parts = [
            "<thead>",
            "<tr>",
            '<th class="time-cell">Время</th>'
        ]
        
        # Заголовки дней недели
        for day in days_order:
            var_cols = building_data.get('_max_cols', {}).get(day, 1)
            for col in range(var_cols):
                # Определяем название кабинета
                cabinet = self._get_room_name(building_data, day, col)
                # Header metadata must stay aligned with td.day-*/data-col and
                # activity-block[data-col-index] so runtime features can map
                # a visible column back to its logical room/day coordinates.
                header_parts.append(
                    f'<th class="day-{day}" '
                    f'data-day="{html_escape(day, quote=True)}" '
                    f'data-col="{col}" '
                    f'data-room="{html_escape(cabinet, quote=True)}">'
                    f'{html_escape(day)}<br>{html_escape(cabinet)}'
                    '</th>'
                )
        
        header_parts.extend(["</tr>", "</thead>"])
        
        logger.debug("Сгенерирован заголовок таблицы с кабинетами")
        return "\n".join(header_parts)
    
    def _generate_table_body(self, building_data, days_order, grid_start, num_rows):
        """
        Генерирует тело таблицы с временными интервалами.
        
        Args:
            building_data (dict): Данные здания
            days_order (list): Порядок дней недели
            grid_start (int): Начальное время в минутах
            num_rows (int): Количество строк
            
        Returns:
            str: HTML код тела таблицы
        """
        body_parts = ["<tbody>"]
        
        for row in range(num_rows):
            body_parts.append(self._generate_table_row(building_data, days_order, grid_start, row))
        
        body_parts.append("</tbody>")
        
        logger.debug(f"Сгенерировано тело таблицы с {num_rows} строками")
        return "\n".join(body_parts)
    
    def _generate_table_row(self, building_data, days_order, grid_start, row):
        """
        Генерирует одну строку таблицы.
        
        Args:
            building_data (dict): Данные здания
            days_order (list): Порядок дней недели
            grid_start (int): Начальное время в минутах
            row (int): Номер строки
            
        Returns:
            str: HTML код строки таблицы
        """
        row_parts = ["<tr>"]
        
        # Ячейка времени
        current_time = minutes_to_time(grid_start + row * self.time_interval)
        time_step = 15 // self.time_interval  # Метки каждые 15 минут
        display_time = current_time if row % time_step == 0 else ""
        
        row_parts.append(f'<td class="time-cell" data-row="{row}" data-col="time">{display_time}</td>')
        
        # Ячейки дней недели
        for day in days_order:
            var_cols = building_data.get('_max_cols', {}).get(day, 1)
            for col in range(var_cols):
                row_parts.append(f'<td class="day-{day}" data-row="{row}" data-col="{col}"></td>')
        
        row_parts.append("</tr>")
        return "".join(row_parts)
    
    def _get_room_name(self, building_data, day, col):
        """
        Получает название кабинета для дня и колонки.
        
        Args:
            building_data (dict): Данные здания
            day (str): День недели
            col (int): Номер колонки
            
        Returns:
            str: Название кабинета
        """
        rooms = building_data.get('_rooms', {}).get(day, [])
        if col < len(rooms):
            return rooms[col]
        return building_data.get('_default_room', "")
    
    def calculate_table_dimensions(self, building_data, days_order, grid_start, grid_end):
        """
        Рассчитывает размеры таблицы.
        
        Args:
            building_data (dict): Данные здания
            days_order (list): Порядок дней недели
            grid_start (int): Начальное время в минутах
            grid_end (int): Конечное время в минутах
            
        Returns:
            dict: Словарь с размерами таблицы
        """
        num_rows = ((grid_end - grid_start) // self.time_interval) + 1
        total_cols = sum(building_data.get('_max_cols', {}).get(day, 1) for day in days_order)
        
        dimensions = {
            'rows': num_rows,
            'cols': total_cols + 1,  # +1 для колонки времени
            'time_span_minutes': grid_end - grid_start,
            'time_intervals': num_rows
        }
        
        logger.debug(f"Рассчитаны размеры таблицы: {dimensions}")
        return dimensions
    
    def validate_table_data(self, building_data, days_order):
        """
        Проверяет валидность данных для генерации таблицы.
        
        Args:
            building_data (dict): Данные здания
            days_order (list): Порядок дней недели
            
        Returns:
            bool: True если данные валидны
        """
        if not building_data or not isinstance(building_data, dict):
            logger.error("Некорректные данные здания")
            return False
        
        if not days_order or not isinstance(days_order, list):
            logger.error("Некорректный порядок дней недели")
            return False
        
        max_cols = building_data.get('_max_cols', {})
        if not max_cols:
            logger.warning("Отсутствует информация о колонках (_max_cols)")
        
        return True
    
    def get_generator_info(self):
        """
        Возвращает информацию о генераторе таблиц.
        
        Returns:
            dict: Словарь с метаинформацией
        """
        return {
            'generator': 'HTMLTableGenerator',
            'version': '1.0.0',
            'time_interval': self.time_interval,
            'time_col_width': self.time_col_width,
            'features': [
                'grid_generation',
                'time_labels',
                'room_headers',
                'responsive_cells'
            ]
        }
    
