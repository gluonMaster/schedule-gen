"""
Модуль для экспорта расписания групп
"""

import os
import pandas as pd
import re
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Импортируем модули проекта
from data_processor import process_schedule_data
from enhanced_layout_manager import EnhancedScheduleLayout


def export_group_schedules(excel_file_path, output_dir="group_schedules"):
    """
    Экспортирует расписание групп в отдельные PDF-файлы
    
    Args:
        excel_file_path (str): Путь к Excel-файлу с расписанием
        output_dir (str): Директория для сохранения PDF-файлов с расписаниями групп
        
    Returns:
        list: Список созданных файлов с расписанием групп
    """
    # Создаем директорию для сохранения файлов, если она не существует
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Получаем список листов в Excel-файле
    xl = pd.ExcelFile(excel_file_path)
    sheets = xl.sheet_names
    
    # Фильтруем листы, начинающиеся с "G_"
    group_sheets = [sheet for sheet in sheets if sheet.startswith("G_")]
    
    created_files = []
    
    # Для каждого листа с расписанием группы
    for sheet in group_sheets:
        try:
            # Извлекаем название группы из названия листа
            group_name = sheet[2:]  # Удаляем префикс "G_"
            
            # Загружаем данные с листа
            df = pd.read_excel(excel_file_path, sheet_name=sheet)
            
            # Проверяем, есть ли данные на листе
            if df.empty:
                print(f"Лист {sheet} не содержит данных. Пропускаем.")
                continue
            
            # Обрабатываем данные расписания
            days_of_week, schedule_by_day = process_schedule_data(df)
            
            if not days_of_week:
                print(f"Лист {sheet} не содержит данных о днях недели. Пропускаем.")
                continue
            
            # Создаем имя файла для сохранения PDF
            # Заменяем недопустимые символы в имени файла
            safe_name = re.sub(r'[\\/*?:"<>|]', "_", group_name)
            pdf_file = os.path.join(output_dir, f"{safe_name}.pdf")
            
            # Создаем менеджер компоновки для расписания
            layout_manager = EnhancedScheduleLayout(days_of_week, schedule_by_day)
            
            # Создаем PDF с визуализацией расписания группы
            create_group_pdf(layout_manager, pdf_file, group_name)
            
            print(f"Расписание для группы '{group_name}' сохранено в файле: {pdf_file}")
            created_files.append(pdf_file)
        
        except Exception as e:
            print(f"Ошибка при обработке листа {sheet}: {e}")
    
    return created_files


def create_group_pdf(layout_manager, output_path, group_name):
    """
    Создает PDF с визуализацией расписания группы
    
    Args:
        layout_manager (EnhancedScheduleLayout): Менеджер компоновки расписания
        output_path (str): Путь для сохранения PDF-файла
        group_name (str): Название группы
    """
    # Создаем PDF-холст (используем A4 для расписания группы)
    c = canvas.Canvas(output_path, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    # Пытаемся использовать Arial, если доступен
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
    
    # Устанавливаем заголовок с названием группы
    c.setFont(font_name, 18)
    c.drawString(margin, height - margin - 20, f"Расписание группы: {group_name}")
    
    # Рисуем расписание
    layout_manager.draw_schedule(c, margin, height - margin - 50, content_width, content_height - 50, font_name)
    
    # Добавляем информацию о дате создания на последней странице
    c.setFont(font_name, 8)
    c.drawString(margin, margin - 15, f"Создано: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    
    # Сохраняем PDF
    c.save()


# Если модуль запущен напрямую, выполняем экспорт расписания групп
if __name__ == "__main__":
    # Путь к файлу расписания
    excel_file = "optimized_schedule.xlsx"
    
    # Экспортируем расписание групп
    exported_files = export_group_schedules(excel_file)
    print(f"Всего экспортировано расписаний групп: {len(exported_files)}")
