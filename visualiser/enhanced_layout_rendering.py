"""
Миксин для рендеринга блоков расписания
Содержит методы для отрисовки блоков со скругленными углами
"""

from color_manager import get_group_color, get_building_color, get_text_color
from lesson_label_utils import format_pdf_group_label, label_text_or_empty, should_show_subject_line


class BlockRenderingMixin:
    """Миксин с методами для рендеринга блоков расписания"""
    
    def draw_lesson_block(self, canvas, lesson, x, y, width, height, font_name):
        """
        Рисует блок занятия со скругленными углами
        
        Args:
            canvas: PDF-холст
            lesson (dict): Информация о занятии
            x (float): X-координата блока
            y (float): Y-координата блока
            width (float): Ширина блока
            height (float): Высота блока
            font_name (str): Название шрифта
        """
        # Определяем цвета для блока
        group_val = label_text_or_empty(lesson.get('group', ''))
        building_val = label_text_or_empty(lesson.get('building', ''))
        teacher_val = label_text_or_empty(lesson.get('teacher', ''))
        room_val = label_text_or_empty(lesson.get('room', ''))
        subject_val_pdf = label_text_or_empty(lesson.get('subject', ''))
        group_val_pdf = format_pdf_group_label(lesson)
        start_time = label_text_or_empty(lesson.get('start_time', ''))
        end_time = label_text_or_empty(lesson.get('end_time', ''))

        fill_color = get_group_color(group_val)
        border_color = get_building_color(building_val)
        text_color = get_text_color(fill_color)
        
        # Устанавливаем цвета
        canvas.setFillColor(fill_color)
        canvas.setStrokeColor(border_color)
        canvas.setLineWidth(self.block_border_width)
        
        # Рисуем прямоугольник со скругленными углами
        self.draw_rounded_rect(canvas, x, y, width, height, self.corner_radius, fill=1, stroke=1)
        
        # Настраиваем шрифт для текста
        canvas.setFillColor(text_color)
        
        # Отступ для текста внутри блока
        text_padding = 3
        text_x = x + text_padding
        text_y = y - text_padding

        # центр блока по горизонтали
        center_x = x + width / 2
        max_width = width - 2 * text_padding

        # Вычисляем размер шрифта в зависимости от высоты блока
        pdf_lesson = dict(lesson, group=group_val_pdf)
        has_subject_line = should_show_subject_line(pdf_lesson)

        if has_subject_line:
            font_size = min(9, height / 7)
        else:
            font_size = min(10, height / 6)
        line_height = font_size + 1
        
        # Рисуем время занятия
        canvas.setFont(font_name, font_size)
        time_text = f"{start_time}-{end_time}"
        canvas.drawCentredString(center_x, text_y - line_height, time_text)

        current_line = 2
        if has_subject_line:
            canvas.setFont(font_name, font_size)
            subject_text = self.truncate_text(subject_val_pdf, max_width, font_name, font_size, canvas)
            canvas.drawCentredString(center_x, text_y - current_line * line_height, subject_text)
            current_line += 1

        # Рисуем группу
        bold_font = f"{font_name}-Bold"
        canvas.setFont(bold_font, font_size + 1)
        group_text = self.truncate_text(group_val_pdf, max_width, font_name, font_size + 1, canvas)
        canvas.drawCentredString(center_x, text_y - current_line * line_height, group_text)
        current_line += 1
        
        # Рисуем преподавателя
        canvas.setFont(font_name, font_size)
        teacher_text = self.truncate_text(teacher_val, max_width, font_name, font_size, canvas)
        canvas.drawCentredString(center_x, text_y - current_line * line_height, teacher_text)
        current_line += 1
        
        # Рисуем аудиторию и здание
        location_text = f"{room_val}, {building_val}"
        location_text = self.truncate_text(location_text, max_width, font_name, font_size, canvas)
        canvas.drawCentredString(center_x, text_y - current_line * line_height, location_text)

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
