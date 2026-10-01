#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис для работы с цветами в системе расписания.
Централизует всю логику генерации, валидации и обработки цветов.
"""

import hashlib
import re
import logging
from typing import Dict, List, Tuple, Optional

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('color_service')


class ColorService:
    """
    Сервис для работы с цветами в системе расписания.
    
    Предоставляет функциональность для:
    - Генерации цветов для групп студентов
    - Определения контрастности цветов
    - Валидации цветовых значений
    - Преобразования между цветовыми форматами
    """
    
    # Глобальный словарь для сопоставления отдельных аббревиатур с объединённым ключом
    COMPOUND_MAPPING = {
        "2a": "2a+4c",
        "4c": "2a+4c"
        # Можно добавить больше маппингов по мере необходимости
    }
    
    # Специальные категории с базовыми цветами
    SPECIAL_CATEGORIES = {
        "schach": "#ff66cc",    # Розовый для шахмат
        "tanz": "#66ccff",      # Голубой для танцев
        "gitarre": "#ffcc66",   # Желтый для гитары
        "deutsch": "#66cc66"    # Зеленый для немецкого языка
    }
    
    # Паттерн для поиска аббревиатур групп
    GROUP_PATTERN = r'\b((?:\d{1,2}[abcdeg])|(?:[34]j[abc])|(?:4-5j)|(?:5-6j))\b'
    
    # Порог яркости для определения светлых/темных цветов (от 0 до 1)
    BRIGHTNESS_THRESHOLD = 0.55
    
    @classmethod
    def get_color_for_group(cls, group: str) -> str:
        """
        Возвращает цвет в формате '#RRGGBB' для заданной группы.
        
        Алгоритм:
        1. Проверяет специальные категории (schach, tanz, etc.)
        2. Извлекает аббревиатуры из названия группы
        3. Формирует канонический ключ
        4. Генерирует цвет на основе MD5-хэша
        
        Args:
            group (str): Название группы
            
        Returns:
            str: Цвет в формате '#RRGGBB'
        """
        if not group:
            logger.debug("Пустое название группы, возвращаем серый цвет по умолчанию")
            return "#CCCCCC"  # Дефолтный серый для пустых групп
        
        group_lower = str(group).lower()
        logger.debug(f"Генерация цвета для группы: {group}")

        # Обработка специальных категорий
        for keyword, base_color in cls.SPECIAL_CATEGORIES.items():
            if keyword in group_lower:
                logger.debug(f"Найдена специальная категория: {keyword}")
                return cls._generate_special_category_color(str(group), base_color)

        # Извлечение аббревиатур из названия группы
        matches = re.findall(cls.GROUP_PATTERN, group_lower)
        unique_matches = list(set(matches))  # Убираем дубликаты
        
        if unique_matches:
            canonical_key = cls._build_canonical_key(unique_matches, group)
            logger.debug(f"Канонический ключ для группы {group}: {canonical_key}")
        else:
            canonical_key = str(group)
            logger.debug(f"Аббревиатуры не найдены, используем полное название: {canonical_key}")

        # Генерация цвета на основе MD5-хэша канонического ключа
        color = cls._generate_hash_based_color(canonical_key)
        logger.debug(f"Сгенерированный цвет для {group}: {color}")
        
        return color
    
    @classmethod
    def _generate_special_category_color(cls, group: str, base_color: str) -> str:
        """
        Генерирует вариацию цвета для специальной категории.
        
        Args:
            group (str): Название группы
            base_color (str): Базовый цвет в формате '#RRGGBB'
            
        Returns:
            str: Вариация цвета в формате '#RRGGBB'
        """
        hash_val = int(hashlib.md5(group.encode()).hexdigest(), 16)
        offset = (hash_val % 41) - 20  # смещение от -20 до +20
        
        # Парсим базовый цвет
        base = base_color.lstrip('#')
        r = max(0, min(255, int(base[0:2], 16) + offset))
        g = max(0, min(255, int(base[2:4], 16) + offset))
        b = max(0, min(255, int(base[4:6], 16) + offset))
        
        return '#{:02x}{:02x}{:02x}'.format(r, g, b)
    
    @classmethod
    def _build_canonical_key(cls, matches: List[str], group: str) -> str:
        """
        Строит канонический ключ для генерации цвета.
        
        Args:
            matches (List[str]): Список найденных аббревиатур
            group (str): Оригинальное название группы
            
        Returns:
            str: Канонический ключ для генерации цвета
        """
        # Если в названии явно присутствует '+', или найдено >1 совпадение,
        # формируем составной ключ как объединение всех аббревиатур.
        if '+' in group or len(matches) > 1:
            canonical_key = '+'.join(sorted(matches))
        else:
            canonical_key = matches[0]
            # Если для найденной аббревиатуры определён объединённый ключ – использовать его.
            if canonical_key in cls.COMPOUND_MAPPING:
                canonical_key = cls.COMPOUND_MAPPING[canonical_key]
                
        return canonical_key
    
    @classmethod
    def _generate_hash_based_color(cls, key: str) -> str:
        """
        Генерирует цвет на основе MD5-хэша ключа.
        
        Args:
            key (str): Ключ для генерации цвета
            
        Returns:
            str: Цвет в формате '#RRGGBB'
        """
        hash_str = hashlib.md5(key.encode()).hexdigest()
        return '#' + hash_str[:6]
    
    @classmethod
    def is_light_color(cls, hex_color: str) -> bool:
        """
        Определяет, является ли цвет светлым.
        
        Args:
            hex_color (str): Цвет в формате HEX (#RRGGBB)
            
        Returns:
            bool: True если цвет светлый, иначе False
        """
        if not hex_color or not isinstance(hex_color, str):
            logger.warning(f"Некорректный цвет для проверки яркости: {hex_color}")
            return True  # По умолчанию считаем светлым
            
        # Удаляем # из начала строки, если он есть
        hex_color = hex_color.lstrip('#')
        
        # Проверяем длину (должна быть 6 символов)
        if len(hex_color) != 6:
            logger.warning(f"Некорректная длина цвета: {hex_color}")
            return True
        
        try:
            # Преобразуем HEX в RGB
            r = int(hex_color[0:2], 16) / 255.0
            g = int(hex_color[2:4], 16) / 255.0
            b = int(hex_color[4:6], 16) / 255.0
            
            # Вычисляем яркость по формуле (0.299*R + 0.587*G + 0.114*B)
            brightness = 0.299 * r + 0.587 * g + 0.114 * b
            
            # Возвращаем True, если яркость больше порога
            return brightness > cls.BRIGHTNESS_THRESHOLD
            
        except ValueError as e:
            logger.error(f"Ошибка при парсинге цвета {hex_color}: {e}")
            return True  # По умолчанию считаем светлым
    
    @classmethod
    def get_contrast_text_color(cls, hex_color: str) -> str:
        """
        Возвращает цвет текста, контрастный к фону.
        
        Args:
            hex_color (str): Цвет фона в формате HEX (#RRGGBB)
            
        Returns:
            str: Цвет текста (#FFFFFF или #000000)
        """
        if not hex_color or not hex_color.startswith('#'):
            logger.debug(f"Некорректный цвет фона: {hex_color}, используем черный текст")
            return '#000000'  # По умолчанию черный текст
        
        # Для светлых фонов возвращаем темный текст, для темных - светлый
        return '#000000' if cls.is_light_color(hex_color) else '#FFFFFF'
    
    @classmethod
    def validate_hex_color(cls, color: str) -> bool:
        """
        Проверяет валидность цвета в формате HEX.
        
        Args:
            color (str): Цвет для проверки
            
        Returns:
            bool: True если цвет валиден, False иначе
        """
        if not color or not isinstance(color, str):
            return False
            
        # Убираем пробелы и приводим к нижнему регистру
        color = color.strip().lower()
        
        # Проверяем формат #RRGGBB
        hex_pattern = r'^#[0-9a-f]{6}$'
        return bool(re.match(hex_pattern, color))
    
    @classmethod
    def hex_to_rgb(cls, hex_color: str) -> Optional[Tuple[int, int, int]]:
        """
        Преобразует цвет из HEX в RGB.
        
        Args:
            hex_color (str): Цвет в формате HEX (#RRGGBB)
            
        Returns:
            Optional[Tuple[int, int, int]]: Кортеж (R, G, B) или None при ошибке
        """
        if not cls.validate_hex_color(hex_color):
            logger.error(f"Некорректный HEX цвет: {hex_color}")
            return None
            
        try:
            hex_color = hex_color.lstrip('#')
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return (r, g, b)
        except ValueError as e:
            logger.error(f"Ошибка преобразования HEX в RGB: {e}")
            return None
    
    @classmethod
    def rgb_to_hex(cls, r: int, g: int, b: int) -> str:
        """
        Преобразует цвет из RGB в HEX.
        
        Args:
            r (int): Красный компонент (0-255)
            g (int): Зеленый компонент (0-255)
            b (int): Синий компонент (0-255)
            
        Returns:
            str: Цвет в формате HEX (#RRGGBB)
        """
        # Ограничиваем значения диапазоном 0-255
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))
        
        return '#{:02x}{:02x}{:02x}'.format(r, g, b)
    
    @classmethod
    def adjust_color_brightness(cls, hex_color: str, adjustment: int) -> str:
        """
        Увеличивает или уменьшает яркость цвета.
        
        Args:
            hex_color (str): Исходный цвет в формате HEX
            adjustment (int): Изменение яркости (-255 до +255)
            
        Returns:
            str: Измененный цвет в формате HEX
        """
        rgb = cls.hex_to_rgb(hex_color)
        if not rgb:
            logger.error(f"Не удалось изменить яркость для цвета: {hex_color}")
            return hex_color  # Возвращаем исходный цвет при ошибке
        
        r, g, b = rgb
        return cls.rgb_to_hex(r + adjustment, g + adjustment, b + adjustment)
    
    @classmethod
    def get_color_palette_for_groups(cls, groups: List[str]) -> Dict[str, str]:
        """
        Генерирует палитру цветов для списка групп.
        
        Args:
            groups (List[str]): Список названий групп
            
        Returns:
            Dict[str, str]: Словарь {группа: цвет}
        """
        palette = {}
        for group in groups:
            palette[group] = cls.get_color_for_group(group)
        
        logger.info(f"Сгенерирована палитра для {len(groups)} групп")
        return palette
    
    @classmethod
    def get_service_info(cls) -> Dict[str, any]:
        """
        Возвращает информацию о сервисе цветов.
        
        Returns:
            Dict[str, any]: Словарь с метаинформацией
        """
        return {
            'version': '1.0.0',
            'special_categories': list(cls.SPECIAL_CATEGORIES.keys()),
            'compound_mappings': len(cls.COMPOUND_MAPPING),
            'brightness_threshold': cls.BRIGHTNESS_THRESHOLD,
            'supported_formats': ['HEX', 'RGB']
        }


# Функции для обратной совместимости с utils.py
def get_color(group: str) -> str:
    """
    Backward compatibility функция для utils.py
    
    Args:
        group (str): Название группы
        
    Returns:
        str: Цвет в формате '#RRGGBB'
    """
    return ColorService.get_color_for_group(group)


# Функции для обратной совместимости с html_generator.py
def is_light_color(hex_color: str) -> bool:
    """
    Backward compatibility функция для html_generator.py
    
    Args:
        hex_color (str): Цвет в формате HEX
        
    Returns:
        bool: True если цвет светлый
    """
    return ColorService.is_light_color(hex_color)


def get_contrast_text_color(hex_color: str) -> str:
    """
    Backward compatibility функция для html_generator.py
    
    Args:
        hex_color (str): Цвет фона в формате HEX
        
    Returns:
        str: Контрастный цвет текста
    """
    return ColorService.get_contrast_text_color(hex_color)
