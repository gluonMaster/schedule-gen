"""
Модуль обработки данных расписания
Содержит функции для загрузки и обработки данных из Excel-файла
"""

import pandas as pd
import numpy as np
from datetime import datetime
try:
    from .lesson_type_utils import classify_lesson_type
except ImportError:
    from lesson_type_utils import classify_lesson_type

try:
    from gear_xls.day_constants import DAY_TO_WEEKDAY, PUBLIC_SCHEDULE_DAYS
except ImportError:
    PUBLIC_SCHEDULE_DAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa")
    DAY_TO_WEEKDAY = {"Mo": 0, "Di": 1, "Mi": 2, "Do": 3, "Fr": 4, "Sa": 5, "So": 6}


_COLUMN_ALIASES = {
    'занятие': 'subject',
    'subject': 'subject',
    'группа': 'group',
    'group': 'group',
    'students': 'group',
    'преподаватель': 'teacher',
    'teacher': 'teacher',
    'кабинет': 'room',
    'room': 'room',
    'здание': 'building',
    'building': 'building',
    'день': 'day',
    'day': 'day',
    'начало': 'start_time',
    'start_time': 'start_time',
    'конец': 'end_time',
    'end_time': 'end_time',
    'продолжительность': 'duration',
    'duration': 'duration',
    'тип занятия': 'lesson_type',
    'lesson_type': 'lesson_type',
    'даты (json)': 'trial_dates_json',
    'trial_dates_json': 'trial_dates_json',
}

_COLUMN_ORDER = [
    'subject',
    'group',
    'teacher',
    'room',
    'building',
    'day',
    'start_time',
    'end_time',
    'duration',
    'lesson_type',
    'trial_dates_json',
]


def _normalize_columns(df):
    rename_map = {}
    for col in df.columns:
        normalized = _COLUMN_ALIASES.get(str(col).strip().lower())
        if normalized and col != normalized:
            rename_map[col] = normalized
    normalized_df = df.rename(columns=rename_map) if rename_map else df

    positional_map = {}
    normalized_columns = list(normalized_df.columns)
    for idx, canonical in enumerate(_COLUMN_ORDER[:len(normalized_columns)]):
        current = normalized_columns[idx]
        if current == canonical or canonical in normalized_df.columns:
            continue
        positional_map[current] = canonical

    return normalized_df.rename(columns=positional_map) if positional_map else normalized_df


def _normalize_lesson_type_value(value):
    if value is None or pd.isna(value):
        return ''
    return str(value).strip().lower()


def _effective_lesson_types(df):
    explicit_types = None
    if 'lesson_type' in df.columns:
        explicit_types = df['lesson_type'].apply(_normalize_lesson_type_value)

    if 'subject' not in df.columns:
        return explicit_types

    classified_types = df['subject'].apply(
        lambda s: classify_lesson_type(str(s) if s is not None else '')
    )

    if explicit_types is None:
        return classified_types
    return explicit_types.where(explicit_types != '', classified_types)


def load_data(excel_file_path):
    """
    Загружает данные расписания из Excel-файла
    
    Args:
        excel_file_path (str): Путь к Excel-файлу с расписанием
        
    Returns:
        pandas.DataFrame: Датафрейм с данными расписания
    """
    # Загружаем данные с листа Schedule
    df = pd.read_excel(excel_file_path, sheet_name='Schedule')
    df = _normalize_columns(df)
    
    # Проверяем структуру данных
    required_columns = [
        'subject', 'group', 'teacher', 'room', 'building', 
        'day', 'start_time', 'end_time', 'duration'
    ]
    
    # Убедимся, что все необходимые столбцы присутствуют
    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"В таблице отсутствует обязательный столбец '{col}'")

    if 'lesson_type' in df.columns:
        df['lesson_type'] = df['lesson_type'].apply(_normalize_lesson_type_value)
    
    # Убедимся, что start_time и end_time имеют правильный формат времени
    if not pd.api.types.is_datetime64_dtype(df['start_time']):
        df['start_time'] = pd.to_datetime(df['start_time'], format='%H:%M', errors='coerce')
    
    if not pd.api.types.is_datetime64_dtype(df['end_time']):
        df['end_time'] = pd.to_datetime(df['end_time'], format='%H:%M', errors='coerce')
    
    # Извлекаем только время (без даты)
    df['start_time'] = df['start_time'].dt.strftime('%H:%M')
    df['end_time'] = df['end_time'].dt.strftime('%H:%M')
    
    return df


