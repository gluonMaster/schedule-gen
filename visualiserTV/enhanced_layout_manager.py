"""
Улучшенный модуль управления компоновкой расписания
Содержит классы и функции для расчета позиций и отрисовки блоков расписания со скругленными углами
Версия 2: добавлена поддержка разделения дней на группы (Mo-Fr и Sa отдельно)
Версия 3: адаптивная толщина границ блоков
"""
from color_manager import initialize_group_colors, initialize_building_colors

class EnhancedScheduleLayout:
    """Улучшенный класс для управления компоновкой расписания со скругленными углами"""
    
    def __init__(self, days_of_week, schedule_by_day):
        """
        Инициализирует менеджер компоновки
        
        Args:
            days_of_week (list): Список дней недели
            schedule_by_day (dict): Словарь с расписанием по дням
        """
        self.days_of_week = days_of_week
        self.schedule_by_day = schedule_by_day
        self.day_translations = {
            'Mo': 'Montag',
            'Di': 'Dienstag',
            'Mi': 'Mittwoch',
            'Do': 'Donnerstag',
            'Fr': 'Freitag',
            'Sa': 'Samstag',
            'So': 'Sonntag'
        }
        
        # Фиксированная высота блока занятия (в пикселях)
        self.block_height = 57
        
        # Адаптивная толщина линии границы блока
        # Будет установлена в методах анализа для каждого типа дней
        self.weekday_border_width = 6.0   # Для рабочих дней (большой холст)
        self.weekend_border_width = 4.0   # Для выходных дней (малый холст)
        
        # Адаптивный отступ между блоками
        self.weekday_block_spacing = 10   # Для рабочих дней (+4 пикселя к базовому)
        self.weekend_block_spacing = 6    # Для выходных дней (без изменений)
        
        # Текущие значения (будут переключаться при отрисовке)
        self.block_border_width = 4.0
        self.block_spacing = 6
        
        # Радиус скругления углов блоков
        self.corner_radius = 6
        
        # Максимальное количество страниц для одного столбца (если больше, делим на подстолбцы)
        self.max_pages_per_column = 2
        
        # Группировка дней: рабочие дни (Mo-Fr) и выходные (Sa-So)
        self.weekdays = [day for day in self.days_of_week if day in ['Mo', 'Di', 'Mi', 'Do', 'Fr']]
        self.weekends = [day for day in self.days_of_week if day in ['Sa', 'So']]
        
        # Проанализируем и подготовим данные для разделения на подстолбцы
        # Для рабочих дней и выходных отдельно
        self.analyze_column_distribution()

        # Инициализируем палитру «группы → цвет» заранее
        all_groups = {
            lesson['group']
            for lessons in self.schedule_by_day.values()
            for lesson in lessons
        }
        initialize_group_colors(all_groups)

        # 2) палитра для зданий
        all_buildings = {
            lesson['building']
            for lessons in self.schedule_by_day.values()
            for lesson in lessons
        }
        initialize_building_colors(all_buildings)

        from reportlab.lib.colors import Color
        from color_manager import BUILDING_COLOR_CACHE

        col = BUILDING_COLOR_CACHE.get('Villa')
        if col:
            # умножаем RGB на 0.8 — делаем цвет на 20% темнее
            BUILDING_COLOR_CACHE['Villa'] = Color(col.red * 0.8,
                                                col.green * 0.8,
                                                col.blue * 0.8)
    
    def set_border_width_for_context(self, is_weekday=True):
        """
        Устанавливает толщину границ блоков и интервалы в зависимости от контекста
        
        Args:
            is_weekday (bool): True для рабочих дней, False для выходных
        """
        if is_weekday:
            self.block_border_width = self.weekday_border_width
            self.block_spacing = self.weekday_block_spacing
            print(f"DEBUG: Установлены параметры для рабочих дней: границы={self.block_border_width}, интервал={self.block_spacing}")
        else:
            self.block_border_width = self.weekend_border_width
            self.block_spacing = self.weekend_block_spacing
            print(f"DEBUG: Установлены параметры для выходных: границы={self.block_border_width}, интервал={self.block_spacing}")
    
    def analyze_column_distribution(self):
        """
        Анализирует распределение блоков по дням недели 
        и определяет необходимость разделения на подстолбцы
        Для рабочих дней и выходных отдельно
        """
        # Словарь для хранения подстолбцов для каждого дня недели
        self.day_subcolumns = {}
        
        # Словарь для хранения количества подстолбцов для каждого дня
        self.subcolumn_count = {}
        
        # Анализируем рабочие дни (Mo-Fr) с умным расчетом высоты блоков
        self._analyze_weekdays_smart()
        
        # Анализируем выходные дни (Sa-So) с принудительным размещением на одной странице
        self._analyze_weekends_single_page()
        
        # Вычисляем общее количество столбцов с учетом подстолбцов для каждой группы дней
        self.weekday_column_count = sum(self.subcolumn_count.get(day, 1) for day in self.weekdays)
        self.weekend_column_count = sum(self.subcolumn_count.get(day, 1) for day in self.weekends)
    
    def _analyze_weekdays_smart(self):
        """
        Умный анализ рабочих дней с расчетом оптимальной высоты блоков
        1) Находим день с максимальным количеством уроков среди Mo-Fr
        2) Определяем максимально возможную высоту блока
        3) Рассчитываем оптимальный размер шрифта
        """
        # Находим максимальное количество уроков среди рабочих дней
        max_lessons_count = 0
        for day in self.weekdays:
            if day in self.schedule_by_day:
                lessons_count = len(self.schedule_by_day[day])
                max_lessons_count = max(max_lessons_count, lessons_count)
        
        if max_lessons_count == 0:
            # Нет уроков в рабочие дни
            for day in self.weekdays:
                self.subcolumn_count[day] = 1
            return
        
        # Параметры холста для рабочих дней (2325×2171)
        canvas_height = 2171
        
        # Минимизируем поля (расписание не будет распечатываться)
        header_height = 35  # Высота заголовка
        margin_top = 15     # Минимальное верхнее поле
        margin_bottom = 15  # Минимальное нижнее поле
        
        # Полезная высота для блоков
        usable_height = canvas_height - header_height - margin_top - margin_bottom
        
        # Рассчитываем максимально возможную высоту блока
        # Учитываем увеличенные отступы между блоками для рабочих дней
        total_spacing = (max_lessons_count - 1) * self.weekday_block_spacing
        available_height_for_blocks = usable_height - total_spacing
        
        # Максимальная высота одного блока
        max_block_height = available_height_for_blocks / max_lessons_count
        
        # Добавляем запас безопасности 8% для гарантированного размещения на одной странице
        # Увеличен с 6% до 8% для компенсации увеличенных интервалов между блоками
        safety_margin = 0.08  # 8% запас
        max_block_height = max_block_height * (1 - safety_margin)
        
        # Устанавливаем разумные ограничения
        min_block_height = 45  # Минимум для читаемости
        max_reasonable_height = 150  # Максимум для эстетики
        
        self.block_height = max(min_block_height, min(max_block_height, max_reasonable_height))
        
        print(f"Рабочие дни: макс. уроков={max_lessons_count}, высота блока={self.block_height:.1f} (с запасом {safety_margin*100}%, интервал={self.weekday_block_spacing}px)")
        
        # Рассчитываем оптимальный размер шрифта для блоков рабочих дней
        self._calculate_font_sizes_for_weekdays()
        
        # Для рабочих дней не используем подстолбцы, так как мы адаптировали высоту блоков
        # Все дни рабочей недели помещаются в один столбец
        for day in self.weekdays:
            self.subcolumn_count[day] = 1
    
    def _calculate_font_sizes_for_weekdays(self):
        """
        Рассчитывает оптимальные размеры шрифтов для блоков рабочих дней
        Учитывает 4 строки текста и необходимые отступы
        """
        # В блоке 4 строки текста:
        # 1. Время (время-время)
        # 2. Группа (жирный)
        # 3. Преподаватель
        # 4. Аудитория и здание
        
        text_padding = 8  # Отступ текста от края блока (сверху и снизу)
        line_spacing = 2  # Межстрочный интервал
        
        # Доступная высота для текста
        available_text_height = self.block_height - 2 * text_padding
        
        # Высота для 4 строк с учетом межстрочных интервалов
        total_line_spacing = 3 * line_spacing  # 3 интервала между 4 строками
        available_for_text_lines = available_text_height - total_line_spacing
        
        # Средняя высота одной строки
        average_line_height = available_for_text_lines / 4
        
        # Размер шрифта примерно равен 70-80% от высоты строки
        base_font_size = average_line_height * 0.75
        
        # Увеличиваем размер шрифта на 30% согласно требованию
        base_font_size *= 1.3
        
        # Устанавливаем разумные ограничения
        min_font_size = 8
        max_font_size = 22
        
        self.weekday_font_size = max(min_font_size, min(base_font_size, max_font_size))
        
        # Размер жирного шрифта для группы (чуть больше)
        self.weekday_group_font_size = min(self.weekday_font_size + 1, max_font_size)
        
        # Размер шрифта для субботы (в 2 раза меньше чем для рабочих дней)
        # Убираем ограничение min_font_size для выходных, чтобы действительно видеть изменения
        self.weekend_font_size = self.weekday_font_size / 2.3
        self.weekend_group_font_size = self.weekday_group_font_size / 2.3
        
        # Устанавливаем разумное минимальное ограничение только если значение слишком мало
        if self.weekend_font_size < 4:
            self.weekend_font_size = 4
        if self.weekend_group_font_size < 4:
            self.weekend_group_font_size = 4
        
        print(f"Шрифты: рабочие дни={self.weekday_font_size:.1f}, группа={self.weekday_group_font_size:.1f}")
        print(f"Шрифты: выходные={self.weekend_font_size:.1f}, группа={self.weekend_group_font_size:.1f}")
    
    def _analyze_weekends_single_page(self):
        """
        Анализирует выходные дни с принудительным размещением на одной странице А4 (портрет)
        Делит столбцы на столько подстолбцов, сколько необходимо
        """
        # Параметры вертикального А4
        # Примерные размеры страницы A4 в portrait: 595×842 пикселей
        page_width = 595
        page_height = 842
        
        # Минимизируем поля
        header_height = 30  # Высота заголовка
        margin_top = 10     # Минимальное верхнее поле
        margin_bottom = 10  # Минимальное нижнее поле
        margin_left = 10    # Минимальное левое поле
        margin_right = 10   # Минимальное правое поле
        
        # Полезная высота и ширина
        usable_height = page_height - header_height - margin_top - margin_bottom
        usable_width = page_width - margin_left - margin_right
        
        # Минимальная ширина колонки для читаемости
        min_column_width = 100
        
        # Максимальное количество колонок, которые поместятся по ширине
        max_columns = int(usable_width / min_column_width)
        
        # Высота блока для выходных (фиксированная)
        weekend_block_height = 55
        weekend_block_spacing = 4
        
        # Количество блоков, которое поместится в одну колонку по высоте
        # Учитываем все отступы более точно
        total_spacing_per_column = lambda n: (n - 1) * weekend_block_spacing if n > 0 else 0
        
        # Находим максимальное количество блоков, которое может поместиться в колонке
        max_blocks_per_column = 0
        for n in range(1, 100):  # Проверяем от 1 до 99 блоков
            required_height = n * weekend_block_height + total_spacing_per_column(n)
            if required_height <= usable_height:
                max_blocks_per_column = n
            else:
                break
        
        print(f"Суббота: полезная высота={usable_height}, макс. блоков в колонке={max_blocks_per_column}")
        
        # Анализируем каждый выходной день
        for day in self.weekends:
            if day in self.schedule_by_day:
                lessons = sorted(self.schedule_by_day[day], key=lambda l: l['start_time_mins'])
                total_lessons = len(lessons)
                
                if total_lessons == 0:
                    self.subcolumn_count[day] = 1
                    continue
                
                # Вычисляем необходимое количество подстолбцов
                required_columns = (total_lessons + max_blocks_per_column - 1) // max_blocks_per_column
                
                # Ограничиваем максимальным количеством колонок, которые поместятся по ширине
                actual_columns = min(required_columns, max_columns)
                
                print(f"{day}: уроков={total_lessons}, требуется колонок={required_columns}, фактически={actual_columns}")
                
                self.subcolumn_count[day] = actual_columns
                
                # Создаем подстолбцы и распределяем блоки
                if actual_columns > 1:
                    self.day_subcolumns[day] = []
                    blocks_per_subcolumn = (total_lessons + actual_columns - 1) // actual_columns
                    
                    for i in range(actual_columns):
                        start_idx = i * blocks_per_subcolumn
                        end_idx = min((i + 1) * blocks_per_subcolumn, total_lessons)
                        if start_idx < total_lessons:
                            self.day_subcolumns[day].append(lessons[start_idx:end_idx])
                else:
                    self.subcolumn_count[day] = 1
            else:
                self.subcolumn_count[day] = 1
    
    def get_weekday_layout_info(self):
        """
        Возвращает информацию о компоновке для рабочих дней
        
        Returns:
            tuple: (список дней, словарь расписания, подстолбцы, количество столбцов)
        """
        weekday_schedule = {day: self.schedule_by_day[day] for day in self.weekdays if day in self.schedule_by_day}
        return self.weekdays, weekday_schedule, self.weekday_column_count
    
    def get_weekend_layout_info(self):
        """
        Возвращает информацию о компоновке для выходных дней
        
        Returns:
            tuple: (список дней, словарь расписания, подстолбцы, количество столбцов)
        """
        weekend_schedule = {day: self.schedule_by_day[day] for day in self.weekends if day in self.schedule_by_day}
        return self.weekends, weekend_schedule, self.weekend_column_count


# Импортируем миксины после определения базового класса
from enhanced_layout_drawing import LayoutDrawingMixin
from enhanced_layout_rendering import BlockRenderingMixin

# Объединяем функциональность через наследование
class FullEnhancedScheduleLayout(EnhancedScheduleLayout, LayoutDrawingMixin, BlockRenderingMixin):
    """Полный класс управления компоновкой с функциями отрисовки и рендеринга блоков"""
    pass

# Заменяем исходный класс на полный для удобства использования
EnhancedScheduleLayout = FullEnhancedScheduleLayout