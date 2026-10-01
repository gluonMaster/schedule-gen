"""
Улучшенный модуль управления компоновкой расписания
Содержит классы и функции для расчета позиций и отрисовки блоков расписания со скругленными углами
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
        
        # Толщина линии границы блока
        self.block_border_width = 4.0
        
        # Радиус скругления углов блоков
        self.corner_radius = 6
        
        # Максимальное количество страниц для одного столбца (если больше, делим на подстолбцы)
        self.max_pages_per_column = 2
        
        # Отступ между блоками
        self.block_spacing = 6
        
        # Проанализируем и подготовим данные для разделения на подстолбцы
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
    
    def analyze_column_distribution(self):
        """
        Анализирует распределение блоков по дням недели 
        и определяет необходимость разделения на подстолбцы
        """
        # Словарь для хранения подстолбцов для каждого дня недели
        self.day_subcolumns = {}
        
        # Словарь для хранения количества подстолбцов для каждого дня
        self.subcolumn_count = {}
        
        # Получаем максимальное количество блоков в одном дне
        for day in self.days_of_week:
            if day in self.schedule_by_day:
                lessons = sorted(self.schedule_by_day[day], key=lambda l: l['start_time_mins'])
                
                # Если количество блоков превышает порог для 2 страниц, создаем подстолбцы
                blocks_per_page = 12  # Примерное количество блоков на странице
                pages_needed = (len(lessons) + blocks_per_page - 1) // blocks_per_page
                
                if pages_needed > self.max_pages_per_column:
                    # Вычисляем количество необходимых подстолбцов
                    subcolumns_needed = (pages_needed + self.max_pages_per_column - 1) // self.max_pages_per_column
                    self.subcolumn_count[day] = subcolumns_needed
                    
                    # Распределяем блоки по подстолбцам
                    blocks_per_subcolumn = (len(lessons) + subcolumns_needed - 1) // subcolumns_needed
                    
                    # Создаем подстолбцы и распределяем блоки
                    self.day_subcolumns[day] = []
                    for i in range(subcolumns_needed):
                        start_idx = i * blocks_per_subcolumn
                        end_idx = min((i + 1) * blocks_per_subcolumn, len(lessons))
                        self.day_subcolumns[day].append(lessons[start_idx:end_idx])
                else:
                    # Если подстолбцы не нужны, используем 1 столбец
                    self.subcolumn_count[day] = 1
        
        # Вычисляем общее количество столбцов с учетом подстолбцов
        self.total_column_count = sum(self.subcolumn_count.get(day, 1) for day in self.days_of_week)


# Импортируем миксины после определения базового класса
from enhanced_layout_drawing import LayoutDrawingMixin
from enhanced_layout_rendering import BlockRenderingMixin

# Объединяем функциональность через наследование
class FullEnhancedScheduleLayout(EnhancedScheduleLayout, LayoutDrawingMixin, BlockRenderingMixin):
    """Полный класс управления компоновкой с функциями отрисовки и рендеринга блоков"""
    pass

# Заменяем исходный класс на полный для удобства использования
EnhancedScheduleLayout = FullEnhancedScheduleLayout