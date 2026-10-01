#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис для обработки пайплайна создания расписания.
Инкапсулирует общую логику преобразования Excel → HTML.
"""

import os
import logging
import re
import uuid
from typing import Dict, Any, Optional

# Импортируем существующие модули
try:
    from ..excel_parser import parse_schedule
    from ..schedule_structure import build_schedule_structure
    from ..html_generator import generate_html_schedule
    from ..time_utils import minutes_to_time
except ImportError:
    from excel_parser import parse_schedule
    from schedule_structure import build_schedule_structure
    from html_generator import generate_html_schedule
    from time_utils import minutes_to_time


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('schedule_pipeline')

_HTML_ACTIVITY_BLOCK_PATTERN = re.compile(
    r"<div(?P<attrs>[^>]*class=['\"][^'\"]*activity-block[^'\"]*['\"][^>]*)>"
    r"(?P<body>.*?)</div>",
    re.I | re.S,
)


class SchedulePipelineError(Exception):
    """Исключение для ошибок в пайплайне обработки расписания"""
    pass


def _resolve_lesson_type(interval: dict) -> str:
    lesson_type = str(interval.get("lesson_type") or "").strip().lower()
    return lesson_type or "group"


def _is_embedded_non_group_block(attrs_text: str) -> bool:
    match = re.search(r"data-lesson-type=['\"]([^'\"]*)['\"]", attrs_text, re.I)
    lesson_type = (match.group(1).strip().lower() if match else "")
    if lesson_type and lesson_type != "group":
        return True
    class_match = re.search(r"class=['\"]([^'\"]*)['\"]", attrs_text, re.I)
    classes = class_match.group(1).lower().split() if class_match else []
    return any(
        cls in ("lesson-type-individual", "lesson-type-nachhilfe", "lesson-type-trial")
        for cls in classes
    )


def strip_non_group_activity_blocks_from_html(html: str) -> tuple[str, int]:
    removed_count = 0

    def replace(match):
        nonlocal removed_count
        if _is_embedded_non_group_block(match.group("attrs")):
            removed_count += 1
            return ""
        return match.group(0)

    return _HTML_ACTIVITY_BLOCK_PATTERN.sub(replace, html), removed_count


def strip_non_group_activity_blocks_from_file(path: str) -> int:
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    stripped, removed_count = strip_non_group_activity_blocks_from_html(html)
    if removed_count:
        with open(path, "w", encoding="utf-8") as f:
            f.write(stripped)
    return removed_count


def collect_individual_blocks_from_buildings(buildings: dict) -> list[dict]:
    blocks = []
    seen_signatures = set()

    for building, building_data in buildings.items():
        if str(building).startswith("_") or not isinstance(building_data, dict):
            continue
        for day, intervals in building_data.items():
            if str(day).startswith("_") or not isinstance(intervals, list):
                continue
            for interval in intervals:
                lesson_type = _resolve_lesson_type(interval)
                if lesson_type == "group":
                    continue
                start_time = minutes_to_time(interval.get("start", 0))
                end_time = minutes_to_time(interval.get("end", 0))
                room = str(interval.get("room_display") or interval.get("room") or "").strip()
                trial_dates = [
                    str(value)
                    for value in (interval.get("trial_dates") or [])
                    if value is not None
                ]
                signature = (
                    str(interval.get("id", "")),
                    str(building),
                    str(day),
                    room,
                    start_time,
                    end_time,
                    str(interval.get("subject", "")),
                    str(interval.get("teacher", "")),
                    str(interval.get("students", "")),
                    lesson_type,
                    tuple(trial_dates),
                )
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)

                block = {
                    "id": str(interval.get("id") or uuid.uuid4()),
                    "day": str(day),
                    "building": str(building),
                    "room": room,
                    "start_time": start_time,
                    "end_time": end_time,
                    "subject": str(interval.get("subject", "")),
                    "teacher": str(interval.get("teacher", "")),
                    "students": str(interval.get("students", "")),
                    "lesson_type": lesson_type,
                    "color": interval.get("color"),
                    "start_row": interval.get("row_start"),
                    "row_span": interval.get("rowspan"),
                }
                if lesson_type == "trial":
                    block["trial_dates"] = trial_dates
                blocks.append({key: value for key, value in block.items() if value is not None})

    return blocks


class SchedulePipeline:
    """
    Сервис для координации процесса создания расписания из Excel файла.
    
    Инкапсулирует весь пайплайн: парсинг → структурирование → генерация HTML
    """
    
    def __init__(self, time_interval: int = 5, border_width: float = 0.5):
        """
        Инициализация пайплайна с настройками по умолчанию.
        
        Args:
            time_interval (int): Интервал времени в минутах для сетки расписания
            border_width (float): Толщина границ ячеек в пикселях
        """
        self.time_interval = time_interval
        self.border_width = border_width
        logger.info(f"Инициализирован SchedulePipeline: interval={time_interval}мин, border={border_width}px")
    
    def process_excel_to_outputs(self, excel_file_path: str, output_dirs: Dict[str, str], spiski_data=None) -> Dict[str, Any]:
        """
        Обрабатывает Excel файл и создает HTML выходной файл.
        
        Args:
            excel_file_path (str): Путь к исходному Excel файлу
            output_dirs (Dict[str, str]): Словарь с путями к директориям вывода
                                        (должен содержать ключ 'html')
        
        Returns:
            Dict[str, Any]: Словарь с результатами обработки:
                - html_file: путь к созданному HTML файлу
                - buildings: структура расписания по зданиям
                - activities_count: количество обработанных занятий
        
        Raises:
            SchedulePipelineError: При ошибках на любом этапе обработки
        """
        logger.info(f"Начинаем обработку файла: {excel_file_path}")
        
        # Проверяем существование входного файла
        if not os.path.exists(excel_file_path):
            raise SchedulePipelineError(f"Excel файл не найден: {excel_file_path}")
          # Проверяем наличие выходных директорий
        required_dirs = ['html']
        for dir_key in required_dirs:
            if dir_key not in output_dirs:
                raise SchedulePipelineError(f"Не указана директория для {dir_key}")
            if not os.path.exists(output_dirs[dir_key]):
                raise SchedulePipelineError(f"Директория не существует: {output_dirs[dir_key]}")
        
        try:
            # Этап 1: Парсинг Excel файла
            logger.info("Этап 1: Парсинг Excel файла...")
            activities = parse_schedule(excel_file_path)
            if not activities:
                raise SchedulePipelineError("Не удалось извлечь данные о занятиях из Excel файла. "
                                          "Проверьте формат файла и наличие листа 'Schedule'.")
            
            activities_count = len(activities)
            logger.info(f"Успешно извлечено {activities_count} занятий")
            
            # Этап 2: Построение структуры расписания
            logger.info("Этап 2: Построение структуры расписания...")
            buildings = build_schedule_structure(activities, time_interval=self.time_interval)
            if not buildings:
                raise SchedulePipelineError("Не удалось создать структуру расписания из извлеченных данных.")
            
            individual_blocks = collect_individual_blocks_from_buildings(buildings)
            buildings_count = len([b for b in buildings.keys() if not b.startswith('_')])
            logger.info(f"Успешно построена структура для {buildings_count} зданий")
            
            # Этап 3: Генерация HTML
            logger.info("Этап 3: Генерация HTML файла...")
            html_file = os.path.join(output_dirs["html"], "schedule.html")
            generate_html_schedule(
                buildings, 
                output_html=html_file, 
                time_interval=self.time_interval,
                borderWidth=self.border_width,
                spiski_data=spiski_data
            )
            
            if not os.path.exists(html_file):
                raise SchedulePipelineError(f"HTML файл не был создан: {html_file}")            
            logger.info(f"HTML файл создан: {html_file}")
            
            # Формируем результат
            removed_embedded_blocks = strip_non_group_activity_blocks_from_file(html_file)
            if removed_embedded_blocks:
                logger.info(
                    "Removed %d embedded non-group blocks from generated HTML; "
                    "they will be initialized from individual_lessons.json",
                    removed_embedded_blocks,
                )

            result = {
                'html_file': html_file,
                'buildings': buildings,
                'individual_blocks': individual_blocks,
                'activities_count': activities_count,
                'buildings_count': buildings_count
            }
            
            logger.info(f"Обработка завершена успешно. Обработано {activities_count} занятий, "
                       f"создано {buildings_count} зданий")
            
            return result
            
        except Exception as e:
            # Логируем подробную информацию об ошибке
            logger.error(f"Ошибка при обработке файла {excel_file_path}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            
            # Перебрасываем как SchedulePipelineError для единообразной обработки
            if isinstance(e, SchedulePipelineError):
                raise
            else:
                raise SchedulePipelineError(f"Внутренняя ошибка при обработке: {e}")
    
    def validate_excel_file(self, excel_file_path: str) -> bool:
        """
        Быстрая проверка валидности Excel файла без полной обработки.
        
        Args:
            excel_file_path (str): Путь к Excel файлу
            
        Returns:
            bool: True если файл можно обработать, False иначе
        """
        try:
            if not os.path.exists(excel_file_path):
                return False
            
            # Пытаемся извлечь хотя бы одно занятие
            activities = parse_schedule(excel_file_path)
            return bool(activities)
            
        except Exception as e:
            logger.warning(f"Файл {excel_file_path} не прошел валидацию: {e}")
            return False
    
    def get_pipeline_info(self) -> Dict[str, Any]:
        """
        Возвращает информацию о текущих настройках пайплайна.
        
        Returns:
            Dict[str, Any]: Словарь с настройками пайплайна
        """
        return {
            'time_interval': self.time_interval,
            'border_width': self.border_width,
            'version': '1.0.0'
        }
    
