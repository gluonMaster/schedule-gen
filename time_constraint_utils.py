"""
Вспомогательные функции для обработки временных ограничений.
"""
from time_utils import time_to_minutes, minutes_to_time, pause_to_slots

def create_conflict_variables(optimizer, i, j, c_i, c_j):
    """
    Создаёт переменные для определения конфликта между занятиями.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        i, j: Индексы классов
        c_i, c_j: Экземпляры ScheduleClass
        
    Returns:
        tuple: (conflict, same_day, time_overlap) - переменные для конфликта
    """
    # Create a variable for conflict detection
    conflict = optimizer.model.NewBoolVar(f"conflict_{i}_{j}")
    
    # Classes conflict if they're on the same day
    same_day = optimizer.model.NewBoolVar(f"same_day_{i}_{j}")
    if isinstance(optimizer.day_vars[i], int) and isinstance(optimizer.day_vars[j], int):
        # Проверяем равенство дней и устанавливаем значение переменной same_day
        if optimizer.day_vars[i] == optimizer.day_vars[j]:
            optimizer.model.Add(same_day == 1)
        else:
            optimizer.model.Add(same_day == 0)
    elif isinstance(optimizer.day_vars[i], int):
        optimizer.model.Add(optimizer.day_vars[j] == optimizer.day_vars[i]).OnlyEnforceIf(same_day)
        optimizer.model.Add(optimizer.day_vars[j] != optimizer.day_vars[i]).OnlyEnforceIf(same_day.Not())
    elif isinstance(optimizer.day_vars[j], int):
        optimizer.model.Add(optimizer.day_vars[i] == optimizer.day_vars[j]).OnlyEnforceIf(same_day)
        optimizer.model.Add(optimizer.day_vars[i] != optimizer.day_vars[j]).OnlyEnforceIf(same_day.Not())
    else:
        optimizer.model.Add(optimizer.day_vars[i] == optimizer.day_vars[j]).OnlyEnforceIf(same_day)
        optimizer.model.Add(optimizer.day_vars[i] != optimizer.day_vars[j]).OnlyEnforceIf(same_day.Not())
    
    # Classes conflict if their time slots overlap
    time_overlap = optimizer.model.NewBoolVar(f"time_overlap_{i}_{j}")
    
    return conflict, same_day, time_overlap

