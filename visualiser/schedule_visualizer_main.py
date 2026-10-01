"""
Визуализатор расписания - основной файл
Создает PDF с визуализацией расписания из Excel-файла
"""

import pandas as pd
import numpy as np
import re
from datetime import datetime, timedelta
import colorsys
import hashlib
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# Импортируем дополнительные модули
from data_processor import load_data, process_schedule_data
from color_manager import get_group_color, get_building_color
from layout_manager import ScheduleLayout


def main(excel_file_path, output_pdf_path):
    """
    Основная функция для генерации PDF с расписанием
    
    Args:
        excel_file_path (str): Путь к Excel-файлу с расписанием
        output_pdf_path (str): Путь для сохранения PDF-файла
    """
    print(f"Загрузка данных из {excel_file_path}...")
    
    # Загружаем данные из Excel-файла
    df = load_data(excel_file_path)
    
    # Обрабатываем данные расписания
    days_of_week, schedule_by_day = process_schedule_data(df)
    
    print(f"Дни недели в расписании: {', '.join(days_of_week)}")
    print(f"Всего занятий: {sum(len(schedule_by_day[day]) for day in days_of_week)}")
    
    # Создаем менеджер компоновки для расписания
    layout_manager = ScheduleLayout(days_of_week, schedule_by_day)
    
    # Создаем PDF с визуализацией
    create_pdf(layout_manager, output_pdf_path)
    
    print(f"PDF-файл с расписанием создан: {output_pdf_path}")


def create_pdf(layout_manager, output_path):
    """
    Создает PDF с визуализацией расписания
    
    Args:
        layout_manager (ScheduleLayout): Менеджер компоновки расписания
        output_path (str): Путь для сохранения PDF-файла
    """
    # Создаем PDF-холст
    c = canvas.Canvas(output_path, pagesize=landscape(A3))
    width, height = landscape(A3)
    
    # Регистрируем шрифты
    try:
        pdfmetrics.registerFont(TTFont('Arial', 'Arial.ttf'))
        font_name = 'Arial'
    except:
        # Если шрифт Arial не найден, используем встроенный шрифт
        font_name = 'Helvetica'
    
    # Настройка полей страницы
    margin = 30
    content_width = width - 2 * margin
    content_height = height - 2 * margin
    
    # Устанавливаем заголовок
    c.setFont(font_name, 18)
    #c.drawString(margin, height - margin - 20, "Stundenplan")
    
    # Рисуем расписание (layout_manager сам добавит страницы при необходимости)
    layout_manager.draw_schedule(c, margin, height - margin - 50, content_width, content_height - 50, font_name)
    
    # Добавляем информацию о дате создания на последней странице
    c.setFont(font_name, 8)
    c.drawString(margin, margin - 15, f"Создано: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    
    # Сохраняем PDF
    c.save()


if __name__ == "__main__":
    # Путь к файлу расписания
    excel_file = "optimized_schedule.xlsx"
    # Путь для сохранения PDF
    pdf_file = "schedule_visualization.pdf"
    
    main(excel_file, pdf_file)
