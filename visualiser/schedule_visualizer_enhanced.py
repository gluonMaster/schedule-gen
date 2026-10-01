"""
Улучшенный визуализатор расписания - основной файл
Создает PDF с визуализацией расписания из Excel-файла с дополнительными возможностями:
- Скругленные углы блоков
- Экспорт расписаний преподавателей/групп
- Улучшенный HTML-экспорт с адаптивностью
"""

import os
import pandas as pd
from datetime import datetime
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Импортируем модули проекта
from data_processor import load_data, process_schedule_data, filter_by_lesson_type
from enhanced_layout_manager import EnhancedScheduleLayout
from teacher_exporter import export_teacher_schedules
from group_exporter import export_group_schedules
from enhanced_export_manager import EnhancedExportManager


def main(excel_file_path, output_pdf_path, export_teachers=False, export_groups=False, export_html=False,
         lesson_type_filter='all'):
    """
    Основная функция для генерации PDF с расписанием и дополнительными экспортами

    Args:
        excel_file_path (str): Путь к Excel-файлу с расписанием
        output_pdf_path (str): Путь для сохранения PDF-файла
        export_teachers (bool): Экспортировать расписание преподавателей
        export_groups (bool): Экспортировать расписание групп
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

    # Создаем PDF с визуализацией
    create_pdf(layout_manager, output_pdf_path)

    print(f"PDF-файл с расписанием создан: {output_pdf_path}")

    # Экспорт расписания преподавателей, если выбрано
    if export_teachers:
        teacher_files = export_teacher_schedules(excel_file_path, lesson_type_filter=lesson_type_filter)
        print(f"Создано расписаний преподавателей: {len(teacher_files)}")

    # Экспорт расписания групп, если выбрано
    if export_groups:
        group_files = export_group_schedules(excel_file_path, lesson_type_filter=lesson_type_filter)
        print(f"Создано расписаний групп: {len(group_files)}")

    # Экспорт в HTML, если выбрано
    if export_html:
        export_manager = EnhancedExportManager(days_of_week, schedule_by_day)
        html_path = os.path.splitext(output_pdf_path)[0] + ".html"
        if not export_manager.export_to_html(html_path):
            raise RuntimeError('HTML export failed; do not publish the previous artifact')
        print(f"HTML-файл с расписанием создан: {html_path}")


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
    pdf_file = "enhanced_schedule_visualization.pdf"

    # Запускаем визуализацию с включенными опциями экспорта
    main(excel_file, pdf_file, export_teachers=True, export_groups=True, export_html=True)
