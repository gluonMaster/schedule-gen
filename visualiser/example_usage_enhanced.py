"""Example usage for the enhanced schedule visualizer."""

import os
import sys
from schedule_visualizer_enhanced import main
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# Register the bold font once at startup.
pdfmetrics.registerFont(TTFont('Arial-Bold', 'c:\\Windows\\Fonts\\arialbd.ttf'))

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Generate schedule visualization')
    parser.add_argument(
        '--lesson-type',
        default='all',
        choices=['all', 'group', 'individual', 'nachhilfe', 'trial', 'non-group'],
        help='Filter lessons by type (default: all)'
    )
    args = parser.parse_args()

    # Path to the Excel file with the schedule
    excel_file = "optimized_schedule.xlsx"

    if not os.path.exists(excel_file):
        print(f"Ошибка: Файл {excel_file} не найден.")
        print("Пожалуйста, убедитесь, что файл с расписанием находится в текущей директории.")
        sys.exit(1)

    pdf_file = "enhanced_schedule_visualization.pdf"

    try:
        main(excel_file, pdf_file, export_teachers=True, export_groups=True, export_html=True,
             lesson_type_filter=args.lesson_type)

        print(f"\nРасписание успешно визуализировано с улучшениями:")
        print(f"1. Основное расписание: {pdf_file}")
        print(f"2. HTML-версия: {os.path.splitext(pdf_file)[0] + '.html'}")
        print("3. Расписания преподавателей: папка 'teacher_schedules/'")
        print("4. Расписания групп: папка 'group_schedules/'")

        print("\nУлучшения включают:")
        print("- Блоки со скругленными углами")
        print("- Адаптивный HTML с поддержкой мобильных устройств")
        print("- Темная тема и возможность поиска в HTML-версии")
        print("- Отдельные PDF-файлы для каждого преподавателя и группы")

    except Exception as e:
        print(f"Ошибка при создании визуализации: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
