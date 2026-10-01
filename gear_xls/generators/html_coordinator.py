#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Координатор HTML генераторов для создания полного расписания.
Управляет взаимодействием между всеми специализированными генераторами
и обеспечивает создание финального HTML документа.
"""

import os
import logging
from .html_structure_generator import HTMLStructureGenerator
from .html_table_generator import HTMLTableGenerator
from .html_block_generator import HTMLBlockGenerator
from gear_xls.day_constants import WEB_EDITOR_DAYS

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('html_coordinator')


class HTMLCoordinator:
    """
    Координатор HTML генераторов.
    
    Управляет процессом создания полного HTML расписания,
    координируя работу всех специализированных генераторов.
    """
    
    def __init__(self, time_interval=5, border_width=0.5):
        """
        Инициализация координатора с настройками.
        
        Args:
            time_interval (int): Интервал времени в минутах
            border_width (float): Толщина границ в пикселях
        """
        self.time_interval = time_interval
        self.border_width = border_width
        
        # Инициализация специализированных генераторов
        self.structure_generator = HTMLStructureGenerator(time_interval, border_width)
        self.table_generator = HTMLTableGenerator(time_interval)
        self.block_generator = HTMLBlockGenerator(time_interval=time_interval, border_width=border_width)
        
        # Константы для расчетов
        self.days_order = list(WEB_EDITOR_DAYS)
        self.day_cell_width = 100
        self.time_col_width = 80
        
        logger.info(f"Инициализирован HTMLCoordinator: interval={time_interval}, border={border_width}")
    
    def generate_complete_schedule(self, buildings, output_html="schedule.html", output_css="schedule.css", spiski_data=None):
        """
        Генерирует полный HTML документ расписания.
        
        Args:
            buildings (dict): Структура расписания по зданиям
            output_html (str): Путь для сохранения HTML-файла
            output_css (str): Путь для сохранения CSS-файла
            
        Returns:
            str: Путь к созданному HTML файлу
        """
        logger.info(f"Начинаем генерацию полного HTML расписания: {output_html}")
        
        # Валидация входных данных
        if not self._validate_buildings_data(buildings):
            raise ValueError("Некорректные данные расписания")
        
        # Определение времени сетки
        grid_start, grid_end = self._determine_grid_bounds(buildings)
        
        html_parts = []
        
        # 1. Генерация структуры документа
        html_parts.extend(self.structure_generator.generate_document_head(grid_start, spiski_data=spiski_data))
        html_parts.append("<body>")
        
        # 2. Генерация панели управления
        html_parts.extend(self.structure_generator.generate_control_panel())
        
        # 3. Генерация заголовка страницы
        html_parts.extend(self.structure_generator.generate_page_header())
        
        # 4. Генерация контента для каждого здания
        buildings_count = 0
        for building, data in buildings.items():
            if building.startswith("_"):
                continue  # Пропускаем служебные ключи
            
            html_parts.extend(self._generate_building_section(building, data, grid_start, grid_end))
            buildings_count += 1
        
        # 5. Завершение документа
        html_parts.extend(self.structure_generator.generate_document_end())
        
        # Сохранение файла
        self._save_html_file(html_parts, output_html)
        
        logger.info(f"HTML расписание создано: {output_html} ({buildings_count} зданий)")
        return output_html
    
    def _generate_building_section(self, building_name, building_data, grid_start, grid_end):
        """
        Генерирует секцию HTML для одного здания.
        
        Args:
            building_name (str): Название здания
            building_data (dict): Данные здания
            grid_start (int): Начальное время сетки
            grid_end (int): Конечное время сетки
            
        Returns:
            list: Список HTML строк для здания
        """
        section_parts = []
        
        # Заголовок здания
        section_parts.extend(self.structure_generator.generate_building_header(building_name))
        
        # Расчет размеров контейнера
        container_width = self.structure_generator.calculate_container_width(
            building_data, self.days_order, self.day_cell_width, self.time_col_width
        )
        
        # Открытие контейнера
        section_parts.append(
            self.structure_generator.generate_container_start(building_name, container_width)
        )
        
        # Генерация таблицы-сетки
        table_html = self.table_generator.generate_schedule_table(
            building_data, self.days_order, grid_start, grid_end
        )
        section_parts.append(table_html)
        
        # Генерация блоков активностей
        blocks_html = self.block_generator.generate_activity_blocks(
            building_data, self.days_order, grid_start
        )
        section_parts.append(blocks_html)
        
        # Закрытие контейнера
        section_parts.append(self.structure_generator.generate_container_end())
        
        logger.debug(f"Сгенерирована секция для здания: {building_name}")
        return section_parts
    
    def _validate_buildings_data(self, buildings):
        """
        Проверяет валидность данных зданий.
        
        Args:
            buildings (dict): Структура расписания
            
        Returns:
            bool: True если данные валидны
        """
        if not buildings or not isinstance(buildings, dict):
            logger.error("Некорректная структура buildings")
            return False
        
        # Проверяем наличие хотя бы одного здания
        building_count = len([b for b in buildings.keys() if not b.startswith('_')])
        if building_count == 0:
            logger.error("Не найдено ни одного здания")
            return False
        
        logger.debug(f"Валидация прошла успешно: {building_count} зданий")
        return True
    
    def _determine_grid_bounds(self, buildings):
        """
        Определяет границы временной сетки из данных зданий.
        
        Args:
            buildings (dict): Структура расписания
            
        Returns:
            tuple: (grid_start, grid_end) в минутах
        """
        # Ищем информацию о сетке в любом здании
        for building, data in buildings.items():
            if building.startswith("_") or not isinstance(data, dict):
                continue
            
            grid_start = data.get('_grid_start', 9 * 60)  # 09:00 по умолчанию
            grid_end = data.get('_grid_end', 20 * 60)  # 20:00 по умолчанию
            
            logger.debug(f"Определены границы сетки: {grid_start//60:02d}:{grid_start%60:02d} - {grid_end//60:02d}:{grid_end%60:02d}")
            return grid_start, grid_end
        
        # Значения по умолчанию
        default_start, default_end = 9 * 60, 20 * 60
        logger.warning(f"Используются границы сетки по умолчанию: {default_start//60:02d}:{default_start%60:02d} - {default_end//60:02d}:{default_end%60:02d}")
        return default_start, default_end
    
    def _save_html_file(self, html_parts, output_path):
        """
        Сохраняет HTML части в файл.
        
        Args:
            html_parts (list): Список HTML строк
            output_path (str): Путь к выходному файлу
        """
        # Создаем директорию если она не существует
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # Записываем HTML-файл
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(html_parts))
        
        logger.debug(f"HTML файл сохранен: {output_path}")
    
    def get_generation_statistics(self, buildings):
        """
        Собирает статистику генерации для зданий.
        
        Args:
            buildings (dict): Структура расписания
            
        Returns:
            dict: Статистика генерации
        """
        stats = {
            'total_buildings': 0,
            'total_blocks': 0,
            'buildings_stats': {}
        }
        
        for building, data in buildings.items():
            if building.startswith("_"):
                continue
            
            stats['total_buildings'] += 1
            
            # Статистика блоков для здания
            building_blocks = self.block_generator.get_block_statistics(data, self.days_order)
            stats['total_blocks'] += building_blocks['total_blocks']
            stats['buildings_stats'][building] = building_blocks
        
        stats['average_blocks_per_building'] = (
            stats['total_blocks'] / stats['total_buildings'] 
            if stats['total_buildings'] > 0 else 0
        )
        
        return stats
    
    def get_coordinator_info(self):
        """
        Возвращает информацию о координаторе и всех генераторах.
        
        Returns:
            dict: Словарь с полной информацией
        """
        return {
            'coordinator': 'HTMLCoordinator',
            'version': '1.0.0',
            'time_interval': self.time_interval,
            'border_width': self.border_width,
            'generators': {
                'structure': self.structure_generator.get_generator_info(),
                'table': self.table_generator.get_generator_info(),
                'blocks': self.block_generator.get_generator_info()
            },
            'constants': {
                'days_order': self.days_order,
                'day_cell_width': self.day_cell_width,
                'time_col_width': self.time_col_width
            }
        }
    
