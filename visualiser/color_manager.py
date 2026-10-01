# color_manager.py

import re
import hashlib
import colorsys
from reportlab.lib.colors import Color

# Кэши
GROUP_COLOR_CACHE = {}
BUILDING_COLOR_CACHE = {}


def initialize_group_colors(group_names, saturation=0.6, value=0.9):
    pass
#    """
#    Инициализирует палитру цветов для групп.
#    
#    Все группы вида "цифра+буква" получают единый цвет,
#    остальные — группируются по первому слову.
#    
#    Args:
#        group_names (iterable of str): список всех названий групп
#        saturation (float): насыщенность (0–1), по умолчанию 0.6
#        value (float): яркость (0–1), по умолчанию 0.9
#    """
#    # Функция, которая по имени группы выдаёт «ключ» для цвета
#    def key_for_group(g):
#        return (
#            "DIGIT_LETTER_GROUP"
#            if re.match(r'^\d+[A-Za-z]$', g)
#            else (g.split()[0] if ' ' in g else g)
#        )
#
#    # Собираем уникальные ключи
#    keys = [key_for_group(g) for g in group_names]
#    unique_keys = sorted(set(keys))
#    n = len(unique_keys)
#
#    # Генерируем палитру: равномерно по кругу HSV → RGB → Color
#    key_color_map = {}
#    for idx, key in enumerate(unique_keys):
#        hue = idx / n
#        r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
#        key_color_map[key] = Color(r, g, b)
#
#    # Заполняем кэш для каждой конкретной группы
#    for g in group_names:
#        GROUP_COLOR_CACHE[g] = key_color_map[key_for_group(g)]


def get_group_color(group_name):
    """
    Возвращает цвет группы. 
    Если вы предварительно вызвали initialize_group_colors, 
    берёт готовый цвет из GROUP_COLOR_CACHE, иначе — делает фолбэк.
    """
#    if group_name in GROUP_COLOR_CACHE:
#        return GROUP_COLOR_CACHE[group_name]
#
#    # Фолбэк: генерируем цвет по ключу
#    if re.match(r'^\d+[A-Za-z]$', group_name):
#        key = "DIGIT_LETTER_GROUP"
#    else:
#        key = group_name.split()[0] if ' ' in group_name else group_name
#
    # единичная генерация, как было раньше
#    color = generate_color_from_string(key)
    color = generate_color_from_string(group_name)
#    GROUP_COLOR_CACHE[group_name] = color
    return color


def initialize_building_colors(building_names, saturation=0.9, value=0.9):
    """
    Инициализирует палитру ярких, равномерно разбросанных цветов для зданий.
    
    building_names: iterable строк, все названия зданий в расписании
    saturation, value: параметры HSV (чем ближе к 1 — тем ярче и насыщеннее)
    """
    unique = sorted(set(building_names))
    n = len(unique)
    for idx, b in enumerate(unique):
        hue = idx / n
        r, g, b_ = colorsys.hsv_to_rgb(hue, saturation, value)
        BUILDING_COLOR_CACHE[b] = Color(r, g, b_)

def get_building_color(building_name):
    """
    Возвращает цвет для здания. 
    После вызова initialize_building_colors все основные здания уже в кэше,
    остальные (если вдруг не проинициализированы) получают «фолбэк» через хеш.
    """
    if building_name in BUILDING_COLOR_CACHE:
        return BUILDING_COLOR_CACHE[building_name]
    # Фолбэк — как раньше
    color = generate_color_from_string(building_name, saturation=0.8, value=0.7)
    BUILDING_COLOR_CACHE[building_name] = color
    return color


#def generate_color_from_string(input_string, saturation=0.5, value=0.95):
#    """Фолбэк‑генерация одного цвета из строки через MD5→HSV."""
#    if not input_string:
#        input_string = "default"
#    hash_int = int(hashlib.md5(input_string.encode()).hexdigest(), 16)
#    hue = (hash_int % 1000) / 1000.0
#    r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
#    return Color(r, g, b)

def generate_color_from_string(input_string, saturation=0.5, value=0.95):
    """Генерация цвета на основе названия учебной группы с особыми правилами."""
    if not input_string:
        input_string = "default"
    
    # Преобразуем строку к нижнему регистру для упрощения проверок
    lower_input = input_string.lower()
    
    # Проверка на число с последующей буквой (например, 2D, 11B)
    if re.match(r'^\d+[A-Za-z]$', input_string):
        # Бледно-зеленый цвет
        return Color(0.8, 1.0, 0.8)
        #return Color(1.0, 1.0, 1.0)
    
    # Проверка на слово "kunst" в названии группы
    elif "kunst" in lower_input:
        # Бледно-голубой цвет
        return Color(0.8, 0.9, 1.0)
        #return Color(1.0, 1.0, 1.0)
    
    # Проверка на слово "tanz" в названии группы
    elif "tanz" in lower_input:
        # Бледно-желтый цвет
        return Color(1.0, 1.0, 0.8)
        #return Color(1.0, 1.0, 1.0)
    
    # Во всех остальных случаях - белый цвет
    else:
        return Color(1.0, 1.0, 1.0)


def get_text_color(background_color):
    """Черный или белый текст в зависимости от яркости фона."""
    lum = 0.299 * background_color.red \
        + 0.587 * background_color.green \
        + 0.114 * background_color.blue
    return Color(0, 0, 0) if lum > 0.5 else Color(1, 1, 1)
