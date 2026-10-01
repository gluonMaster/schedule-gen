"""
Адаптер для улучшения обработки временных окон в планировании расписания.

Этот модуль предоставляет функциональность для анализа возможности последовательного
размещения занятий с учетом временных окон и создания соответствующих ограничений.
"""

from time_utils import time_to_minutes, minutes_to_time, pause_to_slots
from sequential_scheduling_checker import check_two_window_classes
from sequential_scheduling import can_schedule_sequentially
from time_constraint_utils import create_conflict_variables

def find_slot_for_time(optimizer, time_str, rounding="ceil"):
    """Thin wrapper over optimizer time-to-slot helpers."""
    if rounding == "floor":
        return optimizer.time_to_slot_floor(time_str)
    return optimizer.time_to_slot_ceil(time_str)

def is_in_linked_chain(optimizer, idx):
    """
    Проверяет, принадлежит ли занятие с индексом idx к какой-либо связанной цепочке.
    """
    for chain in getattr(optimizer, "linked_chains", []):
        if idx in chain:
            return True
    return False

def get_linked_chain_order(optimizer, idx_i, idx_j):
    """
    Определяет, находятся ли два класса в одной связанной цепочке, 
    и если да, то в каком порядке они должны следовать.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        idx_i, idx_j: Индексы проверяемых классов
        
    Returns:
        tuple: (в_одной_цепочке, порядок_i_j)
            в_одной_цепочке: True, если классы в одной цепочке
            порядок_i_j: 1, если i должен быть перед j, -1, если j перед i, 0 - неопределенно
    """
    if not hasattr(optimizer, "linked_chains") or not optimizer.linked_chains:
        return False, 0
    
    # Проверяем каждую цепочку
    for chain in optimizer.linked_chains:
        if idx_i in chain and idx_j in chain:
            # Оба класса в одной цепочке - определяем их порядок
            i_pos = chain.index(idx_i)
            j_pos = chain.index(idx_j)
            
            if i_pos < j_pos:
                return True, 1  # i должен быть перед j
            else:
                return True, -1  # j должен быть перед i
    
    # Классы не в одной цепочке или одного из них нет в цепочках
    return False, 0

def add_time_separation_constraints(optimizer, idx_i, idx_j, c_i, c_j):
    """
    Добавляет ограничения для гарантированного разделения занятий по времени
    с добавлением минимального интервала между занятиями
    """
    # Проверка на существующие ограничения между этими классами
    pair_key = (idx_i, idx_j)
    reversed_key = (idx_j, idx_i)
    
    if hasattr(optimizer, "applied_constraints") and (pair_key in optimizer.applied_constraints or 
                                                     reversed_key in optimizer.applied_constraints):
        print(f"  Skipping separation constraints for {idx_i} and {idx_j} - already constrained")
        return
    
    # НОВЫЙ КОД: Проверяем, являются ли классы частью одной связанной цепочки
    in_same_chain, chain_order = get_linked_chain_order(optimizer, idx_i, idx_j)
    
    if in_same_chain:
        # Добавляем ограничение только в направлении цепочки
        if chain_order > 0:  # i должен быть перед j
            duration_i_slots = c_i.duration // optimizer.time_interval
            min_pause = pause_to_slots(c_i.pause_after + c_j.pause_before, optimizer.time_interval)
            print(f"DEBUG: Adding one-way chain constraint: {idx_i} -> {idx_j}, gap: {duration_i_slots}+{min_pause}")
            constraint = optimizer.model.Add(optimizer.start_vars[idx_i] + duration_i_slots + min_pause <= 
                                          optimizer.start_vars[idx_j])
            print(f"  Added one-way chain constraint: class {idx_i} before class {idx_j}")
            
            # Сохраняем примененные ограничения
            if not hasattr(optimizer, "applied_constraints"):
                optimizer.applied_constraints = {}
            optimizer.applied_constraints[pair_key] = constraint
            return
        elif chain_order < 0:  # j должен быть перед i
            duration_j_slots = c_j.duration // optimizer.time_interval
            min_pause = pause_to_slots(c_j.pause_after + c_i.pause_before, optimizer.time_interval)
            print(f"DEBUG: Adding one-way chain constraint: {idx_j} -> {idx_i}, gap: {duration_j_slots}+{min_pause}")
            constraint = optimizer.model.Add(optimizer.start_vars[idx_j] + duration_j_slots + min_pause <= 
                                          optimizer.start_vars[idx_i])
            print(f"  Added one-way chain constraint: class {idx_j} before class {idx_i}")
            
            # Сохраняем примененные ограничения
            if not hasattr(optimizer, "applied_constraints"):
                optimizer.applied_constraints = {}
            optimizer.applied_constraints[reversed_key] = constraint
            return
    
    # СУЩЕСТВУЮЩИЙ КОД: для несвязанных классов или если порядок не определен
    print(f"DEBUG: Classes {idx_i} and {idx_j} not in same chain, adding bidirectional constraints")
    
    # Создаем булеву переменную для определения порядка занятий
    i_before_j = optimizer.model.NewBoolVar(f"strict_i_before_j_{idx_i}_{idx_j}")
    
    # Расчет длительности в слотах времени
    duration_i_slots = c_i.duration // optimizer.time_interval
    duration_j_slots = c_j.duration // optimizer.time_interval
    
    # Минимальный интервал между занятиями по данным пауз (0 минут -> 0 слотов)
    min_pause_i_j = pause_to_slots(c_i.pause_after + c_j.pause_before, optimizer.time_interval)
    min_pause_j_i = pause_to_slots(c_j.pause_after + c_i.pause_before, optimizer.time_interval)
    
    # Если i перед j
    constraint1 = optimizer.model.Add(optimizer.start_vars[idx_i] + duration_i_slots + min_pause_i_j <= 
                  optimizer.start_vars[idx_j]).OnlyEnforceIf(i_before_j)
    
    # Если j перед i
    constraint2 = optimizer.model.Add(optimizer.start_vars[idx_j] + duration_j_slots + min_pause_j_i <= 
                  optimizer.start_vars[idx_i]).OnlyEnforceIf(i_before_j.Not())
    
    print(f"  Added strict time separation constraints between classes {idx_i} and {idx_j}")
    
    # Сохраняем примененные ограничения
    if not hasattr(optimizer, "applied_constraints"):
        optimizer.applied_constraints = {}
    
    optimizer.applied_constraints[pair_key] = [constraint1, constraint2]

