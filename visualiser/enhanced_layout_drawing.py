"""
Миксин для отрисовки расписания
Содержит методы для отрисовки расписания на страницах
"""

class LayoutDrawingMixin:
    """Миксин с методами для отрисовки расписания"""
    
    def draw_schedule(self, canvas, x, y, width, height, font_name):
        """
        Рисует расписание на PDF-холсте с разделением на страницы и подстолбцы
        
        Args:
            canvas: PDF-холст
            x (float): X-координата верхнего левого угла области расписания
            y (float): Y-координата верхнего левого угла области расписания
            width (float): Ширина области расписания
            height (float): Высота области расписания
            font_name (str): Название шрифта
        """
        if not self.days_of_week:
            return
        
        # Вычисляем ширину колонки для каждого дня с учетом подстолбцов
        column_width = width / self.total_column_count
        
        # Вычисляем, сколько блоков занятий можно разместить на одной странице
        header_height = 30  # Высота заголовка
        margin_bottom = 50  # Отступ снизу
        usable_height = height - header_height - margin_bottom
        blocks_per_page = int(usable_height / (self.block_height + self.block_spacing))
        
        # Получаем максимальное количество блоков в одном столбце
        max_blocks_in_column = blocks_per_page * self.max_pages_per_column
        
        # Вычисляем, сколько страниц потребуется для отрисовки всего расписания
        # Ищем максимальное количество блоков в подстолбце
        max_blocks_in_subcolumn = 0
        for day in self.days_of_week:
            if day in self.day_subcolumns:
                for subcolumn in self.day_subcolumns[day]:
                    max_blocks_in_subcolumn = max(max_blocks_in_subcolumn, len(subcolumn))
            else:
                if day in self.schedule_by_day:
                    max_blocks_in_subcolumn = max(max_blocks_in_subcolumn, len(self.schedule_by_day[day]))
        
        # Вычисляем общее количество страниц
        total_pages = (max_blocks_in_subcolumn + blocks_per_page - 1) // blocks_per_page
        
        # Отрисовываем расписание по страницам
        for page in range(total_pages):
            if page > 0:
                # Добавляем новую страницу для всех, кроме первой
                canvas.showPage()
                # Устанавливаем заголовок на каждой странице
                canvas.setFont(font_name, 18)
                #canvas.drawString(x, y, "Stundenplan")
            
            # Верхняя позиция для начала блоков на этой странице
            start_y = y - header_height - self.block_spacing
            
            # Индекс начального и конечного блока для этой страницы
            start_idx = page * blocks_per_page
            end_idx = min((page + 1) * blocks_per_page, max_blocks_in_subcolumn)
            
            # Отрисовываем заголовки дней недели и их подстолбцы
            #self.draw_header_with_subcolumns(canvas, x, y, column_width, font_name)
            
            # Отрисовываем блоки занятий
            current_column_pos = 0
            
            for day in self.days_of_week:
                # Определяем количество подстолбцов для этого дня
                subcolumn_count = self.subcolumn_count.get(day, 1)
                
                if day in self.day_subcolumns:
                    # Если день разделен на подстолбцы, отрисовываем каждый подстолбец
                    for subcolumn_idx, subcolumn in enumerate(self.day_subcolumns[day]):
                        col_x = x + current_column_pos * column_width
                        
                        # Отрисовываем блоки только для текущей страницы
                        current_y = start_y
                        
                        # Проходим по блокам для текущей страницы
                        for i in range(start_idx, min(end_idx, len(subcolumn))):
                            lesson = subcolumn[i]
                            
                            # Определяем отступы
                            margin = 10
                            block_width = column_width - 2 * margin
                            
                            # Рисуем блок занятия со скругленными углами
                            self.draw_lesson_block(canvas, lesson, col_x + margin, current_y, 
                                                  block_width, self.block_height, font_name)
                            
                            # Переходим к следующему блоку (вниз)
                            current_y -= (self.block_height + self.block_spacing)
                        
                        current_column_pos += 1
                else:
                    # Если день не разделен, отрисовываем все блоки в одном столбце
                    col_x = x + current_column_pos * column_width
                    
                    if day in self.schedule_by_day:
                        lessons = sorted(self.schedule_by_day[day], key=lambda l: l['start_time_mins'])
                        
                        # Отрисовываем только блоки для текущей страницы
                        current_y = start_y
                        
                        # Проходим по блокам для текущей страницы
                        for i in range(start_idx, min(end_idx, len(lessons))):
                            lesson = lessons[i]
                            
                            # Определяем отступы
                            margin = 10
                            block_width = column_width - 2 * margin
                            
                            # Рисуем блок занятия со скругленными углами
                            self.draw_lesson_block(canvas, lesson, col_x + margin, current_y, 
                                                  block_width, self.block_height, font_name)
                            
                            # Переходим к следующему блоку (вниз)
                            current_y -= (self.block_height + self.block_spacing)
                    
                    current_column_pos += 1

            self.draw_header_with_subcolumns(canvas, x, y, column_width, font_name)

    def draw_header_with_subcolumns(self, canvas, x, y, column_width, font_name):
        """
        Рисует заголовки дней недели с учетом подстолбцов
        
        Args:
            canvas: PDF-холст
            x (float): X-координата начала заголовков
            y (float): Y-координата заголовков
            column_width (float): Ширина колонки
            font_name (str): Название шрифта
        """
        canvas.setFont(font_name, 14)
        
        current_column_pos = 0
        
        for day in self.days_of_week:
            # Определяем количество подстолбцов для этого дня
            subcolumn_count = self.subcolumn_count.get(day, 1)
            
            # Получаем переведенное название дня или используем оригинальное
            day_name = self.day_translations.get(day, day)
            
            if subcolumn_count > 1:
                # Если у дня есть подстолбцы, для каждого делаем отдельный заголовок
                for i in range(subcolumn_count):
                    col_x = x + (current_column_pos + i) * column_width + column_width / 2
                    header_text = f"{day_name} ({i+1}/{subcolumn_count})"
                    canvas.drawCentredString(col_x, y, header_text)
                
                current_column_pos += subcolumn_count
            else:
                # Если только один столбец, рисуем обычный заголовок
                col_x = x + current_column_pos * column_width + column_width / 2
                canvas.drawCentredString(col_x, y, day_name)
                current_column_pos += 1