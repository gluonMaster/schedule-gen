"""
Модуль для анализа возможности последовательного планирования занятий.
Предоставляет функции для определения, могут ли занятия быть размещены последовательно
в одной аудитории или с одним преподавателем.
"""

from time_utils import time_to_minutes, minutes_to_time

def can_schedule_sequentially(c1, c2):
    """
    Проверяет, могут ли два занятия быть запланированы последовательно с учетом их временных ограничений.
    
    Args:
        c1: Первое занятие (ScheduleClass)
        c2: Второе занятие (ScheduleClass)
        
    Returns:
        tuple: (bool, dict) - возможно ли последовательное размещение и дополнительная информация
    """
    info = {
        'reason': '',
        'c1_start': None,
        'c1_end': None,
        'c2_start': None,
        'c2_end': None,
        'common_window': None,
        'required_time': None,
        'available_time': None
    }
    
    # Проверка наличия общего дня
    if c1.day != c2.day:
        info['reason'] = 'different_days'
        return False, info
    
    # Проверка наличия временных ограничений
    if not c1.start_time or not c2.start_time:
        info['reason'] = 'missing_time_info'
        return True, info  # Если нет ограничений по времени, планирование возможно
    
    # Проверка случаев с фиксированным временем и временным окном
    if c1.start_time and not c1.end_time and c2.start_time and c2.end_time:
        # c1 фиксировано, c2 с окном
        fixed_start   = time_to_minutes(c1.start_time)
        fixed_end     = fixed_start + c1.duration + c1.pause_after
        window_start  = time_to_minutes(c2.start_time)
        window_end    = time_to_minutes(c2.end_time)
    
        # Проверяем оба направления
        can_fit_before = (window_start + c2.duration + c2.pause_after) <= (fixed_start - c1.pause_before)
        can_fit_after  = (window_end - fixed_end) >= (c2.duration + c2.pause_before)
    
        if can_fit_before and can_fit_after:
            # Оба варианта возможны — не навязываем порядок
            info['reason']         = 'both_orders_possible'
            info['available_time'] = window_end - window_start
            info['required_time']  = (c1.pause_before + c2.duration + c2.pause_after + c2.pause_before)
            return True, info
        elif can_fit_before:
            info['reason']         = 'fits_before_fixed'
            info['available_time'] = fixed_start - (window_start + c2.duration + c2.pause_after)
            info['required_time']  = c1.pause_before
            return True, info
        elif can_fit_after:
            info['reason']         = 'fits_after_fixed'
            info['available_time'] = window_end - fixed_end
            info['required_time']  = c2.duration + c2.pause_before
            return True, info
        else:
            info['reason'] = 'not_enough_time_around_fixed'
            return False, info
        
    elif c2.start_time and not c2.end_time and c1.start_time and c1.end_time:
        # c2 фиксировано, c1 с окном
        fixed_start   = time_to_minutes(c2.start_time)
        fixed_end     = fixed_start + c2.duration + c2.pause_after
        window_start  = time_to_minutes(c1.start_time)
        window_end    = time_to_minutes(c1.end_time)
    
        # Проверяем оба направления
        can_fit_before = (window_start + c1.duration + c1.pause_after) <= (fixed_start - c2.pause_before)
        can_fit_after  = (window_end - fixed_end) >= (c1.duration + c1.pause_before)
    
        if can_fit_before and can_fit_after:
            info['reason']         = 'both_orders_possible'
            info['available_time'] = window_end - window_start
            info['required_time']  = (c2.pause_before + c1.duration + c1.pause_after + c1.pause_before)
            return True, info
        elif can_fit_before:
            info['reason']         = 'fits_before_fixed'
            info['available_time'] = fixed_start - (window_start + c1.duration + c1.pause_after)
            info['required_time']  = c2.pause_before
            return True, info
        elif can_fit_after:
            info['reason']         = 'fits_after_fixed'
            info['available_time'] = window_end - fixed_end
            info['required_time']  = c1.duration + c1.pause_before
            return True, info
        else:
            info['reason'] = 'not_enough_time_around_fixed'
            return False, info
        
    elif c1.start_time and c1.end_time and c2.start_time and c2.end_time:
        # Оба занятия с временными окнами
        window1_start = time_to_minutes(c1.start_time)
        window1_end = time_to_minutes(c1.end_time)
        window2_start = time_to_minutes(c2.start_time)
        window2_end = time_to_minutes(c2.end_time)
        
        # Проверяем возможность последовательного размещения в порядке c1, затем c2
        c1_earliest_end = window1_start + c1.duration + c1.pause_after
        c2_latest_start = window2_end - c2.duration
        
        # Порядок c1, затем c2 возможен, если:
        order_1_then_2_possible = c1_earliest_end + c2.pause_before <= c2_latest_start and c1_earliest_end <= window2_end
        
        # Порядок c2, затем c1 возможен, если:
        c2_earliest_end = window2_start + c2.duration + c2.pause_after
        c1_latest_start = window1_end - c1.duration
        order_2_then_1_possible = c2_earliest_end + c1.pause_before <= c1_latest_start and c2_earliest_end <= window1_end
        
        info['c1_start'] = c1.start_time
        info['c1_end'] = c1.end_time
        info['c2_start'] = c2.start_time
        info['c2_end'] = c2.end_time
        
        # Находим общее временное окно (для информации)
        common_start = max(window1_start, window2_start)
        common_end = min(window1_end, window2_end)
        common_duration = common_end - common_start
        info['common_window'] = f"{minutes_to_time(common_start)}-{minutes_to_time(common_end)}"
        
        if order_1_then_2_possible and order_2_then_1_possible:
            info['reason'] = 'both_orders_possible'
            info['available_time'] = common_duration
            info['required_time'] = c1.duration + c1.pause_after + c2.pause_before + c2.duration
            return True, info
        elif order_1_then_2_possible:
            info['reason'] = 'fits_in_common_window_1_then_2'
            info['available_time'] = c2_latest_start - c1_earliest_end
            info['required_time'] = c2.pause_before
            return True, info
        elif order_2_then_1_possible:
            info['reason'] = 'fits_in_common_window_2_then_1'
            info['available_time'] = c1_latest_start - c2_earliest_end
            info['required_time'] = c1.pause_before
            return True, info
        else:
            info['reason'] = 'not_enough_time_in_common_window'
            info['available_time'] = common_duration
            info['required_time'] = c1.duration + c1.pause_after + c2.pause_before + c2.duration
            return False, info
            
    elif c1.start_time and not c1.end_time and c2.start_time and not c2.end_time:
        # Оба занятия с фиксированным временем
        start1 = time_to_minutes(c1.start_time)
        end1 = start1 + c1.duration + c1.pause_after
        start2 = time_to_minutes(c2.start_time)
        end2 = start2 + c2.duration + c2.pause_after
        
        info['c1_start'] = c1.start_time
        info['c1_end'] = minutes_to_time(end1)
        info['c2_start'] = c2.start_time
        info['c2_end'] = minutes_to_time(end2)
        
        # Проверяем, пересекаются ли занятия
        if start1 < end2 and start2 < end1:
            info['reason'] = 'fixed_times_overlap'
            return False, info
        else:
            info['reason'] = 'fixed_times_no_overlap'
            return True, info
    
    # Если достигли этой точки, значит не все случаи обработаны
    info['reason'] = 'unknown_time_configuration'
    return True, info  # По умолчанию разрешаем планирование

