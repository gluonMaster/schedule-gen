"""
Миксин для отрисовки расписания
Содержит методы для отрисовки расписания на страницах
Версия 2: добавлена поддержка рисования для конкретных групп дней (Mo-Fr или Sa отдельно)
Версия 3: ИСПРАВЛЕН дублированный метод draw_header_with_subcolumns_for_days
"""

class LayoutDrawingMixin:
    """Миксин с методами для отрисовки расписания"""
    
    def draw_schedule(self, canvas, x, y, width, height, font_name):
        """
        Рисует расписание на PDF-холсте с разделением на страницы и подстолбцы
        Этот метод сохранен для обратной совместимости
        
        Args:
            canvas: PDF-холст
            x (float): X-координата верхнего левого угла области расписания
            y (float): Y-координата верхнего левого угла области расписания
            width (float): Ширина области расписания
            height (float): Высота области расписания
            font_name (str): Название шрифта
        """
        # Для обратной совместимости рисуем все дни
        self.draw_schedule_for_days(canvas, self.days_of_week, x, y, width, height, font_name)
    
    def draw_weekday_schedule(self, canvas, x, y, width, height, font_name):
        """
        Рисует расписание для рабочих дней (Mo-Fr) на PDF-холсте
        
        Args:
            canvas: PDF-холст
            x (float): X-координата верхнего левого угла области расписания
            y (float): Y-координата верхнего левого угла области расписания
            width (float): Ширина области расписания
            height (float): Высота области расписания
            font_name (str): Название шрифта
        """
        # Устанавливаем толщину границ для рабочих дней
        self.set_border_width_for_context(is_weekday=True)
        
        self.draw_schedule_for_days(canvas, self.weekdays, x, y, width, height, font_name)
    
    def draw_weekend_schedule(self, canvas, x, y, width, height, font_name):
        """
        Рисует расписание для выходных дней (Sa-So) на PDF-холсте
        
        Args:
            canvas: PDF-холст
            x (float): X-координата верхнего левого угла области расписания
            y (float): Y-координата верхнего левого угла области расписания
            width (float): Ширина области расписания
            height (float): Высота области расписания
            font_name (str): Название шрифта
        """
        # Устанавливаем толщину границ для выходных дней
        self.set_border_width_for_context(is_weekday=False)
        
        self.draw_schedule_for_days(canvas, self.weekends, x, y, width, height, font_name)
    
    def draw_schedule_for_days(self, canvas, target_days, x, y, width, height, font_name):
        """
        Рисует расписание для конкретного списка дней на PDF-холсте
        
        Args:
            canvas: PDF-холст
            target_days (list): Список дней для отрисовки
            x (float): X-координата верхнего левого угла области расписания
            y (float): Y-координата верхнего левого угла области расписания
            width (float): Ширина области расписания
            height (float): Высота области расписания
            font_name (str): Название шрифта
        """
        if not target_days:
            return
        
        # ВАЖНО: Определяем тип дней для использования правильных параметров
        weekday_names = {'Mo', 'Di', 'Mi', 'Do', 'Fr'}
        is_weekdays = any(day in weekday_names for day in target_days)
        
        # Устанавливаем правильные параметры для данного типа дней
        self.set_border_width_for_context(is_weekday=is_weekdays)
        
        # Вычисляем общее количество столбцов для указанных дней
        total_columns = sum(self.subcolumn_count.get(day, 1) for day in target_days)
        
        if total_columns == 0:
            return
        
        # Вычисляем ширину колонки
        column_width = width / total_columns
        
        # Вычисляем, сколько блоков занятий можно разместить на одной странице
        # Используем правильные параметры в зависимости от типа дней
        if is_weekdays:
            # Для рабочих дней используем параметры большого холста
            header_height = 35
            margin_bottom = 15
            current_block_height = self.block_height  # Рассчитанная адаптивная высота
        else:
            # Для выходных используем параметры малого холста
            header_height = 30
            margin_bottom = 10
            current_block_height = 50  # Фиксированная высота для выходных
        
        usable_height = height - header_height - margin_bottom
        
        # Используем текущий интервал, который уже установлен в set_border_width_for_context
        blocks_per_page = int(usable_height / (current_block_height + self.block_spacing))
        
        # Получаем максимальное количество блоков в подстолбце для указанных дней
        max_blocks_in_subcolumn = 0
        for day in target_days:
            if day in self.day_subcolumns:
                for subcolumn in self.day_subcolumns[day]:
                    max_blocks_in_subcolumn = max(max_blocks_in_subcolumn, len(subcolumn))
            else:
                if day in self.schedule_by_day:
                    max_blocks_in_subcolumn = max(max_blocks_in_subcolumn, len(self.schedule_by_day[day]))
        
        # Вычисляем общее количество страниц
        total_pages = max(1, (max_blocks_in_subcolumn + blocks_per_page - 1) // blocks_per_page)
        
        # Отрисовываем расписание по страницам
        for page in range(total_pages):
            if page > 0:
                # Добавляем новую страницу для всех, кроме первой
                canvas.showPage()
            
            # Верхняя позиция для начала блоков на этой странице
            start_y = y - header_height - self.block_spacing
            
            # Индекс начального и конечного блока для этой страницы
            start_idx = page * blocks_per_page
            end_idx = min((page + 1) * blocks_per_page, max_blocks_in_subcolumn)
            
            # Отрисовываем блоки занятий
            current_column_pos = 0
            
            for day in target_days:
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
                            
                            # Определяем отступы (минимизируем для лучшего использования пространства)
                            margin = 5
                            block_width = column_width - 2 * margin
                            
                            # Определяем, является ли это рабочим днем
                            is_weekday = day in weekday_names
                            print(f"DEBUG draw_schedule: day={day}, is_weekday={is_weekday}, spacing={self.block_spacing}")
                            
                            # Рисуем блок занятия со скругленными углами
                            # Передаем информацию, что это рабочий день, и используем правильную высоту
                            self.draw_lesson_block(canvas, lesson, col_x + margin, current_y, 
                                                  block_width, current_block_height, font_name, is_weekday=is_weekday)
                            
                            # Переходим к следующему блоку (вниз) с учетом текущего интервала
                            current_y -= (current_block_height + self.block_spacing)
                        
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
                            
                            # Определяем отступы (минимизируем для лучшего использования пространства)
                            margin = 5
                            block_width = column_width - 2 * margin
                            
                            # Определяем, является ли это рабочим днем
                            is_weekday = day in weekday_names
                            print(f"DEBUG draw_schedule: day={day}, is_weekday={is_weekday}, spacing={self.block_spacing}")
                            
                            # Рисуем блок занятия со скругленными углами
                            # Определяем, является ли это рабочим днем, и используем правильную высоту
                            self.draw_lesson_block(canvas, lesson, col_x + margin, current_y, 
                                                  block_width, current_block_height, font_name, is_weekday=is_weekday)
                            
                            # Переходим к следующему блоку (вниз) с учетом текущего интервала
                            current_y -= (current_block_height + self.block_spacing)
                    
                    current_column_pos += 1
            
            # Рисуем заголовки для текущей страницы
            self.draw_header_with_subcolumns_for_days(canvas, target_days, x, y, column_width, font_name)

    def draw_header_with_subcolumns_for_days(self, canvas, target_days, x, y, column_width, font_name):
        """
        Рисует заголовки дней недели с учетом подстолбцов для конкретных дней
        
        Args:
            canvas: PDF-холст
            target_days (list): Список дней для отрисовки заголовков
            x (float): X-координата начала заголовков
            y (float): Y-координата заголовков
            column_width (float): Ширина колонки
            font_name (str): Название шрифта
        """
        # ИСПРАВЛЕНО: Определяем размер шрифта в зависимости от типа дней
        # Рабочие дни (Mo-Fr) на большом холсте: 22 пункта
        # Выходные дни (Sa-So) на малом холсте: 14 пунктов
        
        # Проверяем, есть ли среди target_days рабочие дни
        weekday_names = {'Mo', 'Di', 'Mi', 'Do', 'Fr'}
        is_weekdays = any(day in weekday_names for day in target_days)
        
        header_font_size = 26 if is_weekdays else 14
        
        print(f"DEBUG: target_days={target_days}, is_weekdays={is_weekdays}, font_size={header_font_size}")
        
        canvas.setFont(font_name, header_font_size)
        
        current_column_pos = 0
        
        for day in target_days:
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