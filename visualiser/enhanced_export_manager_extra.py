"""
Модуль с дополнительными методами экспорта (PNG, ICS)
"""

import os
import hashlib
from datetime import datetime, timedelta
import tempfile

# Импортируем необходимые модули при наличии
try:
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.pdfgen import canvas
    PDF_EXPORT_AVAILABLE = True
except ImportError:
    PDF_EXPORT_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    PNG_EXPORT_AVAILABLE = True
except ImportError:
    PNG_EXPORT_AVAILABLE = False


class ExtraExportMixin:
    """Миксин с дополнительными методами экспорта"""
    
    def export_to_png(self, output_path, layout_manager):
        """
        Экспортирует расписание в PNG с улучшенным качеством
        
        Args:
            output_path (str): Путь для сохранения PNG-файла
            layout_manager (ScheduleLayout): Менеджер компоновки расписания
            
        Returns:
            bool: True, если экспорт успешен, иначе False
        """
        if not PNG_EXPORT_AVAILABLE:
            print("Ошибка: Для экспорта в PNG требуются дополнительные библиотеки")
            print("Установите их с помощью команды: pip install pdf2image reportlab[images]")
            return False
        
        try:
            # Создаем временный PDF-файл
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
                temp_pdf_path = temp_pdf.name
            
            # Создаем экземпляр EnhancedExportManager с тем же набором данных
            from enhanced_layout_manager import EnhancedScheduleLayout
            layout = EnhancedScheduleLayout(self.days_of_week, self.schedule_by_day)
            
            # Экспортируем расписание в PDF
            if PDF_EXPORT_AVAILABLE:
                # Создаем PDF-холст
                c = canvas.Canvas(temp_pdf_path, pagesize=landscape(A3))
                width, height = landscape(A3)
                
                # Настройка полей страницы
                margin = 20
                content_width = width - 2 * margin
                content_height = height - 2 * margin
                
                # Устанавливаем заголовок
                font_name = 'Helvetica'
                c.setFont(font_name, 18)
                #c.drawString(margin, height - margin - 20, "Stundenplan")
                
                # Рисуем расписание
                layout.draw_schedule(c, margin, height - margin - 50, content_width, content_height - 50, font_name)
                
                # Добавляем информацию о дате создания
                c.setFont(font_name, 8)
                c.drawString(margin, margin - 15, f"Создано: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
                
                # Сохраняем PDF
                c.save()
            else:
                print("Ошибка: Отсутствуют библиотеки для создания PDF")
                return False
            
            # Конвертируем PDF в PNG
            # Увеличиваем DPI для лучшего качества
            images = convert_from_path(temp_pdf_path, dpi=200)
            if images:
                images[0].save(output_path, 'PNG')
                print(f"PNG-файл сохранен: {output_path}")
                
                # Удаляем временный PDF-файл
                os.unlink(temp_pdf_path)
                
                return True
            else:
                print("Ошибка: Не удалось преобразовать PDF в PNG")
                return False
        
        except ImportError:
            print("Ошибка: Для экспорта в PNG требуется библиотека pdf2image")
            print("Установите ее с помощью команды: pip install pdf2image")
            print("Также может потребоваться установка Poppler: https://github.com/oschwartz10612/poppler-windows")
            return False
        
        except Exception as e:
            print(f"Ошибка при экспорте в PNG: {e}")
            return False

    def export_to_ics(self, output_path):
        """
        Экспортирует расписание в формат календаря ICS (iCalendar) с улучшенным форматированием
        
        Args:
            output_path (str): Путь для сохранения ICS-файла
            
        Returns:
            bool: True, если экспорт успешен, иначе False
        """
        try:
            from icalendar import Calendar, Event, vDuration, Alarm
            import pytz
            
            # Создаем календарь
            cal = Calendar()
            cal.add('prodid', '-//Schedule Visualizer Enhanced//schedulevis_enhanced.py//')
            cal.add('version', '2.0')
            cal.add('x-wr-calname', 'Stundenplan')
            cal.add('x-wr-caldesc', 'Stundenplan, созданное Визуализатором Расписаний')
            
            # Добавляем события для каждого занятия
            for day in self.days_of_week:
                if day not in self.schedule_by_day:
                    continue
                
                lessons = self.schedule_by_day[day]
                
                # Определяем день недели в числовом формате (0 - понедельник, 6 - воскресенье)
                day_mapping = {'Mo': 0, 'Di': 1, 'Mi': 2, 'Do': 3, 'Fr': 4, 'Sa': 5, 'So': 6}
                day_num = day_mapping.get(day, 0)
                
                # Получаем текущую дату
                now = datetime.now()
                
                # Находим ближайшую дату для этого дня недели
                days_ahead = day_num - now.weekday()
                if days_ahead <= 0:  # Этот день недели уже прошел на этой неделе
                    days_ahead += 7
                next_day = now + timedelta(days=days_ahead)
                
                for lesson in lessons:
                    # Создаем событие
                    event = Event()
                    
                    # Устанавливаем свойства события
                    summary = f"{lesson['subject']} - {lesson['group']}"
                    event.add('summary', summary)
                    
                    description = f"Предмет: {lesson['subject']}\n"
                    description += f"Группа: {lesson['group']}\n"
                    description += f"Преподаватель: {lesson['teacher']}\n"
                    description += f"Аудитория: {lesson['room']}, {lesson['building']}"
                    event.add('description', description)
                    
                    location = f"{lesson['room']}, {lesson['building']}"
                    event.add('location', location)
                    
                    # Время начала и окончания занятия
                    start_hour, start_minute = map(int, lesson['start_time'].split(':'))
                    end_hour, end_minute = map(int, lesson['end_time'].split(':'))
                    
                    start_time = next_day.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
                    end_time = next_day.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
                    
                    event.add('dtstart', start_time)
                    event.add('dtend', end_time)
                    
                    # Добавляем уникальный идентификатор
                    uid_string = f"{day}-{lesson['group']}-{lesson['start_time']}-{lesson['room']}"
                    uid = hashlib.md5(uid_string.encode()).hexdigest()
                    event.add('uid', uid)
                    
                    # Настраиваем повторение события каждую неделю
                    event.add('rrule', {'freq': 'weekly'})
                    
                    # Добавляем напоминание за 15 минут до начала занятия
                    alarm = Alarm()
                    alarm.add('action', 'DISPLAY')
                    alarm.add('description', f"Напоминание: {summary}")
                    alarm.add('trigger', vDuration(-timedelta(minutes=15)))
                    event.add_component(alarm)
                    
                    # Добавляем событие в календарь
                    cal.add_component(event)
            
            # Записываем календарь в файл
            with open(output_path, 'wb') as f:
                f.write(cal.to_ical())
            
            print(f"ICS-файл сохранен: {output_path}")
            return True
            
        except ImportError:
            print("Ошибка: Для экспорта в ICS требуется библиотека icalendar")
            print("Установите ее с помощью команды: pip install icalendar")
            return False
            
        except Exception as e:
            print(f"Ошибка при экспорте в ICS: {e}")
            return False
        