def check_sequential_for_same_teacher(optimizer, teacher_name):
    """
    Проверяет возможность последовательного планирования для занятий с одним преподавателем.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        teacher_name: Имя преподавателя для проверки
        
    Returns:
        list: Список пар занятий, которые можно запланировать последовательно
    """
    sequential_pairs = []
    
    # Находим все занятия указанного преподавателя
    teacher_class_indices = []
    for idx, c in enumerate(optimizer.classes):
        if c.teacher == teacher_name:
            teacher_class_indices.append(idx)
    
    # Для каждой пары занятий проверяем возможность последовательного планирования
    for i, idx_i in enumerate(teacher_class_indices):
        c_i = optimizer.classes[idx_i]
        
        for j, idx_j in enumerate(teacher_class_indices[i+1:], i+1):
            c_j = optimizer.classes[idx_j]
            
            # Проверяем наличие общего дня
            if c_i.day and c_j.day and c_i.day != c_j.day:
                continue
                
            # Проверяем наличие общих групп
            shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
            if shared_groups:
                continue  # Пропускаем, если есть общие группы
                
            # Проверяем наличие общих аудиторий
            shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
            if not shared_rooms:
                continue  # Пропускаем, если нет общих аудиторий
                
            # Проверяем возможность последовательного планирования
            can_schedule, info = can_schedule_sequentially(c_i, c_j)
            
            if can_schedule:
                sequential_pairs.append({
                    'class1_idx': idx_i,
                    'class2_idx': idx_j,
                    'class1': c_i,
                    'class2': c_j,
                    'info': info
                })
    
    return sequential_pairs

def analyze_tanz_classes(optimizer):
    """
    Специальный анализ для занятий Tanz с преподавателем Melnikov Olga.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        
    Returns:
        dict: Результаты анализа
    """
    # Находим все занятия Tanz с преподавателем Melnikov Olga
    tanz_indices = []
    for idx, c in enumerate(optimizer.classes):
        if c.subject == "Tanz" and c.teacher == "Melnikov Olga":
            tanz_indices.append(idx)
    
    results = {
        'num_classes': len(tanz_indices),
        'classes': [],
        'sequential_possible': False,
        'details': {}
    }
    
    # Если нашли два или более занятия, анализируем их
    if len(tanz_indices) >= 2:
        for idx in tanz_indices:
            c = optimizer.classes[idx]
            results['classes'].append({
                'index': idx,
                'group': c.group,
                'day': c.day,
                'start_time': c.start_time,
                'end_time': c.end_time,
                'duration': c.duration,
                'rooms': c.possible_rooms
            })
        
        # Проверяем возможность последовательного планирования для каждой пары
        sequential_pairs = []
        for i, idx_i in enumerate(tanz_indices):
            c_i = optimizer.classes[idx_i]
            
            for j, idx_j in enumerate(tanz_indices[i+1:], i+1):
                c_j = optimizer.classes[idx_j]
                
                can_schedule, info = can_schedule_sequentially(c_i, c_j)
                
                sequential_pairs.append({
                    'class1_idx': idx_i,
                    'class2_idx': idx_j,
                    'can_schedule': can_schedule,
                    'info': info
                })
        
        results['sequential_pairs'] = sequential_pairs
        results['sequential_possible'] = any(pair['can_schedule'] for pair in sequential_pairs)
    
    return results
