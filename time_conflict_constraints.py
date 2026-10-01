"""
Модуль для добавления ограничений по времени и предотвращения конфликтов.
"""
from time_utils import time_to_minutes, minutes_to_time, pause_to_slots
from time_constraint_utils import create_conflict_variables, add_time_overlap_constraints
from sequential_scheduling_checker import check_two_window_classes
from sequential_scheduling import can_schedule_sequentially

def add_sequential_constraints(optimizer, i, j, c_i, c_j):
    """
    Добавляет строгие ограничения для последовательного размещения занятий
    """
    # Создаем булеву переменную для определения порядка занятий
    i_before_j = optimizer.model.NewBoolVar(f"seq_strict_{i}_{j}")
    
    # Расчет длительности в слотах времени
    duration_i_slots = c_i.duration // optimizer.time_interval
    duration_j_slots = c_j.duration // optimizer.time_interval
    
    # Переменные для конца занятий
    end_i = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"seq_end_{i}")
    end_j = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"seq_end_{j}")
    
    # Устанавливаем значения концов занятий
    optimizer.model.Add(end_i == optimizer.start_vars[i] + duration_i_slots)
    optimizer.model.Add(end_j == optimizer.start_vars[j] + duration_j_slots)
    
    # Направленные интервалы между занятиями: зависят от выбранного порядка.
    pause_i_j = pause_to_slots(c_i.pause_after + c_j.pause_before, optimizer.time_interval)
    pause_j_i = pause_to_slots(c_j.pause_after + c_i.pause_before, optimizer.time_interval)
    
    # Строгое ограничение: i перед j или j перед i, без перекрытия
    optimizer.model.Add(end_i + pause_i_j <= optimizer.start_vars[j]).OnlyEnforceIf(i_before_j)
    optimizer.model.Add(end_j + pause_j_i <= optimizer.start_vars[i]).OnlyEnforceIf(i_before_j.Not())
    
    print(
        f"  Added STRICT sequential constraints between classes {i} and {j} "
        f"(directional pauses: i->j={pause_i_j}, j->i={pause_j_i} slots)"
    )


def _create_same_room_var(optimizer, i, j):
    """Создает BoolVar same_room для пары занятий."""
    same_room = optimizer.model.NewBoolVar(f"same_room_{i}_{j}")
    room_i = optimizer.room_vars[i]
    room_j = optimizer.room_vars[j]

    if isinstance(room_i, int) and isinstance(room_j, int):
        optimizer.model.Add(same_room == int(room_i == room_j))
    elif isinstance(room_i, int):
        optimizer.model.Add(room_j == room_i).OnlyEnforceIf(same_room)
        optimizer.model.Add(room_j != room_i).OnlyEnforceIf(same_room.Not())
    elif isinstance(room_j, int):
        optimizer.model.Add(room_i == room_j).OnlyEnforceIf(same_room)
        optimizer.model.Add(room_i != room_j).OnlyEnforceIf(same_room.Not())
    else:
        optimizer.model.Add(room_i == room_j).OnlyEnforceIf(same_room)
        optimizer.model.Add(room_i != room_j).OnlyEnforceIf(same_room.Not())

    return same_room


def _forbid_same_day_overlap(optimizer, conflict, same_day, time_overlap):
    """Запрещает пересечение времени в один день."""
    optimizer.model.AddBoolAnd([same_day, time_overlap]).OnlyEnforceIf(conflict)
    optimizer.model.AddBoolOr([same_day.Not(), time_overlap.Not()]).OnlyEnforceIf(conflict.Not())
    optimizer.model.Add(conflict == 0)


def _forbid_same_day_overlap_if_same_room(optimizer, i, j, same_day, time_overlap):
    """Запрещает пересечение времени только если выбрана одна и та же аудитория."""
    same_room = _create_same_room_var(optimizer, i, j)
    room_conflict = optimizer.model.NewBoolVar(f"room_conflict_{i}_{j}")
    optimizer.model.AddBoolAnd([same_day, time_overlap, same_room]).OnlyEnforceIf(room_conflict)
    optimizer.model.AddBoolOr(
        [same_day.Not(), time_overlap.Not(), same_room.Not()]
    ).OnlyEnforceIf(room_conflict.Not())
    optimizer.model.Add(room_conflict == 0)


