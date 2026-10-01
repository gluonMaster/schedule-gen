#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для генерации PDF-версий расписания для печати.
Использует pdfkit и wkhtmltopdf для преобразования HTML в PDF.
"""

import os
import logging
from utils import minutes_to_time

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('pdf_generator')

def generate_pdf_schedule(buildings, output_dir="pdfs", time_interval=5):
    """
    Генерирует PDF для каждой таблицы расписания (для каждого здания)
    с параметрами: формат A2, горизонтальная ориентация, поля 15 мм.
    
    Args:
        buildings (dict): Структура расписания по зданиям
        output_dir (str): Путь к директории для сохранения PDF-файлов
        time_interval (int): Интервал времени в минутах для отображения в сетке
    """
    try:
        import pdfkit
    except ImportError:
        logger.error("Не удалось импортировать pdfkit. Установите его с помощью pip install pdfkit")
        logger.error("Также требуется установить wkhtmltopdf: https://wkhtmltopdf.org/downloads.html")
        return

    # Создаём папку для PDF, если её ещё нет
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Порядок дней (как в основном расписании)
    days_order = ["Mo", "Di", "Mi", "Do", "Fr", "Sa"]
    
    logger.info(f"Генерация PDF-расписаний в директорию: {output_dir}")

    # Для каждого здания генерируем отдельный HTML и преобразуем его в PDF
    for building, data in buildings.items():
        # Пропускаем служебные ключи
        if building.startswith("_"):
            continue

        # Получаем время начала и конца сетки расписания
        grid_start = data.get('_grid_start', 9 * 60)  # 09:00 в минутах
        grid_end = data.get('_grid_end', 19 * 60 + 45)  # 19:45 в минутах

        html_parts = []
        html_parts.append("<!DOCTYPE html>")
        html_parts.append("<html>")
        html_parts.append("<head>")
        html_parts.append('    <meta charset="UTF-8">')
        # Вставляем минимальные CSS-стили, необходимые для отображения таблицы
        html_parts.append("""
        <style>
            body { 
                font-family: Arial, sans-serif; 
                margin: 0; 
                padding: 10px;
            }
            .schedule-table { 
                border-collapse: collapse; 
                width: 100%; 
                table-layout: fixed; 
            }
            .schedule-table th, .schedule-table td { 
                border: 1px solid #888; 
                padding: 5px; 
                text-align: center; 
                vertical-align: middle; 
                font-size: 10px;
            }
            .schedule-table thead { 
                display: table-row-group; 
            }
            .time-header { 
                background-color: #f0f0f0; 
                font-weight: bold;
            }
            .time-cell { 
                background-color: #f9f9f9; 
                font-weight: bold;
            }
            .activity-block { 
                font-size: 9px; 
                color: #fff; 
                line-height: 1.2; 
                word-break: break-all; 
                padding: 2px;
                text-shadow: 0 0 1px #000;
            }
            h2 { 
                text-align: center; 
                font-size: 20px;
                margin-top: 0;
                margin-bottom: 20px;
            }
        </style>
        """)
        html_parts.append("</head>")
        html_parts.append("<body>")
        html_parts.append(f"<h2>Расписание занятий - Здание: {building}</h2>")
        html_parts.append('<table class="schedule-table">')
        
        # Генерация заголовка таблицы
        html_parts.append("<thead>")
        html_parts.append("<tr>")
        html_parts.append('    <th class="time-header">Время</th>')
        for day in days_order:
            cols = data.get('_max_cols', {}).get(day, 1)
            if cols > 0:
                html_parts.append(f'    <th colspan="{cols}">{day}</th>')
        html_parts.append("</tr>")
        html_parts.append("<tr>")
        html_parts.append("    <th></th>")
        for day in days_order:
            cols = data.get('_max_cols', {}).get(day, 1)
            for col in range(cols):
                cabinet = ""
                if day in data.get('_rooms', {}) and col < len(data['_rooms'][day]):
                    cabinet = data['_rooms'][day][col]
                html_parts.append(f'    <th>{cabinet}</th>')
        html_parts.append("</tr>")
        html_parts.append("</thead>")
        
        # Генерация тела таблицы
        html_parts.append("<tbody>")
        
        # Учитываем новый интервал времени (5 минут)
        # Для PDF выводим только строки, кратные 15 минутам
        time_step = 15 // time_interval
        num_rows = ((grid_end - grid_start) // time_interval) + 1

        # Создаём словарь для отслеживания rowspan по дням
        occupancy = {day: [0] * data.get('_max_cols', {}).get(day, 1) for day in days_order}

        for row in range(0, num_rows, time_step):
            html_parts.append("<tr>")
            current_time = minutes_to_time(grid_start + row * time_interval)
            html_parts.append(f'    <td class="time-cell">{current_time}</td>')
            
            for day in days_order:
                cols = data.get('_max_cols', {}).get(day, 1)
                grid_day = data.get('_grid', {}).get(day, {})
                
                for col in range(cols):
                    # Если ячейка уже занята предыдущим rowspan, пропускаем её
                    if occupancy[day][col] > row:
                        continue
                    
                    # Проверяем, есть ли занятие, начинающееся в этой ячейке
                    if (col, row) in grid_day:
                        interval = grid_day[(col, row)]
                        rowspan = max(1, (interval['rowspan'] + time_step - 1) // time_step)  # Округляем вверх
                        
                        cell_content = (
                            f"<div class='activity-block'>"
                            f"<strong>{interval['subject'] or 'Не указано'}</strong><br>"
                            f"{interval['teacher'] or ''}<br>"
                            f"{interval['students'] or ''}<br>"
                            f"{interval['room_display'] or ''}<br>"
                            f"{minutes_to_time(interval['start'])}-{minutes_to_time(interval['end'])}"
                            f"</div>"
                        )
                        html_parts.append(
                            f'    <td rowspan="{rowspan}" style="background-color: {interval["color"]};">{cell_content}</td>'
                        )
                        occupancy[day][col] = row + (rowspan * time_step)
                    else:
                        html_parts.append("    <td></td>")
            
            html_parts.append("</tr>")
        
        html_parts.append("</tbody>")
        html_parts.append("</table>")
        html_parts.append("</body>")
        html_parts.append("</html>")

        # Собираем весь HTML в одну строку
        building_html = "\n".join(html_parts)

        # Опции для pdfkit: формат A2, горизонтальное расположение, поля 15 мм
        options = {
            'page-size': 'A2',
            'orientation': 'Landscape',
            'margin-top': '15mm',
            'margin-right': '15mm',
            'margin-bottom': '15mm',
            'margin-left': '15mm',
            'encoding': "UTF-8",
            'quiet': ''  # Подавляем вывод сообщений wkhtmltopdf
        }

        # Определяем имя выходного PDF файла (например, "Kolibri.pdf")
        output_file = os.path.join(output_dir, f"{building}.pdf")
        try:
            pdfkit.from_string(building_html, output_file, options=options)
            logger.info(f"PDF для здания {building} сохранён в {output_file}")
        except Exception as e:
            logger.error(f"Ошибка при создании PDF для здания {building}: {e}")
            import traceback
            traceback.print_exc()
            
    logger.info(f"Генерация PDF-файлов завершена. Всего создано файлов: {len([b for b in buildings if not b.startswith('_')])}")
