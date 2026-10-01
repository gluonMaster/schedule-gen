"""
Миксин для рендеринга блоков расписания
Содержит методы для отрисовки блоков со скругленными углами
Версия 2: улучшена адаптация размеров для разных типов холстов
"""

from color_manager import get_group_color, get_building_color, get_text_color
from lesson_label_utils import format_pdf_group_label

class BlockRenderingMixin:
    """Миксин с методами для рендеринга блоков расписания"""
    
    def draw_lesson_block(self, canvas, lesson, x, y, width, height, font_name, is_weekday=True):
        """
        Рисует блок занятия со скругленными углами
        
        Args:
            canvas: PDF-холст
            lesson (dict): Информация о занятии
            x (float): X-координата блока
            y (float): Y-координата блока (верхний край)
            width (float): Ширина блока
            height (float): Высота блока
            font_name (str): Название шрифта
            is_weekday (bool): True для рабочих дней, False для выходных
        """
        # Определяем цвета для блока
        fill_color = get_group_color(lesson['group'])
        border_color = get_building_color(lesson['building'])
        text_color = get_text_color(fill_color)
        group_label = format_pdf_group_label(lesson)
        
        # Устанавливаем цвета
        canvas.setFillColor(fill_color)
        canvas.setStrokeColor(border_color)
        canvas.setLineWidth(self.block_border_width)
        
        # Рисуем прямоугольник со скругленными углами
        self.draw_rounded_rect(canvas, x, y, width, height, self.corner_radius, fill=1, stroke=1)
        
        # Настраиваем шрифт для текста
        canvas.setFillColor(text_color)
        
        # Центр блока по горизонтали
        center_x = x + width / 2
        
        # DEBUG: Добавляем отладочную информацию
        print(f"DEBUG draw_lesson_block: is_weekday={is_weekday}, lesson={group_label or lesson.get('group', 'N/A')}")
        
        # Используем рассчитанные размеры шрифтов для рабочих дней или выходных дней
        if is_weekday and hasattr(self, 'weekday_font_size'):
            base_font_size = self.weekday_font_size
            group_font_size = self.weekday_group_font_size
            text_padding = 8
            line_spacing = 2
            print(f"DEBUG: Используется weekday font={base_font_size}")
        elif not is_weekday and hasattr(self, 'weekend_font_size'):
            base_font_size = self.weekend_font_size
            group_font_size = self.weekend_group_font_size
            text_padding = 4  # Меньше отступы для выходных
            line_spacing = 1
            print(f"DEBUG: Используется weekend font={base_font_size}")
        else:
            # Fallback для старой логики (если размеры шрифтов не рассчитаны)
            base_font_size = min(10, height / 6, width / 15)
            base_font_size = max(6, base_font_size)
            group_font_size = base_font_size + 1
            text_padding = 6
            line_spacing = 1
            print(f"DEBUG: Используется fallback font={base_font_size}, is_weekday={is_weekday}")
            print(f"DEBUG: hasattr weekday_font_size={hasattr(self, 'weekday_font_size')}")
            print(f"DEBUG: hasattr weekend_font_size={hasattr(self, 'weekend_font_size')}")
        
        # ИСПРАВЛЕНИЕ: Правильное позиционирование текста по вертикали
        # У нас есть 4 строки текста с разными размерами шрифтов
        line_heights = [base_font_size, group_font_size, base_font_size, base_font_size]
        total_lines = 4
        total_spacing = (total_lines - 1) * line_spacing
        
        # Полная высота всего текстового блока
        total_text_height = sum(line_heights) + total_spacing
        
        # Доступная высота для текста (блок минус отступы сверху и снизу)
        available_text_height = height - 2 * text_padding
        
        # Вертикально центрируем весь текстовый блок в доступной области
        # y - это верхний край блока, поэтому:
        # - сначала отступаем на text_padding от верха
        # - затем отступаем на половину свободного места для центрирования
        # - затем отступаем на высоту первой строки, чтобы получить baseline первой строки
        vertical_offset = (available_text_height - total_text_height) / 2
        start_y = y - text_padding - vertical_offset - line_heights[0]
        
        # Строка 1: Время занятия
        current_y = start_y
        canvas.setFont(font_name, base_font_size)
        time_text = f"{lesson['start_time']}-{lesson['end_time']}"
        canvas.drawCentredString(center_x, current_y, time_text)
        
        # Строка 2: Группа (жирный шрифт)
        current_y -= (line_heights[0] + line_spacing)
        bold_font = f"{font_name}-Bold"
        canvas.setFont(bold_font, group_font_size)
        group_text = self.truncate_text(group_label, width - 2 * text_padding, bold_font, group_font_size, canvas)
        canvas.drawCentredString(center_x, current_y, group_text)
        
        # Строка 3: Преподаватель
        current_y -= (line_heights[1] + line_spacing)
        canvas.setFont(font_name, base_font_size)
        teacher_text = self.truncate_text(lesson['teacher'], width - 2 * text_padding, font_name, base_font_size, canvas)
        canvas.drawCentredString(center_x, current_y, teacher_text)
        
        # Строка 4: Аудитория и здание
        current_y -= (line_heights[2] + line_spacing)
        location_text = f"{lesson['room']}, {lesson['building']}"
        location_text = self.truncate_text(location_text, width - 2 * text_padding, font_name, base_font_size, canvas)
        canvas.drawCentredString(center_x, current_y, location_text)

    def draw_rounded_rect(self, canvas, x, y, width, height, radius, fill=1, stroke=1):
        """
        Рисует прямоугольник со скруглёнными углами.
        Параметр y у нас — это верхняя граница, а для roundRect нужно y-ниж.
        """
        # ограничиваем радиус
        radius = min(radius, height/2, width/2)

        # переводим y‑коорд. из top-left в bottom-left
        bottom_y = y - height

        canvas.saveState()
        canvas.setLineWidth(self.block_border_width)
        # если нужно закрасить — используем fill, иначе только обводка
        if radius > 0:
            canvas.roundRect(x, bottom_y, width, height, radius,
                            stroke=stroke, fill=fill)
        else:
            canvas.rect(x, bottom_y, width, height,
                        stroke=stroke, fill=fill)
        canvas.restoreState()

    def truncate_text(self, text, max_width, font_name, font_size, canvas):
        """
        Обрезает текст, если он не помещается в заданную ширину
        
        Args:
            text (str): Исходный текст
            max_width (float): Максимальная ширина текста
            font_name (str): Название шрифта
            font_size (float): Размер шрифта
            canvas: PDF-холст
            
        Returns:
            str: Обрезанный текст (с многоточием, если необходимо)
        """
        if not text:
            return ""
        
        # Проверяем ширину текста
        text_width = canvas.stringWidth(text, font_name, font_size)
        
        if text_width <= max_width:
            return text
        
        # Если текст не помещается, обрезаем его
        for i in range(len(text) - 1, 0, -1):
            truncated = text[:i] + "..."
            if canvas.stringWidth(truncated, font_name, font_size) <= max_width:
                return truncated
        
        # Если даже один символ не помещается
        return text[0] + "..."
