#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утилиты для работы со временем.
Выделены в отдельный модуль для избежания циклических импортов.
"""

def time_to_minutes(time_str):
    """
    Преобразует время в формате 'HH:MM' в количество минут с начала суток.
    
    Args:
        time_str (str): Время в формате 'HH:MM'
        
    Returns:
        int: Количество минут с начала суток
    """
    if not time_str or not isinstance(time_str, str):
        return 0
        
    try:
        hours, minutes = map(int, time_str.split(':'))
        return hours * 60 + minutes
    except (ValueError, AttributeError):
        return 0


def minutes_to_time(m):
    """
    Преобразует количество минут в строку формата 'HH:MM'.
    
    Args:
        m (int): Количество минут с начала суток
        
    Returns:
        str: Время в формате 'HH:MM'
    """
    if m is None:
        return "00:00"
    return f"{m // 60:02d}:{m % 60:02d}"


def add_minutes(t, mins):
    """
    Прибавляет к времени в формате 'HH:MM' заданное число минут.
    
    Args:
        t (str): Исходное время в формате 'HH:MM'
        mins (int): Добавляемое количество минут
        
    Returns:
        str: Результирующее время в формате 'HH:MM'
    """
    total = time_to_minutes(t) + mins
    return minutes_to_time(total)
