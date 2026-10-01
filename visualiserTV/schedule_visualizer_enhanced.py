"""
Улучшенный визуализатор расписания - основной файл
Создает PDF с визуализацией расписания из Excel-файла с дополнительными возможностями:
- Скругленные углы блоков
- Улучшенный HTML-экспорт с адаптивностью
Версия 2: поддержка разделения на два холста (Mo-Fr и Sa отдельно)
Версия 3: отключена генерация индивидуальных расписаний учителей и групп
"""

import os
import pandas as pd
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Импортируем модули проекта
from data_processor import load_data, process_schedule_data, filter_by_lesson_type
from enhanced_layout_manager import EnhancedScheduleLayout
from enhanced_export_manager import EnhancedExportManager


def main(excel_file_path, output_pdf_path, export_html=False, lesson_type_filter='group'):
    """
    Основная функция для генерации PDF с расписанием и HTML-экспорта
    
    Args:
        excel_file_path (str): Путь к Excel-файлу с расписанием
        output_pdf_path (str): Путь для сохранения PDF-файла
        export_html (bool): Экспортировать в HTML формат
    """
    print(f"Загрузка данных из {excel_file_path}...")
    
    # Загружаем данные из Excel-файла
    df = load_data(excel_file_path)
    df = filter_by_lesson_type(df, lesson_type_filter)
    
    # Обрабатываем данные расписания
    days_of_week, schedule_by_day = process_schedule_data(df)
    
    print(f"Дни недели в расписании: {', '.join(days_of_week)}")
    print(f"Всего занятий: {sum(len(schedule_by_day[day]) for day in days_of_week)}")
    
    # Создаем менеджер компоновки для расписания с улучшенным рендерингом (скругленные углы)
    layout_manager = EnhancedScheduleLayout(days_of_week, schedule_by_day)
    
    # Создаем PDF с визуализацией (версия с разделением на два холста)
    create_pdf_v2(layout_manager, output_pdf_path)
    
    print(f"PDF-файл с расписанием создан: {output_pdf_path}")
    
    # Экспорт в HTML, если выбрано
    if export_html:
        export_manager = EnhancedExportManager(days_of_week, schedule_by_day)
        html_path = os.path.splitext(output_pdf_path)[0] + ".html"
        export_manager.export_to_html(html_path)
        print(f"HTML-файл с расписанием создан: {html_path}")


def create_pdf_v2(layout_manager, output_path):
    """
    Создает PDF с визуализацией расписания, используя два холста:
    - Холст 2325×2171 пикселей для рабочих дней (Mo-Fr)
    - Холст A4 для выходных дней (Sa)
    
    Args:
        layout_manager (EnhancedScheduleLayout): Менеджер компоновки расписания
        output_path (str): Путь для сохранения PDF-файла
    """
    # Регистрируем шрифты
    try:
        pdfmetrics.registerFont(TTFont('Arial', 'Arial.ttf'))
        font_name = 'Arial'
    except:
        # Если шрифт Arial не найден, используем встроенный шрифт
        font_name = 'Helvetica'
    
    # Получаем информацию о рабочих днях и выходных
    weekdays, weekday_schedule, weekday_columns = layout_manager.get_weekday_layout_info()
    weekends, weekend_schedule, weekend_columns = layout_manager.get_weekend_layout_info()
    
    # Создаем PDF файл
    has_weekdays = bool(weekdays and weekday_schedule)
    has_weekends = bool(weekends and weekend_schedule)
    
    if not has_weekdays and not has_weekends:
        print("Нет данных для экспорта")
        return
    
    # Определяем размер первого холста
    if has_weekdays:
        # Пользовательский размер холста для рабочих дней: 2325×2171 пикселей
        weekday_canvas_size = (2325, 2171)
        # Создаем холст с пользовательским размером
        c = canvas.Canvas(output_path, pagesize=weekday_canvas_size)
        
        # Настройка полей страницы для рабочих дней (минимизируем)
        margin = 15
        content_width = weekday_canvas_size[0] - 2 * margin
        content_height = weekday_canvas_size[1] - 2 * margin
        
        # Устанавливаем заголовок для рабочих дней
        c.setFont(font_name, 24)  # Увеличен размер заголовка для большого холста
        # c.drawString(margin, weekday_canvas_size[1] - margin - 35, "Stundenplan (Mo-Fr)")
        
        # Рисуем расписание рабочих дней
        layout_manager.draw_weekday_schedule(c, margin, weekday_canvas_size[1] - margin - 50, 
                                           content_width, content_height - 50, font_name)
        
        # Добавляем информацию о дате создания
        c.setFont(font_name, 8)
        c.drawString(margin, margin - 15, f"Создано: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        
        # Если есть выходные дни, добавляем новую страницу
        if has_weekends:
            c.showPage()
    
    # Обрабатываем выходные дни (если есть)
    if has_weekends:
        if not has_weekdays:
            # Если нет рабочих дней, создаем новый холст с портретным А4
            c = canvas.Canvas(output_path, pagesize=A4)  # Portrait A4
        else:
            # Устанавливаем размер страницы для следующих страниц (портретный А4)
            c.setPageSize(A4)  # Portrait A4
        
        # Настройка для портретного A4 (минимизируем поля)
        width, height = A4  # Portrait orientation
        margin = 10  # Минимальные поля
        content_width = width - 2 * margin
        content_height = height - 2 * margin
        
        # Устанавливаем заголовок для выходных дней
        c.setFont(font_name, 18)
        # c.drawString(margin, height - margin - 30, "Stundenplan (Sa)")
        
        # Рисуем расписание выходных дней
        layout_manager.draw_weekend_schedule(c, margin, height - margin - 40, 
                                           content_width, content_height - 40, font_name)
        
        # Добавляем информацию о дате создания
        c.setFont(font_name, 8)
        c.drawString(margin, margin - 15, f"Создано: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    
    # Сохраняем PDF
    c.save()


def create_pdf(layout_manager, output_path):
    """
    Оригинальная функция создания PDF (сохранена для обратной совместимости)
    
    Args:
        layout_manager (ScheduleLayout): Менеджер компоновки расписания
        output_path (str): Путь для сохранения PDF-файла
    """
    from reportlab.lib.pagesizes import A3
    
    # Создаем PDF-холст (старая версия с A3)
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
    # c.drawString(margin, height - margin - 20, "Stundenplan")
    
    # Рисуем расписание (layout_manager сам добавит страницы при необходимости)
    layout_manager.draw_schedule(c, margin, height - margin - 50, content_width, content_height - 50, font_name)
    
    # Добавляем информацию о дате создания на последней странице
    c.setFont(font_name, 8)
    c.drawString(margin, margin - 15, f"Создано: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    
    # Сохраняем PDF
    c.save()


if __name__ == "__main__":
    # Путь к файлу расписания
    excel_file = os.path.join("..", "visualiser", "optimized_schedule.xlsx")
    # Путь для сохранения PDF
    pdf_file = "enhanced_schedule_visualization_tv.pdf"
    
    # Запускаем визуализацию только со сводным расписанием и HTML-экспортом
    main(excel_file, pdf_file, export_html=False, lesson_type_filter='group')
