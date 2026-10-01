"""
Улучшенный модуль экспорта расписания
Предоставляет возможность экспорта расписания в различные форматы с улучшенным дизайном
"""

import os
from datetime import datetime

# Импортируем необходимые модули при наличии
try:
    from reportlab.lib.pagesizes import A3, A4, landscape
    from reportlab.lib.colors import Color
    PDF_EXPORT_AVAILABLE = True
except ImportError:
    PDF_EXPORT_AVAILABLE = False

try:
    from enhanced_export_manager_extra import convert_from_path
    PNG_EXPORT_AVAILABLE = True
except ImportError:
    PNG_EXPORT_AVAILABLE = False


class EnhancedExportManager:
    """Класс для экспорта расписания в различные форматы с улучшенным дизайном"""
    
    def __init__(self, days_of_week, schedule_by_day, config=None):
        """
        Инициализирует менеджер экспорта
        
        Args:
            days_of_week (list): Список дней недели
            schedule_by_day (dict): Словарь с расписанием по дням
            config (ConfigManager, optional): Менеджер настроек
        """
        self.days_of_week = days_of_week
        self.schedule_by_day = schedule_by_day
        self.config = config
        
        # Словарь для перевода дней недели
        self.day_translations = {
            'Mo': 'Montag',
            'Di': 'Dienstag',
            'Mi': 'Mittwoch',
            'Do': 'Donnerstag',
            'Fr': 'Freitag',
            'Sa': 'Samstag',
            'So': 'Sonntag'
        }
        
        # Если указан менеджер настроек, используем переводы из него
        if config:
            self.day_translations = {
                day: config.get('translations', day, default) 
                for day, default in self.day_translations.items()
            }
        
        # Параметры для разделения на подстолбцы
        self.max_pages_per_column = 2
        self.blocks_per_page = 12  # Примерное количество блоков на странице


# Импортируем миксины после определения основного класса
from enhanced_export_manager_html import HtmlExportMixin
from enhanced_export_manager_extra import ExtraExportMixin

# Создаем полную версию класса путем добавления миксинов
class FullEnhancedExportManager(EnhancedExportManager, HtmlExportMixin, ExtraExportMixin):
    """Полный класс экспорта с поддержкой HTML и других форматов"""
    pass

# Заменяем оригинальный класс на полный для удобства использования
EnhancedExportManager = FullEnhancedExportManager