def analyze_related_classes(optimizer):
    """
    Анализирует группы взаимосвязанных занятий (общая группа/преподаватель/аудитория)
    и создает оптимальное последовательное планирование.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        
    Returns:
        bool: True, если анализ успешно выполнен
    """
    linked_chains_dict = {}
    if hasattr(optimizer, "linked_chains"):
        for chain_idx, chain in enumerate(optimizer.linked_chains):
            for cls_idx in chain:
                linked_chains_dict[cls_idx] = (chain_idx, chain.index(cls_idx))

    print("\nAnalyzing related classes for sequential scheduling...")

    # Отслеживание занятий, для которых уже добавлены ограничения связывания
    linked_processed = set()
    
    # Словари для хранения связанных занятий по разным критериям
    classes_by_group = {}   # Занятия каждой группы
    classes_by_teacher = {} # Занятия каждого преподавателя
    classes_by_room = {}    # Занятия каждой аудитории
    
    # Группировка занятий
    for idx, c in enumerate(optimizer.classes):
        # Группировка по группам
        for group in c.get_groups():
            if group not in classes_by_group:
                classes_by_group[group] = []
            classes_by_group[group].append((idx, c))
        
        # Группировка по преподавателям
        if c.teacher:
            if c.teacher not in classes_by_teacher:
                classes_by_teacher[c.teacher] = []
            classes_by_teacher[c.teacher].append((idx, c))
        
        # Группировка по аудиториям 
        for room in c.possible_rooms:
            if room not in classes_by_room:
                classes_by_room[room] = []
            classes_by_room[room].append((idx, c))
    
    # Отслеживание обработанных пар занятий
    processed_pairs = set()
    prefer_late_start = set()

    # Словари для отслеживания связанных классов
    linked_fixed_classes = {}  # оконные -> фиксированные
    linked_window_classes = {}  # фиксированные -> оконные
    
    # Обработка каждой группы (студенческий класс)
    print("\nProcessing classes by student groups:")
    for group, group_classes in classes_by_group.items():
        # Фильтрация занятий по дням
        classes_by_day = {}
        for idx, c in group_classes:
            if c.day not in classes_by_day:
                classes_by_day[c.day] = []
            classes_by_day[c.day].append((idx, c))
        
        # Обработка каждого дня отдельно  
        for day, day_classes in classes_by_day.items():
            if day is None:
                # Variable-day classes must not receive unconditional start-time ordering
                # from this heuristic; same_day-conditional non-overlap is added elsewhere.
                continue

            if len(day_classes) > 1:
                print(f"  Analyzing group {group} on day {day} with {len(day_classes)} classes")
                
                # Разделение на занятия с фиксированным временем и временными окнами
                fixed_classes = [(idx, c) for idx, c in day_classes if c.start_time and not c.end_time]
                window_classes = [(idx, c) for idx, c in day_classes if c.start_time and c.end_time]
                
                # Сортировка фиксированных занятий по времени начала
                fixed_classes.sort(key=lambda x: time_to_minutes(x[1].start_time))
                
                # Проверяем наличие связанных классов для определения порядка
                linked_order = []
                for chain in getattr(optimizer, "linked_chains", []):
                    # Фильтруем цепочку только для классов в текущем дне/группе
                    window_indices = [idx for idx, _ in window_classes]
                    ordered_indices = [idx for idx in chain if idx in window_indices]
                    if ordered_indices:
                        linked_order.extend(ordered_indices)

                # Сортируем окна - сначала по связанным цепочкам, затем по продолжительности
                def get_window_sort_key(idx_c_pair):
                    idx, c = idx_c_pair
                    if idx in linked_order:
                        return (0, linked_order.index(idx))
                    return (1, c.duration)  # Если нет в цепочке, сортируем по длительности

                window_classes.sort(key=get_window_sort_key)
                
                print(f"    Fixed classes: {len(fixed_classes)}, Window classes: {len(window_classes)}")
                
                # Если есть фиксированные занятия, они служат "якорями"
                if fixed_classes:
                    # Создаем временную шкалу дня
                    timeline = []
                    for idx, c in fixed_classes:
                        start_min = time_to_minutes(c.start_time)
                        end_min = start_min + c.duration + c.pause_after
                        timeline.append((start_min, end_min, idx, c))
                    
                    # Сортируем временную шкалу
                    timeline.sort()
                    
                    # Выводим информацию о фиксированных занятиях
                    print(f"    Fixed classes timeline:")
                    for start_min, end_min, idx, c in timeline:
                        print(f"      Class {idx}: {minutes_to_time(start_min)}-{minutes_to_time(end_min)}")
                    
                    # Находим "свободные окна" между фиксированными занятиями
                    free_slots = []
                    day_start = 8 * 60  # 8:00
                    day_end = 20 * 60    # 20:00
                    buf = optimizer.time_interval  # Буфер в 1 слот текущей сетки
                    
                    # Добавляем слот до первого фиксированного занятия
                    if timeline:
                        first_start = timeline[0][0]
                        if first_start > day_start:
                            free_slots.append((day_start, first_start - buf))
                    
                    # Добавляем слоты между фиксированными занятиями
                    for i in range(len(timeline) - 1):
                        current_end = timeline[i][1] + buf
                        next_start = timeline[i+1][0] - buf
                        if next_start > current_end:
                            free_slots.append((current_end, next_start))
                    
                    # Добавляем слот после последнего фиксированного занятия
                    if timeline:
                        last_end = timeline[-1][1] + buf
                        if last_end < day_end:
                            free_slots.append((last_end, day_end))
                    
                    # Выводим информацию о свободных слотах
                    print(f"    Free time slots:")
                    for start_min, end_min in free_slots:
                        print(f"      {minutes_to_time(start_min)}-{minutes_to_time(end_min)} ({end_min - start_min} min)")
                    
                    # Анализируем связанные классы перед размещением
                    for idx_i, c_i in fixed_classes:
                        if hasattr(c_i, 'linked_classes') and c_i.linked_classes:
                            for linked_class in c_i.linked_classes:
                                try:
                                    linked_idx = optimizer._find_class_index(linked_class)
                                    # Проверяем, является ли связанный класс оконным
                                    if linked_class.start_time and linked_class.end_time:
                                        linked_fixed_classes[linked_idx] = idx_i
                                        print(f"    Fixed class {idx_i} is linked to window class {linked_idx}")
                                except Exception as e:
                                    print(f"    Warning: Error finding linked class: {str(e)}")

                    # Также проверяем связи от оконных к фиксированным
                    for idx_i, c_i in window_classes:
                        if hasattr(c_i, 'linked_classes') and c_i.linked_classes:
                            for linked_class in c_i.linked_classes:
                                try:
                                    linked_idx = optimizer._find_class_index(linked_class)
                                    # Проверяем, является ли связанный класс фиксированным
                                    if linked_class.start_time and not linked_class.end_time:
                                        linked_window_classes[idx_i] = linked_idx
                                        print(f"    Window class {idx_i} is linked to fixed class {linked_idx}")
                                except Exception as e:
                                    print(f"    Warning: Error finding linked class: {str(e)}")

                    # Для каждого занятия с временным окном
                    for window_idx, (idx, c) in enumerate(window_classes):
                        window_start = time_to_minutes(c.start_time)
                        window_end = time_to_minutes(c.end_time)
                        window_duration = window_end - window_start
                        
                        print(f"    Window class {idx}: {c.start_time}-{c.end_time} ({c.duration} min)")
                        
                        # Проверяем, связан ли класс с фиксированным
                        is_linked_to_fixed = False
                        
                        # Проверяем, связан ли этот класс с фиксированным
                        if idx in linked_window_classes:
                            fixed_idx = linked_window_classes[idx]
                            fixed_c = None
                            for fixed_i, fixed_class in fixed_classes:
                                if fixed_i == fixed_idx:
                                    fixed_c = fixed_class
                                    break
                                    
                            if fixed_c:
                                fixed_start = time_to_minutes(fixed_c.start_time)
                                fixed_end = fixed_start + fixed_c.duration + fixed_c.pause_after
                                print(f"    Window class {idx} is linked to fixed class {fixed_idx} starting at {minutes_to_time(fixed_start)}")
                                is_linked_to_fixed = True
                                
                                # Класс должен предшествовать фиксированному
                                adjusted_end = fixed_start - fixed_c.pause_before
                                
                                # Ищем подходящий слот до фиксированного занятия
                                best_slot = None
                                for slot_start, slot_end in free_slots:
                                    # Проверяем, перекрывается ли слот с временем до фиксированного занятия
                                    if slot_start < adjusted_end and slot_end > slot_start:
                                        # Ограничиваем конец слота концом окна
                                        real_end = min(slot_end, adjusted_end)
                                        # Проверяем, помещается ли занятие
                                        if real_end - slot_start >= c.duration:
                                            best_slot = (slot_start, slot_end)
                                            break
                                
                                if best_slot:
                                    slot_start, slot_end = best_slot
                                    # Рассчитываем реальный диапазон размещения
                                    real_start = slot_start
                                    real_end = min(slot_end, adjusted_end)
                                    
                                    # Находим допустимый диапазон начала
                                    start_min = real_start
                                    start_max = real_end - c.duration
                                    
                                    # Преобразуем в индексы слотов
                                    start_min_slot = find_slot_for_time(optimizer, minutes_to_time(start_min), "ceil")
                                    start_max_slot = find_slot_for_time(optimizer, minutes_to_time(start_max), "floor")
                                    
                                    print(f"      Placing linked class before fixed class: {minutes_to_time(start_min)}-{minutes_to_time(start_max)}")
                                    
                                    # Добавляем ограничения на время начала
                                    if start_max_slot >= start_min_slot:
                                        optimizer.model.Add(optimizer.start_vars[idx] >= start_min_slot)
                                        optimizer.model.Add(optimizer.start_vars[idx] <= start_max_slot)
                                    else:
                                        print(
                                            f"WARNING: Slot inversion for class {idx}: "
                                            f"max_slot={start_max_slot} ({optimizer.time_slots[start_max_slot]}) < "
                                            f"min_slot={start_min_slot} ({optimizer.time_slots[start_min_slot]}), "
                                            f"skipping placement constraint"
                                        )
                                    
                                    # Обновляем свободные слоты
                                    free_slots.remove(best_slot)
                                    
                                    # Начало и конец реального размещения класса
                                    actual_start = start_max  # Предпочитаем размещение ближе к фиксированному занятию
                                    actual_end = actual_start + c.duration + c.pause_after
                                    
                                    # Если есть свободное место до начала класса
                                    if actual_start > slot_start:
                                        free_slots.append((slot_start, actual_start - buf))
                                    
                                    # Если есть свободное место после конца класса до начала фиксированного
                                    if actual_end + buf < adjusted_end:
                                        free_slots.append((actual_end + buf, adjusted_end - buf))
                                    
                                    # Если конец исходного слота после конца фиксированного занятия
                                    if slot_end > fixed_end + buf:
                                        free_slots.append((fixed_end + buf, slot_end))
                                    
                                    print(f"      Updated free slots after placing linked class {idx}:")
                                    for s_start, s_end in free_slots:
                                        print(f"        {minutes_to_time(s_start)}-{minutes_to_time(s_end)} ({s_end - s_start} min)")
                                    
                                    # Добавляем ограничения между этим занятием и фиксированными занятиями
                                    for fixed_idx, fixed_c in fixed_classes:
                                        pair_key = (min(idx, fixed_idx), max(idx, fixed_idx))
                                        if pair_key not in processed_pairs:
                                            add_time_separation_constraints(optimizer, idx, fixed_idx, c, fixed_c)
                                            processed_pairs.add(pair_key)
                                    
                                    # Добавляем ограничения между этим занятием и предыдущими оконными занятиями
                                    for prev_window_idx in range(window_idx):
                                        prev_idx, prev_c = window_classes[prev_window_idx]
                                        pair_key = (min(idx, prev_idx), max(idx, prev_idx))
                                        if pair_key not in processed_pairs:
                                            add_time_separation_constraints(optimizer, idx, prev_idx, c, prev_c)
                                            processed_pairs.add(pair_key)
                                    
                                    continue  # Переходим к следующему классу, этот уже обработан
                        
                        # Если класс не связан с фиксированным или связь не обработана
                        # Стандартный поиск свободного слота
                        best_slot = None
                        best_fit = 0
                        
                        for slot_start, slot_end in free_slots:
                            # Находим пересечение слота и временного окна
                            overlap_start = max(slot_start, window_start)
                            overlap_end = min(slot_end, window_end)
                            overlap_size = overlap_end - overlap_start
                            
                            # Если занятие помещается в слот и это лучшее совпадение
                            if overlap_size >= c.duration and overlap_size > best_fit:
                                best_slot = (slot_start, slot_end)
                                best_fit = overlap_size
                        
                        if best_slot:
                            # Нашли подходящий слот - создаем ограничения
                            slot_start, slot_end = best_slot
                            
                            # Находим пересечение слота и временного окна
                            overlap_start = max(slot_start, window_start)
                            overlap_end = min(slot_end, window_end)
                            
                            # Рассчитываем допустимый диапазон начала
                            start_min = overlap_start
                            start_max = overlap_end - c.duration
                            
                            # Преобразуем в индексы слотов
                            start_min_slot = find_slot_for_time(optimizer, minutes_to_time(start_min), "ceil")
                            start_max_slot = find_slot_for_time(optimizer, minutes_to_time(start_max), "floor")
                            
                            print(f"      Placing in slot {minutes_to_time(start_min)}-{minutes_to_time(start_max)}")
                            
                            # Добавляем ограничения на время начала
                            if start_max_slot >= start_min_slot:
                                optimizer.model.Add(optimizer.start_vars[idx] >= start_min_slot)
                                optimizer.model.Add(optimizer.start_vars[idx] <= start_max_slot)
                            else:
                                print(
                                    f"WARNING: Slot inversion for class {idx}: "
                                    f"max_slot={start_max_slot} ({optimizer.time_slots[start_max_slot]}) < "
                                    f"min_slot={start_min_slot} ({optimizer.time_slots[start_min_slot]}), "
                                    f"skipping placement constraint"
                                )
                            
                            # Отмечаем использованный слот и добавляем оставшиеся части
                            free_slots.remove(best_slot)
                            
                            # Начало и конец реального размещения класса
                            actual_start = start_min  # Предпочитаем раннее начало для стандартных классов
                            actual_end = actual_start + c.duration + c.pause_after  
                            
                            # Если есть свободное место до начала класса
                            if actual_start > slot_start:
                                free_slots.append((slot_start, actual_start - buf))
                                
                            # Если есть свободное место после конца класса
                            if actual_end + buf < slot_end:
                                free_slots.append((actual_end + buf, slot_end))
                                
                            print(f"      Updated free slots after placing class {idx}:")
                            for s_start, s_end in free_slots:
                                print(f"        {minutes_to_time(s_start)}-{minutes_to_time(s_end)} ({s_end - s_start} min)")
                            
                            # Добавляем ограничения между этим занятием и фиксированными занятиями
                            for fixed_idx, fixed_c in fixed_classes:
                                pair_key = (min(idx, fixed_idx), max(idx, fixed_idx))
                                if pair_key not in processed_pairs:
                                    add_time_separation_constraints(optimizer, idx, fixed_idx, c, fixed_c)
                                    processed_pairs.add(pair_key)
                            
                            # Добавляем ограничения между этим занятием и предыдущими оконными занятиями
                            for prev_window_idx in range(window_idx):
                                prev_idx, prev_c = window_classes[prev_window_idx]
                                pair_key = (min(idx, prev_idx), max(idx, prev_idx))
                                if pair_key not in processed_pairs:
                                    add_time_separation_constraints(optimizer, idx, prev_idx, c, prev_c)
                                    processed_pairs.add(pair_key)
                        else:
                            print(f"      WARNING: Could not find suitable slot for class {idx}")
                            
                            # В случае неудачи попробуем найти наилучшее пересечение с окном
                            best_overlap = 0
                            best_range = None
                            
                            for slot_start, slot_end in free_slots:
                                overlap_start = max(slot_start, window_start)
                                overlap_end = min(slot_end, window_end)
                                overlap_size = overlap_end - overlap_start
                                
                                if overlap_size > best_overlap:
                                    best_overlap = overlap_size
                                    best_range = (overlap_start, overlap_end)
                            
                            if best_range:
                                start_min, end_min = best_range
                                print(f"      Placing with partial fit {minutes_to_time(start_min)}-{minutes_to_time(end_min)} ({end_min - start_min} min)")
                                
                                # Преобразуем в индексы слотов
                                start_min_slot = find_slot_for_time(optimizer, minutes_to_time(start_min), "ceil")
                                start_max_slot = find_slot_for_time(optimizer, minutes_to_time(end_min - c.duration), "floor")
                                
                                if start_max_slot >= start_min_slot:
                                    # Можем хотя бы частично разместить
                                    optimizer.model.Add(optimizer.start_vars[idx] >= start_min_slot)
                                    optimizer.model.Add(optimizer.start_vars[idx] <= start_max_slot)
                                else:
                                    # Очень сложный случай - просто пытаемся максимизировать расстояние от других занятий
                                    print(f"      CRITICAL: Cannot fit class in any free slot, using general constraints")
                
                # Случай, когда нет фиксированных занятий, но есть несколько оконных
                elif len(window_classes) > 1:
                    print(f"    No fixed classes, scheduling {len(window_classes)} window classes sequentially")
                    
                    # Находим общее временное окно
                    common_start = max(time_to_minutes(c.start_time) for _, c in window_classes)
                    common_end = min(time_to_minutes(c.end_time) for _, c in window_classes)
                    
                    print(f"    Common window: {minutes_to_time(common_start)}-{minutes_to_time(common_end)} ({common_end - common_start} min)")
                    
                    # Рассчитываем общую требуемую длительность
                    total_duration = sum(c.duration for _, c in window_classes)
                    # Учитываем паузы между занятиями
                    total_pauses = sum(c.pause_after for _, c in window_classes[:-1]) + \
                                sum(c.pause_before for _, c in window_classes[1:])
                    
                    total_minutes = total_duration + total_pauses
                    
                    print(f"    Total required time: {total_minutes} min (classes: {total_duration} min, pauses: {total_pauses} min)")
                    
                    if common_end - common_start >= total_minutes:
                        # Достаточно времени для последовательного размещения
                        print(f"    Sufficient time for sequential scheduling")
                        
                        # Начинаем с начала общего окна
                        current_time = common_start
                        
                        # Размещаем занятия последовательно
                        for i, (idx, c) in enumerate(window_classes):
                            # Находим слот для текущего времени
                            time_str = minutes_to_time(int(current_time))
                            start_slot = find_slot_for_time(optimizer, time_str, "ceil")
                            
                            print(f"      Class {idx} at {time_str} (slot {start_slot})")
                            
                            # В блоке обработки последовательных занятий без фиксированных уроков
                            # Заменить жесткую фиксацию времени начала для всех кроме первого занятия
                            if i == 0:
                                # Для первого занятия задаем только нижнюю границу,
                                # чтобы сохранить гибкость временного окна.
                                constraint = optimizer.model.Add(optimizer.start_vars[idx] >= start_slot)
                                print(f"DEBUG: Added lower bound for first class: start_vars[{idx}] >= {start_slot} ({optimizer.time_slots[start_slot]})")
                            else:
                                # Для последующих - проверяем, не было ли уже добавлено ограничение
                                prev_idx, prev_c = window_classes[i-1]
                                pair_key = (prev_idx, idx)
                                reversed_key = (idx, prev_idx)
                                
                                # Проверяем, не было ли уже добавлено ограничение между этими классами
                                already_constrained = False
                                if hasattr(optimizer, "applied_constraints"):
                                    already_constrained = pair_key in optimizer.applied_constraints or reversed_key in optimizer.applied_constraints
                                
                                # Проверяем положение в связанной цепочке
                                in_same_chain = False
                                if not already_constrained and hasattr(optimizer, "linked_chains"):
                                    in_same_chain, chain_order = get_linked_chain_order(optimizer, prev_idx, idx)
                                    # Если не в правильном порядке по цепочке, не добавляем ограничение
                                    if in_same_chain and chain_order <= 0:
                                        print(f"  WARNING: Classes {prev_idx} and {idx} are in wrong order in linked chain")
                                        already_constrained = True

                                if not already_constrained:
                                    # Ограничение: текущее занятие должно начаться ПОСЛЕ завершения предыдущего + пауза
                                    prev_duration_slots = prev_c.duration // optimizer.time_interval
                                    prev_pause_slots = pause_to_slots(prev_c.pause_after, optimizer.time_interval)
                                    current_pause_before_slots = pause_to_slots(c.pause_before, optimizer.time_interval)
                                    
                                    # Минимальное время начала - после окончания предыдущего занятия + паузы
                                    total_gap = prev_duration_slots + prev_pause_slots + current_pause_before_slots
                                    print(f"DEBUG: Adding sequential constraint: start_vars[{idx}] >= start_vars[{prev_idx}] + {total_gap}")
                                    constraint = optimizer.model.Add(optimizer.start_vars[idx] >= 
                                            optimizer.start_vars[prev_idx] + prev_duration_slots + prev_pause_slots + current_pause_before_slots)
                                    print(f"DEBUG: Added constraint {constraint}: start_vars[{idx}] >= start_vars[{prev_idx}] + {total_gap}")
                                    
                                    # Не добавляем ограничение на максимальное время начала - это уже есть в ограничениях окна
                                    print(f"  Added sequential constraint: {prev_idx} -> {idx}")
                                    
                                    # Сохраняем примененные ограничения
                                    if not hasattr(optimizer, "applied_constraints"):
                                        optimizer.applied_constraints = {}
                                    optimizer.applied_constraints[pair_key] = constraint
                                else:
                                    print(f"  Sequential constraint already exists: {prev_idx} -> {idx}")
                            
                            # Обновляем текущее время для следующего занятия - только паузы, без дополнительных промежутков
                            current_time += c.duration + c.pause_after
                            if i < len(window_classes) - 1:
                                current_time += window_classes[i+1][1].pause_before
                            
                            # Добавляем ограничения между этим занятием и предыдущими оконными занятиями
                            for prev_i in range(i):
                                prev_idx, prev_c = window_classes[prev_i]
                                pair_key = (min(idx, prev_idx), max(idx, prev_idx))
                                # Проверяем, не обработана ли уже пара и не в списке ли обработанных связанных занятий
                                if pair_key not in processed_pairs and idx not in linked_processed and prev_idx not in linked_processed:
                                    add_time_separation_constraints(optimizer, idx, prev_idx, c, prev_c)
                                    processed_pairs.add(pair_key)
                                    # Если это связанные занятия, отмечаем их обработанными
                                    if is_in_linked_chain(optimizer, idx) and is_in_linked_chain(optimizer, prev_idx):
                                        linked_processed.add(idx)
                                        linked_processed.add(prev_idx)
                    else:
                        # Недостаточно времени - используем стандартные ограничения
                        print(f"    WARNING: Not enough time for sequential scheduling, using separation constraints")
                        
                        # Добавляем ограничения между всеми парами занятий
                        for i in range(len(window_classes)):
                            idx_i, c_i = window_classes[i]
                            for j in range(i+1, len(window_classes)):
                                idx_j, c_j = window_classes[j]
                                pair_key = (min(idx_i, idx_j), max(idx_i, idx_j))
                                if pair_key not in processed_pairs:
                                    add_time_separation_constraints(optimizer, idx_i, idx_j, c_i, c_j)
                                    processed_pairs.add(pair_key)
                                    
                                    # Определяем, какому занятию предпочтительно начинаться позже
                                    if c_i.duration <= c_j.duration:
                                        # Если первое занятие короче, пусть оно начнется раньше
                                        prefer_late_start.add(idx_j)
                                    else:
                                        # Иначе пусть второе занятие начнется раньше
                                        prefer_late_start.add(idx_i)
    
    # Обработка классов по преподавателям
    print("\nProcessing classes by teachers:")
    for teacher, teacher_classes in classes_by_teacher.items():
        # Фильтрация занятий по дням
        classes_by_day = {}
        for idx, c in teacher_classes:
            if c.day not in classes_by_day:
                classes_by_day[c.day] = []
            classes_by_day[c.day].append((idx, c))
        
        # Обработка каждого дня отдельно  
        for day, day_classes in classes_by_day.items():
            if day is None:
                # Variable-day classes must not receive unconditional start-time ordering
                # from this heuristic; same_day-conditional non-overlap is added elsewhere.
                continue

            if len(day_classes) > 1:
                print(f"  Teacher {teacher} on day {day} with {len(day_classes)} classes")
                
                # Пропускаем классы с общими группами (они уже обработаны)
                need_processing = []
                for i, (idx_i, c_i) in enumerate(day_classes):
                    has_shared_group = False
                    for j, (idx_j, c_j) in enumerate(day_classes):
                        if i != j:
                            shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
                            if shared_groups:
                                has_shared_group = True
                                break
                    
                    if not has_shared_group:
                        need_processing.append((idx_i, c_i))
                
                if not need_processing:
                    print(f"    All classes have shared groups, already processed")
                    continue
                
                print(f"    Processing {len(need_processing)} classes without shared groups")
                
                # Разделение на занятия с фиксированным временем и временными окнами
                fixed_classes = [(idx, c) for idx, c in need_processing if c.start_time and not c.end_time]
                window_classes = [(idx, c) for idx, c in need_processing if c.start_time and c.end_time]
                
                # Сортировка фиксированных занятий по времени начала
                fixed_classes.sort(key=lambda x: time_to_minutes(x[1].start_time))
                
                # Проверяем наличие связанных классов для определения порядка
                linked_order = []
                for chain in getattr(optimizer, "linked_chains", []):
                    # Фильтруем цепочку только для классов в текущем дне/группе
                    window_indices = [idx for idx, _ in window_classes]
                    ordered_indices = [idx for idx in chain if idx in window_indices]
                    if ordered_indices:
                        linked_order.extend(ordered_indices)

                # Сортируем окна - сначала по связанным цепочкам, затем по продолжительности
                def get_window_sort_key(idx_c_pair):
                    idx, c = idx_c_pair
                    if idx in linked_order:
                        return (0, linked_order.index(idx))
                    return (1, c.duration)  # Если нет в цепочке, сортируем по длительности

                window_classes.sort(key=get_window_sort_key)
                
                print(f"    Fixed classes: {len(fixed_classes)}, Window classes: {len(window_classes)}")
                
                # Добавляем ограничения между всеми парами занятий
                for i in range(len(need_processing)):
                    idx_i, c_i = need_processing[i]
                    for j in range(i+1, len(need_processing)):
                        idx_j, c_j = need_processing[j]
                        pair_key = (min(idx_i, idx_j), max(idx_i, idx_j))
                        if pair_key not in processed_pairs:
                            # Проверяем возможность последовательного размещения
                            can_schedule, info = can_schedule_sequentially(c_i, c_j)
                            
                            if can_schedule:
                                print(f"      Classes {idx_i} and {idx_j} can be scheduled sequentially: {info['reason']}")
                                
                                # Отмечаем пару как обработанную
                                processed_pairs.add(pair_key)
                                
                                if info['reason'] == 'fits_before_fixed':
                                    # Первое занятие должно быть до второго
                                    fixed_slot = find_slot_for_time(optimizer, c_j.start_time, "ceil")
                                    end_slot = fixed_slot - pause_to_slots(c_j.pause_before, optimizer.time_interval)
                                    pause_after_i_slots = pause_to_slots(c_i.pause_after, optimizer.time_interval)
                                    start_slot = end_slot - ((c_i.duration // optimizer.time_interval) + pause_after_i_slots)
                                    
                                    print(f"        Class {idx_i} must end before {c_j.start_time}")
                                    optimizer.model.Add(
                                        optimizer.start_vars[idx_i]
                                        + (c_i.duration // optimizer.time_interval)
                                        + pause_after_i_slots
                                        <= end_slot
                                    )
                                
                                elif info['reason'] == 'fits_after_fixed':
                                    # Первое занятие должно быть после второго
                                    fixed_slot = find_slot_for_time(optimizer, c_j.start_time, "ceil")
                                    end_slot = fixed_slot + (c_j.duration // optimizer.time_interval)
                                    start_slot = end_slot + pause_to_slots(c_j.pause_after, optimizer.time_interval)
                                    
                                    print(f"        Class {idx_i} must start after class {idx_j} ends")
                                    optimizer.model.Add(optimizer.start_vars[idx_i] >= start_slot)
                                
                                elif info['reason'] == 'both_orders_possible':
                                    # Можно разместить в любом порядке - добавляем ограничение на непересечение
                                    add_time_separation_constraints(optimizer, idx_i, idx_j, c_i, c_j)
                                
                                elif 'fits_in_common_window' in info['reason']:
                                    # Можно разместить в общем окне - добавляем ограничение на непересечение
                                    add_time_separation_constraints(optimizer, idx_i, idx_j, c_i, c_j)
                            else:
                                print(f"      WARNING: Classes {idx_i} and {idx_j} cannot be scheduled sequentially")
                                
                                # Добавляем ограничение на непересечение, если нужно
                                if (c_i.start_time and c_j.start_time) and (not c_i.end_time or not c_j.end_time):
                                    # Хотя бы одно занятие с фиксированным временем - проверяем пересечение
                                    if not c_i.end_time and not c_j.end_time:
                                        # Оба фиксированные - определяем пересечение явно
                                        start_i = time_to_minutes(c_i.start_time)
                                        end_i = start_i + c_i.duration
                                        start_j = time_to_minutes(c_j.start_time)
                                        end_j = start_j + c_j.duration
                                        
                                        if (start_i < end_j) and (start_j < end_i):
                                            print(f"        CONFLICT: Fixed time classes overlap")
                                    else:
                                        # Добавляем ограничение на непересечение
                                        add_time_separation_constraints(optimizer, idx_i, idx_j, c_i, c_j)
                                        processed_pairs.add(pair_key)
    
    # Сохраняем информацию о предпочтениях в оптимизаторе
    optimizer.prefer_late_start = prefer_late_start
    
    return processed_pairs

def apply_timewindow_improvements(optimizer):
    """
    Применяет улучшения для обработки временных окон к оптимизатору.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        
    Returns:
        bool: True, если улучшения применены успешно
    """
    print("\nApplying timewindow scheduling improvements...")

    prefer_late_start = set()  # Индексы занятий, которым лучше начинаться позже

    # Сбрасываем кэш обработанных проверок между занятиями
    try:
        from sequential_scheduling_checker import reset_window_checks_cache
        reset_window_checks_cache()
    except ImportError:
        print("Warning: Could not reset window checks cache.")
    
    # Словарь для отслеживания уже обработанных пар занятий
    processed_pairs = set()

    # Проверяем, инициализированы ли уже переменные оптимизатора
    if not hasattr(optimizer, 'start_vars') or not optimizer.start_vars:
        print("Warning: Optimizer variables not initialized yet. Call optimizer.build_model() before applying timewindow improvements.")
        return False
                    
    # Общий анализ занятий с временными окнами
    window_classes = []
    for idx, c in enumerate(optimizer.classes):
        if c.start_time and c.end_time:
            window_classes.append((idx, c))
    
    print(f"\nFound {len(window_classes)} classes with time windows.")
    
    # Для каждого занятия с временным окном добавляем ограничения на временное окно
    for idx_i, c_i in window_classes:
        # Проверяем имеется ли уже фиксированное ограничение для этого занятия
        # и если нет, добавляем ограничения на временное окно
        if not isinstance(optimizer.start_vars[idx_i], int):
            window_start_time = c_i.start_time
            window_end_time = c_i.end_time

            window_start_slot = optimizer.time_to_slot_ceil(window_start_time)
            latest_start_minutes = time_to_minutes(window_end_time) - c_i.duration
            max_start_slot = optimizer.minutes_to_slot_floor(latest_start_minutes)

            if max_start_slot >= window_start_slot:
                constraint1 = optimizer.model.Add(optimizer.start_vars[idx_i] >= window_start_slot)
                constraint2 = optimizer.model.Add(optimizer.start_vars[idx_i] <= max_start_slot)
                #---Debug---
                print(f"DEBUG: Added window constraints for class {idx_i}:")
                print(f"  - Lower bound: {constraint1} - start_vars[{idx_i}] >= {window_start_slot} ({optimizer.time_slots[window_start_slot]})")
                print(f"  - Upper bound: {constraint2} - start_vars[{idx_i}] <= {max_start_slot} ({optimizer.time_slots[max_start_slot]})")
                #-----------
                print(f"  Added window constraints for class {idx_i}: start between slots {window_start_slot} and {max_start_slot}")
    
    # Применяем новый алгоритм комплексного анализа связанных занятий
    processed_pairs = analyze_related_classes(optimizer)
    
    print("\nTimewindow improvements applied successfully.")
    return True

def add_objective_weights_for_timewindows(optimizer):
    """
    Добавляет веса к целевой функции для улучшения планирования с временными окнами.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        
    Returns:
        list: Дополнительные термы для целевой функции
    """
    additional_terms = []
    
    # 1. Для стандартных занятий добавляем стимул начинать как можно раньше
    for idx, c in enumerate(optimizer.classes):
        if not isinstance(optimizer.start_vars[idx], int):
            # Проверяем, не в списке ли занятий для позднего начала
            if idx not in getattr(optimizer, "prefer_late_start", set()):
                # Добавляем увеличенный штраф пропорциональный времени начала
                additional_terms.append(optimizer.start_vars[idx] * 15)  # Увеличенный вес для более раннего начала
    
    # 2. Для занятий с временными окнами 
    for idx, c in enumerate(optimizer.classes):
        if c.start_time and c.end_time and not isinstance(optimizer.start_vars[idx], int):
            window_start = time_to_minutes(c.start_time)
            window_end = time_to_minutes(c.end_time)
            window_size = window_end - window_start
            
            # Находим соответствующие временные слоты
            window_start_slot = optimizer.time_to_slot_ceil(c.start_time)
            latest_start_minutes = window_end - c.duration
            max_start_slot = optimizer.minutes_to_slot_floor(latest_start_minutes)

            if max_start_slot >= window_start_slot:
                # Проверяем, должно ли это занятие начинаться позже
                if idx in getattr(optimizer, "prefer_late_start", set()):
                    # Prefer later start inside the valid window domain.
                    distance_from_end = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"end_distance_{idx}")
                    optimizer.model.Add(distance_from_end == max_start_slot - optimizer.start_vars[idx])
                    
                    # Значительно больший вес для стимулирования позднего начала
                    flexibility_factor = 200
                    additional_terms.append(distance_from_end * flexibility_factor)
                    print(f"  Added VERY STRONG incentive for class {idx} to start LATER (weight: {flexibility_factor})")
                else:
                    # Стандартное поведение - стимулируем раннее начало
                    delay_var = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"window_delay_{idx}")
                    optimizer.model.Add(delay_var == optimizer.start_vars[idx] - window_start_slot)
                    
                    flexibility_factor = min(16, 6 + (window_size // 60))
                    additional_terms.append(delay_var * flexibility_factor)
    
    # 3. Дополнительно проверяем задержки, установленные в analyze_related_classes
    if hasattr(optimizer, "prefer_window_start_delay"):
        for idx, delay_var in optimizer.prefer_window_start_delay.items():
            # Добавляем штраф за задержку начала в слоте
            additional_terms.append(delay_var * 10)
            print(f"  Added incentive for class {idx} to start EARLY in its assigned slot (weight: 10)")
    
    return additional_terms