def filter_by_lesson_type(df, lesson_type_filter='all'):
    """
    Filters a schedule DataFrame by lesson type.

    Args:
        df: DataFrame with a 'subject' column and optional 'lesson_type' column.
        lesson_type_filter: one of 'all', 'group', 'individual', 'nachhilfe', 'trial', 'non-group'.

    Returns:
        Filtered DataFrame (original df returned unchanged for filter='all').
        Trial filtering uses the explicit 'lesson_type' column when present.
        If filter='trial' and 'lesson_type' is absent, returns an empty DataFrame.
    """
    if lesson_type_filter == 'all':
        return df

    if lesson_type_filter == 'trial':
        if 'lesson_type' not in df.columns:
            return df.iloc[0:0].reset_index(drop=True)
    effective_types = _effective_lesson_types(df)
    if effective_types is None:
        return df

    if lesson_type_filter == 'non-group':
        mask = effective_types.isin(('individual', 'nachhilfe', 'trial'))
    else:
        mask = effective_types == lesson_type_filter
    return df[mask].reset_index(drop=True)


def filter_final_visualization_days(df):
    """Keep only public schedule days for final PDF/HTML outputs."""
    if df is None or 'day' not in df.columns:
        return df
    return df[df['day'].isin(PUBLIC_SCHEDULE_DAYS)].reset_index(drop=True)


def process_schedule_data(df):
    """
    Обрабатывает данные расписания, группируя их по дням недели
    
    Args:
        df (pandas.DataFrame): Датафрейм с данными расписания
        
    Returns:
        tuple: (список дней недели, словарь с расписанием по дням)
    """
    df = filter_final_visualization_days(df)

    # Порядок дней недели
    day_order = DAY_TO_WEEKDAY
    
    # Получаем уникальные дни недели в правильном порядке
    unique_days = sorted(df['day'].unique(), key=lambda x: day_order.get(x, 99))
    
    # Словарь для хранения расписания по дням
    schedule_by_day = {}
    
    for day in unique_days:
        # Фильтруем занятия для текущего дня
        day_schedule = df[df['day'] == day].copy()
        
        # Преобразуем время в формат для сортировки
        day_schedule['start_time_dt'] = pd.to_datetime(day_schedule['start_time'], format='%H:%M')
        
        # Сортируем по времени начала
        day_schedule = day_schedule.sort_values('start_time_dt')
        
        # Создаем список занятий для текущего дня с нужной информацией
        lessons = []
        for _, row in day_schedule.iterrows():
            # очищаем номер кабинета от символа-здания (первая буква в названии кабинета):
            original_room = row['room']
            if isinstance(original_room, str) and original_room and original_room[0].isalpha():
                cleaned_room = original_room[1:]
            else:
                cleaned_room = original_room

            lesson = {
                'subject':         row['subject'],
                'group':           row['group'],
                'teacher':         row['teacher'],
                'room':            cleaned_room,     # теперь без первого символа
                'building':        row['building'],
                'start_time':      row['start_time'],
                'end_time':        row['end_time'],
                'duration':        row['duration'],
                'start_time_mins': time_to_minutes(row['start_time']),
                'end_time_mins':   time_to_minutes(row['end_time'])
            }
            if 'lesson_type' in day_schedule.columns and pd.notna(row['lesson_type']):
                lesson['lesson_type'] = str(row['lesson_type']).strip().lower()
            lessons.append(lesson)
        
        schedule_by_day[day] = lessons
    
    return unique_days, schedule_by_day


def time_to_minutes(time_str):
    """
    Преобразует время в формате ЧЧ:ММ в количество минут от полуночи
    
    Args:
        time_str (str): Время в формате ЧЧ:ММ
        
    Returns:
        int: Количество минут от полуночи
    """
    try:
        hours, minutes = map(int, time_str.split(':'))
        return hours * 60 + minutes
    except (ValueError, AttributeError):
        # В случае ошибки возвращаем 0
        return 0


def minutes_to_time(minutes):
    """
    Преобразует количество минут от полуночи в время в формате ЧЧ:ММ
    
    Args:
        minutes (int): Количество минут от полуночи
        
    Returns:
        str: Время в формате ЧЧ:ММ
    """
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"