def _add_conditional_room_overlap_constraint(optimizer, i, j, c_i, c_j):
    """
    Добавляет условный запрет overlap только при выборе одной и той же комнаты.
    """
    same_day = optimizer.model.NewBoolVar(f"same_day_room_only_{i}_{j}")
    if isinstance(optimizer.day_vars[i], int) and isinstance(optimizer.day_vars[j], int):
        optimizer.model.Add(same_day == int(optimizer.day_vars[i] == optimizer.day_vars[j]))
    elif isinstance(optimizer.day_vars[i], int):
        optimizer.model.Add(optimizer.day_vars[j] == optimizer.day_vars[i]).OnlyEnforceIf(same_day)
        optimizer.model.Add(optimizer.day_vars[j] != optimizer.day_vars[i]).OnlyEnforceIf(same_day.Not())
    elif isinstance(optimizer.day_vars[j], int):
        optimizer.model.Add(optimizer.day_vars[i] == optimizer.day_vars[j]).OnlyEnforceIf(same_day)
        optimizer.model.Add(optimizer.day_vars[i] != optimizer.day_vars[j]).OnlyEnforceIf(same_day.Not())
    else:
        optimizer.model.Add(optimizer.day_vars[i] == optimizer.day_vars[j]).OnlyEnforceIf(same_day)
        optimizer.model.Add(optimizer.day_vars[i] != optimizer.day_vars[j]).OnlyEnforceIf(same_day.Not())

    time_overlap = optimizer.model.NewBoolVar(f"time_overlap_room_only_{i}_{j}")
    add_time_overlap_constraints(optimizer, i, j, c_i, c_j, time_overlap)
    _forbid_same_day_overlap_if_same_room(optimizer, i, j, same_day, time_overlap)

