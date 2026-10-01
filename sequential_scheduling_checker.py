"""
Модуль для проверки возможности последовательного размещения занятий.
"""
from time_utils import time_to_minutes, minutes_to_time

def _minutes_to_slot_with_fallback(optimizer, minutes, rounding="ceil"):
    """
    Convert absolute minutes to slot index using the best available optimizer API.
    Priority: explicit floor/ceil helpers, then _get_time_slot_index legacy fallback.
    """
    time_str = minutes_to_time(minutes)

    if rounding == "floor":
        if hasattr(optimizer, "minutes_to_slot_floor"):
            return optimizer.minutes_to_slot_floor(minutes)
        if hasattr(optimizer, "time_to_slot_floor"):
            return optimizer.time_to_slot_floor(time_str)
    else:
        if hasattr(optimizer, "minutes_to_slot_ceil"):
            return optimizer.minutes_to_slot_ceil(minutes)
        if hasattr(optimizer, "time_to_slot_ceil"):
            return optimizer.time_to_slot_ceil(time_str)

    if hasattr(optimizer, "_get_time_slot_index"):
        # Legacy fallback has ceil-like semantics.
        return optimizer._get_time_slot_index(time_str)

    raise AttributeError("Optimizer has no supported minutes->slot conversion API")

def _check_sequential_scheduling(optimizer, fixed_idx, window_idx):
    """
    Проверяет, можно ли разместить занятие с временным окном до или после фиксированного занятия.
    Если возможно — добавляет соответствующее ограничение. Если оба варианта невозможны — возвращает False.
    """
    fixed_c = optimizer.classes[fixed_idx]
    window_c = optimizer.classes[window_idx]

    if fixed_c.day != window_c.day:
        return False

    if not fixed_c.start_time or not window_c.start_time or not window_c.end_time:
        return False

    fixed_start = time_to_minutes(fixed_c.start_time)
    fixed_end = fixed_start + fixed_c.duration + fixed_c.pause_after

    window_start = time_to_minutes(window_c.start_time)
    window_end = time_to_minutes(window_c.end_time)
    window_duration = window_c.duration + window_c.pause_before + window_c.pause_after

    # Сначала пробуем разместить ДО фиксированного занятия
    latest_end_before_fixed = fixed_start - fixed_c.pause_before
    can_fit_before = (latest_end_before_fixed - window_start) >= window_duration
    if can_fit_before:
        latest_start_slot = _minutes_to_slot_with_fallback(
            optimizer,
            latest_end_before_fixed - window_duration,
            rounding="floor",
        )
        optimizer.model.Add(optimizer.start_vars[window_idx] <= latest_start_slot)
        print(f"SEQUENTIAL SCHEDULING: Window class {window_c.subject}"
              f" scheduled BEFORE fixed class {fixed_c.subject}"
              f" at {fixed_c.start_time}")
        return True

    # Если «до» не подошло, пробуем «после»
    earliest_start_after_fixed = fixed_end
    can_fit_after = (window_end - earliest_start_after_fixed) >= window_duration
    if can_fit_after:
        earliest_start_slot = _minutes_to_slot_with_fallback(
            optimizer,
            earliest_start_after_fixed,
            rounding="ceil",
        )
        optimizer.model.Add(optimizer.start_vars[window_idx] >= earliest_start_slot)
        print(f"SEQUENTIAL SCHEDULING: Window class {window_c.subject}"
              f" scheduled AFTER fixed class {fixed_c.subject}"
              f" at {fixed_c.start_time}")
        return True

    # Ни туда, ни туда не влезает
    print(f"NO SEQUENTIAL SCHEDULING POSSIBLE between {fixed_c.subject}"
          f" and {window_c.subject}")
    return False

# Глобальный словарь для отслеживания уже обработанных проверок
# Это позволит избежать дублирующих сообщений и ограничений
_processed_window_checks = set()

# sequential_scheduling_checker.py

def check_two_window_classes(optimizer, idx1, idx2, class1, class2):
    """
    Проверяет, можно ли разместить два занятия последовательно без пересечения
    в рамках их временных окон.

    Args:
        optimizer: Экземпляр оптимизатора расписания.
        idx1, idx2: Индексы занятий.
        class1, class2: Объекты ScheduleClass.

    Returns:
        bool: True, если возможно разместить последовательно без конфликтов, иначе False.
    """

    # Конвертация времени в минуты
    start1 = time_to_minutes(class1.start_time)
    end1 = time_to_minutes(class1.end_time)

    start2 = time_to_minutes(class2.start_time)
    end2 = time_to_minutes(class2.end_time)

    # Длительности в минутах
    duration1 = class1.duration
    duration2 = class2.duration

    # Пауза между занятиями зависит от порядка.
    gap_1_before_2 = class1.pause_after + class2.pause_before
    gap_2_before_1 = class2.pause_after + class1.pause_before

    # Возможные временные диапазоны для начала
    earliest_start1 = start1
    latest_start1 = end1 - duration1

    earliest_start2 = start2
    latest_start2 = end2 - duration2

    # Проверяем, можем ли разместить class1 перед class2 (с учетом пауз)
    can_schedule_1_before_2 = (earliest_start1 + duration1 + gap_1_before_2 <= latest_start2)

    # Проверяем, можем ли разместить class2 перед class1 (с учетом пауз)
    can_schedule_2_before_1 = (earliest_start2 + duration2 + gap_2_before_1 <= latest_start1)

    # Проверяем наложение окон вообще
    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)
    total_overlap_time = overlap_end - overlap_start

    min_gap = min(gap_1_before_2, gap_2_before_1)
    total_duration_needed = duration1 + duration2 + min_gap

    # Если общее пересечение окон достаточно большое для двух занятий подряд
    enough_overlap = total_overlap_time >= total_duration_needed

    # Логика возврата
    return can_schedule_1_before_2 or can_schedule_2_before_1 or enough_overlap

def reset_window_checks_cache():
    """
    Сбрасывает кэш обработанных проверок. Эту функцию следует вызывать
    перед каждым новым запуском оптимизатора, чтобы избежать сохранения
    состояния между запусками.
    """
    global _processed_window_checks
    _processed_window_checks = set()
    print("Window checks cache has been reset.")