def add_time_overlap_constraints(optimizer, i, j, c_i, c_j, time_overlap):
    """
    Добавляет ограничения для определения перекрытия времени между занятиями.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        i, j: Индексы классов
        c_i, c_j: Экземпляры ScheduleClass
        time_overlap: Булева переменная для определения перекрытия времени
    """
    # Calculate the duration in time slots for each class
    duration_i_slots = (c_i.duration) // optimizer.time_interval
    duration_j_slots = (c_j.duration) // optimizer.time_interval
    
    # Добавляем паузы до и после только если они явно указаны для конфликтов
    pause_before_i_slots = pause_to_slots(c_i.pause_before, optimizer.time_interval)
    pause_after_i_slots = pause_to_slots(c_i.pause_after, optimizer.time_interval)
    pause_before_j_slots = pause_to_slots(c_j.pause_before, optimizer.time_interval)
    pause_after_j_slots = pause_to_slots(c_j.pause_after, optimizer.time_interval)
    
    # Проверка наличия временного окна у любого из классов
    c_i_has_window = hasattr(c_i, 'has_time_window') and c_i.has_time_window
    c_j_has_window = hasattr(c_j, 'has_time_window') and c_j.has_time_window
    
    # If both start times are fixed
    # If both start times are fixed
    if isinstance(optimizer.start_vars[i], int) and isinstance(optimizer.start_vars[j], int):
        # Для всех занятий с фиксированными временами учитываем реальное время - убираем проверку на окна
        start_i = optimizer.start_vars[i]
        end_i = optimizer.start_vars[i] + duration_i_slots
        
        start_j = optimizer.start_vars[j]
        end_j = optimizer.start_vars[j] + duration_j_slots
        
        # Создаем временную переменную для проверки пересечения
        overlap_check = (start_i < end_j) and (start_j < end_i)
        
        # Присваиваем значение переменной time_overlap в зависимости от результата проверки
        if overlap_check:
            print(f"  Fixed time conflict: {c_i.subject} ({start_i}-{end_i}) and {c_j.subject} ({start_j}-{end_j})")
            optimizer.model.Add(time_overlap == 1)
        else:
            optimizer.model.Add(time_overlap == 0)
    else:
        # One of the start times is not fixed
        if isinstance(optimizer.start_vars[i], int):
            # i имеет фиксированное время
            start_i = optimizer.start_vars[i]
            end_i = start_i + duration_i_slots
            
            # j имеет переменное время
            start_j = optimizer.start_vars[j]
            end_j = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"end_{j}")
            optimizer.model.Add(end_j == start_j + duration_j_slots)
            
            # Определяем условия пересечения
            overlap1 = optimizer.model.NewBoolVar(f"overlap1_{i}_{j}")
            overlap2 = optimizer.model.NewBoolVar(f"overlap2_{i}_{j}")
            
            optimizer.model.Add(start_i < end_j).OnlyEnforceIf(overlap1)
            optimizer.model.Add(start_i >= end_j).OnlyEnforceIf(overlap1.Not())
            
            optimizer.model.Add(start_j < end_i).OnlyEnforceIf(overlap2)
            optimizer.model.Add(start_j >= end_i).OnlyEnforceIf(overlap2.Not())
            
            # Перекрытие времени есть, если оба условия выполняются
            optimizer.model.AddBoolAnd([overlap1, overlap2]).OnlyEnforceIf(time_overlap)
            optimizer.model.AddBoolOr([overlap1.Not(), overlap2.Not()]).OnlyEnforceIf(time_overlap.Not())
            
        elif isinstance(optimizer.start_vars[j], int):
            # j имеет фиксированное время
            start_j = optimizer.start_vars[j]
            end_j = start_j + duration_j_slots
            
            # i имеет переменное время
            start_i = optimizer.start_vars[i]
            end_i = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"end_{i}")
            optimizer.model.Add(end_i == start_i + duration_i_slots)
            
            # Определяем условия пересечения
            overlap1 = optimizer.model.NewBoolVar(f"overlap1_{i}_{j}")
            overlap2 = optimizer.model.NewBoolVar(f"overlap2_{i}_{j}")
            
            optimizer.model.Add(start_i < end_j).OnlyEnforceIf(overlap1)
            optimizer.model.Add(start_i >= end_j).OnlyEnforceIf(overlap1.Not())
            
            optimizer.model.Add(start_j < end_i).OnlyEnforceIf(overlap2)
            optimizer.model.Add(start_j >= end_i).OnlyEnforceIf(overlap2.Not())
            
            # Перекрытие времени есть, если оба условия выполняются
            optimizer.model.AddBoolAnd([overlap1, overlap2]).OnlyEnforceIf(time_overlap)
            optimizer.model.AddBoolOr([overlap1.Not(), overlap2.Not()]).OnlyEnforceIf(time_overlap.Not())
            
        else:
            # Оба времени переменные
            start_i = optimizer.start_vars[i]
            end_i = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"end_{i}")
            optimizer.model.Add(end_i == start_i + duration_i_slots)
            
            start_j = optimizer.start_vars[j]
            end_j = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"end_{j}")
            optimizer.model.Add(end_j == start_j + duration_j_slots)
            
            # Определяем условия пересечения
            overlap1 = optimizer.model.NewBoolVar(f"overlap1_{i}_{j}")
            overlap2 = optimizer.model.NewBoolVar(f"overlap2_{i}_{j}")
            
            optimizer.model.Add(start_i < end_j).OnlyEnforceIf(overlap1)
            optimizer.model.Add(start_i >= end_j).OnlyEnforceIf(overlap1.Not())
            
            optimizer.model.Add(start_j < end_i).OnlyEnforceIf(overlap2)
            optimizer.model.Add(start_j >= end_i).OnlyEnforceIf(overlap2.Not())
            
            # Перекрытие времени есть, если оба условия выполняются
            optimizer.model.AddBoolAnd([overlap1, overlap2]).OnlyEnforceIf(time_overlap)
            optimizer.model.AddBoolOr([overlap1.Not(), overlap2.Not()]).OnlyEnforceIf(time_overlap.Not())