def _add_time_conflict_constraints(optimizer, i, j, c_i, c_j):
    """
    Добавляет ограничения для предотвращения конфликтов времени между занятиями.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        i, j: Индексы классов
        c_i, c_j: Экземпляры ScheduleClass
    """
    # Пропускаем пару только когда оба дня фиксированы и различаются.
    day_i = optimizer.day_vars[i]
    day_j = optimizer.day_vars[j]
    both_days_fixed = isinstance(day_i, int) and isinstance(day_j, int)
    if both_days_fixed and day_i != day_j:
        return
    
    # Проверяем наличие общих аудиторий/групп и конфликта преподавателя
    shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
    shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
    teacher_conflict = bool(c_i.teacher and c_i.teacher == c_j.teacher)

    # Флаг для обязательного добавления ограничений при общих группах
    must_add_constraints = bool(teacher_conflict or shared_groups or shared_rooms)
    
    # Если оба занятия имеют фиксированное время начала
    if c_i.fixed_start_time and c_j.fixed_start_time:
        # Оба занятия фиксированные - проверяем реальное пересечение
        conflict, same_day, time_overlap = create_conflict_variables(optimizer, i, j, c_i, c_j)
        add_time_overlap_constraints(optimizer, i, j, c_i, c_j, time_overlap)
        
        if teacher_conflict or shared_groups:
            _forbid_same_day_overlap(optimizer, conflict, same_day, time_overlap)
        elif shared_rooms:
            _forbid_same_day_overlap_if_same_room(optimizer, i, j, same_day, time_overlap)
        
        return  # Только после добавления всех проверок для общих аудиторий

    # При переменном дне не применяем эвристики, которые добавляют
    # безусловные ограничения по start_vars без привязки к same_day.
    if not both_days_fixed:
        if not must_add_constraints:
            return

        print(
            f"  [variable-day] skipping sequential heuristics for classes {i},{j}; "
            f"using same_day-conditional conflict constraints"
        )
        conflict, same_day, time_overlap = create_conflict_variables(optimizer, i, j, c_i, c_j)
        add_time_overlap_constraints(optimizer, i, j, c_i, c_j, time_overlap)

        if teacher_conflict or shared_groups:
            _forbid_same_day_overlap(optimizer, conflict, same_day, time_overlap)
        elif shared_rooms:
            _forbid_same_day_overlap_if_same_room(optimizer, i, j, same_day, time_overlap)
        return

    # Изменение логики проверки временного перекрытия
    # Проверяем наличие пересечения времени или общих аудиторий
    time_overlaps = times_overlap(c_i, c_j)
    if not time_overlaps and not shared_rooms:
        # Нет пересечения времени и нет общих аудиторий - можно пропустить проверку
        return
    
    # 0) Спец.-случай: оба занятия имеют временные окна и нет конфликта ресурсов.
    #    Проверяем, можно ли их разместить подряд; если да — ограничений не нужно.
    if c_i.start_time and c_i.end_time and c_j.start_time and c_j.end_time and not must_add_constraints:
        if check_two_window_classes(optimizer, i, j, c_i, c_j):
            # Нет конфликта ресурсов, и занятия помещаются подряд -> ничего не добавляем.
            print(f"  [window-window] no resource conflict, sequential fit confirmed for classes {i},{j}")
            return

        # Окна перекрываются, но совместно не вмещают оба занятия.
        # Конфликта ресурсов нет -> ограничений добавлять не нужно.
        print(f"  [window-window] no resource conflict, no sequential fit - no constraints needed for classes {i},{j}")
        return
    # Проверяем возможность последовательного размещения для занятий одного преподавателя
    if c_i.teacher == c_j.teacher and c_i.teacher:
        # Проверяем наличие общих групп
        shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())

        # Для занятий с общими группами вычисляем оба направления один раз
        if shared_groups:
            can_seq_i_j, info_i_j = can_schedule_sequentially(c_i, c_j)
            can_seq_j_i, info_j_i = can_schedule_sequentially(c_j, c_i)

            # Проверяем случай, когда одно занятие фиксированное, а другое оконное
            # Если фиксированное c_i и оконное c_j
            if c_i.start_time and not c_i.end_time and c_j.start_time and c_j.end_time:
                if can_seq_i_j and info_i_j['reason'] == 'fits_before_fixed':
                    # c_j можно разместить ДО c_i - предпочитаем этот вариант
                    fixed_start = time_to_minutes(c_i.start_time)
                    latest_end = fixed_start - c_i.pause_before
                    latest_start = latest_end - c_j.pause_after - c_j.duration
                    latest_slot_idx = optimizer.minutes_to_slot_floor(latest_start)

                    print(f"  [shared_groups] PRIORITIZING window class {j} BEFORE fixed class {i}")
                    optimizer.model.Add(optimizer.start_vars[j] <= latest_slot_idx)
                    return
                elif can_seq_i_j and info_i_j['reason'] == 'fits_after_fixed':
                    # c_j можно разместить ПОСЛЕ c_i
                    fixed_start = time_to_minutes(c_i.start_time)
                    fixed_end = fixed_start + c_i.duration + c_i.pause_after

                    earliest_start = fixed_end + c_j.pause_before
                    earliest_slot = optimizer.minutes_to_slot_ceil(earliest_start)

                    # Проверяем, хватает ли времени для размещения ПОСЛЕ
                    window_end = time_to_minutes(c_j.end_time)
                    if (window_end - optimizer.slot_to_minutes(earliest_slot)) >= c_j.duration:
                        print(f"  [shared_groups] Applying AFTER-fixed for class {j}")
                        optimizer.model.Add(optimizer.start_vars[j] >= earliest_slot)
                    else:
                        print(f"  [WARNING] Not enough time to schedule {j} after {i}, but forcing BEFORE-fixed")
                        # Принудительно размещаем ДО, даже если первоначально это не было обнаружено
                        latest_end = fixed_start - c_i.pause_before
                        latest_start = latest_end - c_j.pause_after - c_j.duration
                        latest_slot_idx = optimizer.minutes_to_slot_floor(latest_start)
                        optimizer.model.Add(optimizer.start_vars[j] <= latest_slot_idx)
                    return

            # Если фиксированное c_j и оконное c_i
            elif c_j.start_time and not c_j.end_time and c_i.start_time and c_i.end_time:
                if can_seq_j_i and info_j_i['reason'] == 'fits_before_fixed':
                    # c_i можно разместить ДО c_j - предпочитаем этот вариант
                    fixed_start = time_to_minutes(c_j.start_time)
                    latest_end = fixed_start - c_j.pause_before
                    latest_start = latest_end - c_i.pause_after - c_i.duration
                    latest_slot_idx = optimizer.minutes_to_slot_floor(latest_start)

                    print(f"  [shared_groups] PRIORITIZING window class {i} BEFORE fixed class {j}")
                    optimizer.model.Add(optimizer.start_vars[i] <= latest_slot_idx)
                    return
                elif can_seq_j_i and info_j_i['reason'] == 'fits_after_fixed':
                    # c_i можно разместить ПОСЛЕ c_j
                    fixed_start = time_to_minutes(c_j.start_time)
                    fixed_end = fixed_start + c_j.duration + c_j.pause_after

                    earliest_start = fixed_end + c_i.pause_before
                    earliest_slot = optimizer.minutes_to_slot_ceil(earliest_start)

                    # Проверяем, хватает ли времени для размещения ПОСЛЕ
                    window_end = time_to_minutes(c_i.end_time)
                    if (window_end - optimizer.slot_to_minutes(earliest_slot)) >= c_i.duration:
                        print(f"  [shared_groups] Applying AFTER-fixed for class {i}")
                        optimizer.model.Add(optimizer.start_vars[i] >= earliest_slot)
                    else:
                        print(f"  [WARNING] Not enough time to schedule {i} after {j}, but forcing BEFORE-fixed")
                        # Принудительно размещаем ДО, даже если первоначально это не было обнаружено
                        latest_end = fixed_start - c_j.pause_before
                        latest_start = latest_end - c_i.pause_after - c_i.duration
                        latest_slot_idx = optimizer.minutes_to_slot_floor(latest_start)
                        optimizer.model.Add(optimizer.start_vars[i] <= latest_slot_idx)
                    return

            # Оба занятия с временными окнами или оба фиксированные:
            # используем уже рассчитанное обратное направление.
            can_seq_rev, info_rev = can_seq_j_i, info_j_i
        else:
            # Для случаев без общих групп достаточно одного вызова (обратный порядок).
            can_seq_rev, info_rev = can_schedule_sequentially(c_j, c_i)

        if can_seq_rev:
            reason = info_rev.get('reason')

            fixed_class = None
            window_class = None
            window_idx = None
            if c_i.start_time and not c_i.end_time and c_j.start_time and c_j.end_time:
                fixed_class = c_i
                window_class = c_j
                window_idx = j
            elif c_j.start_time and not c_j.end_time and c_i.start_time and c_i.end_time:
                fixed_class = c_j
                window_class = c_i
                window_idx = i

            # fits_before_fixed для reversed: window class must be before fixed class
            if reason == 'fits_before_fixed':
                if fixed_class is not None and window_class is not None and window_idx is not None:
                    fixed_start = time_to_minutes(fixed_class.start_time)
                    latest_start_window = (
                        fixed_start
                        - fixed_class.pause_before
                        - window_class.pause_after
                        - window_class.duration
                    )
                    slot_idx = optimizer.minutes_to_slot_floor(latest_start_window)

                    print(f"  [no-shared-groups] Applying BEFORE-fixed (reversed) for WINDOW class {window_idx}")
                    optimizer.model.Add(optimizer.start_vars[window_idx] <= slot_idx)
                    return

            # fits_after_fixed для reversed: window class must be after fixed class
            elif reason == 'fits_after_fixed':
                if fixed_class is not None and window_class is not None and window_idx is not None:
                    fixed_end = (
                        time_to_minutes(fixed_class.start_time)
                        + fixed_class.duration
                        + fixed_class.pause_after
                    )
                    earliest_start_window = fixed_end + window_class.pause_before
                    slot_idx = optimizer.minutes_to_slot_ceil(earliest_start_window)

                    print(f"  [no-shared-groups] Applying AFTER-fixed (reversed) for WINDOW class {window_idx}")
                    optimizer.model.Add(optimizer.start_vars[window_idx] >= slot_idx)
                    return

            elif reason == 'fits_in_common_window_1_then_2':
                print(f"  [shared_groups] fits_in_common_window (j->i) - adding non-overlap constraint")
                add_sequential_constraints(optimizer, i, j, c_i, c_j)
                return

            elif reason == 'fits_in_common_window_2_then_1':
                print(f"  [shared_groups] fits_in_common_window (i->j) - adding non-overlap constraint")
                add_sequential_constraints(optimizer, i, j, c_i, c_j)
                return

            else:  # both_orders_possible или unknown
                print(f"  [shared_groups] both_orders_possible - adding non-overlap constraint")
                add_sequential_constraints(optimizer, i, j, c_i, c_j)
                return
    
    # 0-2) Оба занятия в одной комнате и оба с окнами → тоже можно short-circuit
    if shared_rooms and c_i.start_time and c_i.end_time and c_j.start_time and c_j.end_time:
        if check_two_window_classes(optimizer, i, j, c_i, c_j):
            # Для teacher/group конфликтов non-overlap обязателен всегда,
            # и здесь можно сразу зафиксировать последовательность.
            if teacher_conflict or shared_groups:
                print(f"  [window-window room] Adding sequential constraint for shared room: {i},{j}")
                add_sequential_constraints(optimizer, i, j, c_i, c_j)
                return
            # shared_rooms-only: последовательное размещение возможно,
            # но запрещаем overlap только если выбрана одна и та же комната.
            print(f"  [window-window room] Sequential fit possible; adding conditional room-overlap constraint for classes {i},{j}")
            _add_conditional_room_overlap_constraint(optimizer, i, j, c_i, c_j)
            return

    if shared_rooms and not teacher_conflict and not shared_groups:
        print(f"  [room-conflict] Adding conditional room-overlap constraint between classes {i} and {j}")
    else:
        print(
            f"  [hard-conflict] Sequential scheduling not possible, "
            f"adding hard non-overlap constraint between classes {i} and {j}"
        )
    
    # Создаем переменные для конфликта
    conflict, same_day, time_overlap = create_conflict_variables(optimizer, i, j, c_i, c_j)
    
    # Добавляем ограничения для определения перекрытия времени
    add_time_overlap_constraints(optimizer, i, j, c_i, c_j, time_overlap)
    
    if teacher_conflict or shared_groups:
        _forbid_same_day_overlap(optimizer, conflict, same_day, time_overlap)
    elif shared_rooms:
        _forbid_same_day_overlap_if_same_room(optimizer, i, j, same_day, time_overlap)

def times_overlap(class1, class2):
    """
    Проверяет, пересекаются ли занятия по времени.
    Учитывает фиксированное время и временные окна.
    """
    # Если оба дня фиксированы и различаются — пересечения быть не может.
    # Если хотя бы один день не фиксирован, конфликт по дню возможен.
    if class1.day and class2.day and class1.day != class2.day:
        return False
    
    # Если у занятия нет времени начала, считаем пересекающимся
    if not class1.start_time or not class2.start_time:
        return True
        
    # Обрабатываем случай временных окон (когда есть end_time)
    if class1.start_time and class1.end_time and class2.start_time and class2.end_time:
        # Оба занятия с временными окнами
        # Проверяем, может ли быть конфликт при неподходящем назначении времени
        window1_start = time_to_minutes(class1.start_time)
        window1_end = time_to_minutes(class1.end_time)
        window2_start = time_to_minutes(class2.start_time)
        window2_end = time_to_minutes(class2.end_time)
        
        # Находим общее окно
        common_start = max(window1_start, window2_start)
        common_end = min(window1_end, window2_end)
        
        if common_end <= common_start:
            # Нет общего времени вообще
            return False
            
        # Если общее окно меньше суммы длительностей, возможен конфликт
        total_duration = class1.duration + class2.duration
        if common_end - common_start < total_duration:
            return True
            
        # Здесь важное отличие: даже если общее окно больше суммы длительностей,
        # мы всё равно возвращаем True, если нас интересует возможность конфликта
        # Но в этом случае конфликт может быть разрешен с помощью правильного планирования
        return True
        
    # Случай, когда первое занятие имеет фиксированное время, а второе - временное окно
    elif class1.start_time and not class1.end_time and class2.start_time and class2.end_time:
        fixed_start = time_to_minutes(class1.start_time)
        fixed_end = fixed_start + class1.duration
        window_start = time_to_minutes(class2.start_time)
        window_end = time_to_minutes(class2.end_time)
        
        # Проверяем, может ли быть конфликт
        return (fixed_start < window_end) and (window_start < fixed_end)
        
    # Случай, когда второе занятие имеет фиксированное время, а первое - временное окно
    elif class2.start_time and not class2.end_time and class1.start_time and class1.end_time:
        fixed_start = time_to_minutes(class2.start_time)
        fixed_end = fixed_start + class2.duration
        window_start = time_to_minutes(class1.start_time)
        window_end = time_to_minutes(class1.end_time)
        
        # Проверяем, может ли быть конфликт
        return (fixed_start < window_end) and (window_start < fixed_end)
    
    # Оба занятия имеют фиксированное время
    else:
        start1 = time_to_minutes(class1.start_time)
        end1 = start1 + class1.duration
        start2 = time_to_minutes(class2.start_time)
        end2 = start2 + class2.duration
        return (start1 < end2) and (start2 < end1)

        
