"""
Модуль для обнаружения потенциальных конфликтов в расписании.
"""

from time_utils import time_to_minutes, minutes_to_time

def check_potential_conflicts(optimizer):
    """Check for obvious conflicts before building the model."""
    print("\nChecking for potential scheduling conflicts...")
    
    # Для каждого преподавателя проверяем конфликты в одно и то же время
    teachers_classes = {}
    for idx, c in enumerate(optimizer.classes):
        if c.teacher:
            if c.teacher not in teachers_classes:
                teachers_classes[c.teacher] = []
            teachers_classes[c.teacher].append((idx, c))
    
    # Проверка конфликтов у преподавателей
    for teacher, classes in teachers_classes.items():
        # Группируем занятия по дням
        day_classes = {}
        for idx, c in classes:
            if c.day:
                if c.day not in day_classes:
                    day_classes[c.day] = []
                day_classes[c.day].append((idx, c))
        
        # Проверяем конфликты в каждый день
        for day, day_classes_list in day_classes.items():
            if len(day_classes_list) > 1:  # Если больше одного занятия в день
                # Проверяем пересечения по времени
                for i, (idx_i, c_i) in enumerate(day_classes_list):
                    # Для занятий с фиксированным временем начала
                    if c_i.start_time and not c_i.end_time:
                        start_i = time_to_minutes(c_i.start_time)
                        end_i = start_i + c_i.duration + c_i.pause_after
                        
                        for j, (idx_j, c_j) in enumerate(day_classes_list):
                            if i != j:  # Не сравниваем занятие с самим собой
                                # Если второе занятие тоже с фиксированным временем
                                if c_j.start_time and not c_j.end_time:
                                    start_j = time_to_minutes(c_j.start_time)
                                    end_j = start_j + c_j.duration + c_j.pause_after
                                    
                                    # Проверяем пересечение
                                    if (start_i < end_j and start_j < end_i):
                                        # Проверяем, не разные ли группы у этих занятий
                                        shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
                                        
                                        if shared_groups:
                                            print(f"\nCONFLICT DETECTED: Teacher {teacher} has overlapping classes with shared groups:")
                                            print(f"  Class 1: {c_i.subject} for groups {c_i.get_groups()} at {c_i.start_time} ({c_i.duration} min)")
                                            print(f"  Class 2: {c_j.subject} for groups {c_j.get_groups()} at {c_j.start_time} ({c_j.duration} min)")
                                            print(f"  Time ranges: {minutes_to_time(start_i)}-{minutes_to_time(end_i)} and {minutes_to_time(start_j)}-{minutes_to_time(end_j)}")
                                            print(f"  These classes cannot be scheduled together with current constraints.")
                                        else:
                                            # Если группы разные, проверяем аудитории
                                            shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
                                            
                                            if shared_rooms and len(c_i.possible_rooms) == 1 and len(c_j.possible_rooms) == 1:
                                                print(f"\nCONFLICT DETECTED: Teacher {teacher} has overlapping classes in the same fixed room:")
                                                print(f"  Class 1: {c_i.subject} for groups {c_i.get_groups()} at {c_i.start_time} ({c_i.duration} min)")
                                                print(f"  Class 2: {c_j.subject} for groups {c_j.get_groups()} at {c_j.start_time} ({c_j.duration} min)")
                                                print(f"  Both classes are fixed to room(s): {shared_rooms}")
                                            else:
                                                print(f"\nNOTE: Teacher {teacher} has overlapping classes but with different groups and different rooms possible:")
                                                print(f"  Class 1: {c_i.subject} for groups {c_i.get_groups()} at {c_i.start_time} ({c_i.duration} min)")
                                                print(f"  Class 2: {c_j.subject} for groups {c_j.get_groups()} at {c_j.start_time} ({c_j.duration} min)")
                                                print(f"  This may be intentional (teacher teaching multiple groups in different rooms).")
                                
                                # Если второе занятие с временным окном
                                elif c_j.start_time and c_j.end_time:
                                    window_start = time_to_minutes(c_j.start_time)
                                    window_end = time_to_minutes(c_j.end_time)
                                    
                                    # Проверяем, можно ли разместить второе занятие после первого
                                    earliest_possible_start = end_i + c_j.pause_before
                                    latest_possible_end = window_end
                                    
                                    # Если есть общие группы, всегда считаем конфликтом
                                    shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
                                    
                                    if shared_groups:
                                        print(f"\nWARNING: Teacher {teacher} has fixed class and window class with shared groups:")
                                        print(f"  Fixed class: {c_i.subject} for groups {c_i.get_groups()} at {c_i.start_time} ({c_i.duration} min)")
                                        print(f"  Window class: {c_j.subject} for groups {c_j.get_groups()} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                                        print(f"  These classes must not overlap due to shared groups: {shared_groups}")
                                    else:
                                        # Если группы разные, проверяем возможность последовательного размещения
                                        if earliest_possible_start + c_j.duration > latest_possible_end:
                                            shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
                                            
                                            if shared_rooms and len(c_i.possible_rooms) == 1 and len(c_j.possible_rooms) == 1:
                                                print(f"\nPOTENTIAL CONFLICT: Teacher {teacher} may not have enough time for both classes in the same fixed room:")
                                                print(f"  Fixed class: {c_i.subject} at {c_i.start_time} ({c_i.duration} min)")
                                                print(f"  Window class: {c_j.subject} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                                                print(f"  Earliest possible start for window class: {minutes_to_time(earliest_possible_start)}")
                                                print(f"  Latest possible end for window class: {minutes_to_time(latest_possible_end)}")
                                                print(f"  Required time: {c_j.duration} min; Available time: {latest_possible_end - earliest_possible_start} min")
                                                
                                                if latest_possible_end - earliest_possible_start < c_j.duration:
                                                    print(f"  WARNING: There is not enough time to schedule both classes!")
                                                else:
                                                    print(f"  There should be enough time to schedule both classes.")
                                            else:
                                                print(f"\nINFO: Teacher {teacher} has fixed class and window class with different groups and room options:")
                                                print(f"  Fixed class: {c_i.subject} at {c_i.start_time} ({c_i.duration} min)")
                                                print(f"  Window class: {c_j.subject} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                                                print(f"  These can be scheduled in parallel with different rooms.")
    
    # Проверка конфликтов аудиторий
    print("\nChecking for room conflicts...")
    room_classes = {}
    for idx, c in enumerate(optimizer.classes):
        for room in c.possible_rooms:
            if room not in room_classes:
                room_classes[room] = []
            room_classes[room].append((idx, c))

    # Проверка конфликтов для каждой аудитории
    for room, classes in room_classes.items():
        # Группировка занятий по дням
        day_classes = {}
        for idx, c in classes:
            if c.day:
                if c.day not in day_classes:
                    day_classes[c.day] = []
                day_classes[c.day].append((idx, c))
        
        # Проверяем конфликты в каждый день
        for day, day_classes_list in day_classes.items():
            if len(day_classes_list) > 1:  # Если больше одного занятия в день в этой аудитории
                # Сортируем по фиксированному времени начала
                fixed_classes = [(idx, c) for idx, c in day_classes_list if c.start_time and not c.end_time]
                window_classes = [(idx, c) for idx, c in day_classes_list if c.start_time and c.end_time]
                
                # Проверяем конфликты между фиксированными занятиями
                for i, (idx_i, c_i) in enumerate(fixed_classes):
                    start_i = time_to_minutes(c_i.start_time)
                    end_i = start_i + c_i.duration + c_i.pause_after
                    
                    for j, (idx_j, c_j) in enumerate(fixed_classes[i+1:], i+1):
                        start_j = time_to_minutes(c_j.start_time)
                        end_j = start_j + c_j.duration + c_j.pause_after
                        
                        # Проверяем пересечение
                        if (start_i < end_j and start_j < end_i):
                            print(f"\nCONFLICT DETECTED: Room {room} has overlapping fixed classes:")
                            print(f"  Class 1: {c_i.subject} at {c_i.start_time} ({c_i.duration} min)")
                            print(f"  Class 2: {c_j.subject} at {c_j.start_time} ({c_j.duration} min)")
                            print(f"  Time ranges: {minutes_to_time(start_i)}-{minutes_to_time(end_i)} and {minutes_to_time(start_j)}-{minutes_to_time(end_j)}")
                            print(f"  These classes cannot be scheduled together in the same room.")
                
                # Проверяем совместимость фиксированных занятий с занятиями с временным окном
                for idx_i, c_i in fixed_classes:
                    start_i = time_to_minutes(c_i.start_time)
                    end_i = start_i + c_i.duration + c_i.pause_after
                    
                    for idx_j, c_j in window_classes:
                        window_start = time_to_minutes(c_j.start_time)
                        window_end = time_to_minutes(c_j.end_time)
                        
                        # Сначала — можно ли вместить окно ДО фиксированного занятия?
                        if start_i >= window_start + c_j.duration + c_j.pause_after:
                            print(f"\nSEQUENTIAL SCHEDULING: Room {room} can fit window class BEFORE fixed class:")
                            print(f"  Window class: {c_j.subject} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                            print(f"  Fixed class: {c_i.subject} at {c_i.start_time}-{minutes_to_time(end_i)} ({c_i.duration} min)")
                            print(f"  Window must start at the beginning of its window: {c_j.start_time}")

                        # Если «до» не подошло, проверяем «после»
                        elif window_end - end_i >= c_j.duration + c_j.pause_before:
                            print(f"\nSEQUENTIAL SCHEDULING: Room {room} can fit window class AFTER fixed class:")
                            print(f"  Fixed class: {c_i.subject} at {c_i.start_time}-{minutes_to_time(end_i)} ({c_i.duration} min)")
                            print(f"  Window class: {c_j.subject} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                            print(f"  Available time after fixed: {window_end - end_i} min")
                            print(f"  Required for window: {c_j.duration + c_j.pause_before} min")

                        else:
                            # Ни «до», ни «после» не влезает
                            print(f"\nPOTENTIAL CONFLICT: Room {room} - cannot fit window class around fixed class")
                            print(f"  Fixed: {c_i.subject} at {c_i.start_time}-{minutes_to_time(end_i)}")
                            print(f"  Window: {c_j.subject} {c_j.start_time}-{c_j.end_time}")
                
                # Проверяем совместимость занятий с временным окном между собой
                for i, (idx_i, c_i) in enumerate(window_classes):
                    window_i_start = time_to_minutes(c_i.start_time)
                    window_i_end = time_to_minutes(c_i.end_time)
                    
                    for j, (idx_j, c_j) in enumerate(window_classes[i+1:], i+1):
                        window_j_start = time_to_minutes(c_j.start_time)
                        window_j_end = time_to_minutes(c_j.end_time)
                        
                        # Находим общее временное окно
                        common_start = max(window_i_start, window_j_start)
                        common_end = min(window_i_end, window_j_end)
                        common_duration = common_end - common_start
                        
                        # Суммарное время, требуемое для обоих занятий
                        total_duration = c_i.duration + c_i.pause_after + c_j.pause_before + c_j.duration
                        
                        if common_duration >= total_duration:
                            print(f"\nSEQUENTIAL SCHEDULING: Room {room} can fit both window classes sequentially:")
                            print(f"  Class 1: {c_i.subject} with window {c_i.start_time}-{c_i.end_time} ({c_i.duration} min)")
                            print(f"  Class 2: {c_j.subject} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                            print(f"  Common window: {minutes_to_time(common_start)}-{minutes_to_time(common_end)} ({common_duration} min)")
                            print(f"  Required time: {total_duration} min")
                        else:
                            print(f"\nPOTENTIAL CONFLICT: Room {room} - insufficient common window for sequential scheduling:")
                            print(f"  Class 1: {c_i.subject} with window {c_i.start_time}-{c_i.end_time} ({c_i.duration} min)")
                            print(f"  Class 2: {c_j.subject} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                            print(f"  Common window: {minutes_to_time(common_start)}-{minutes_to_time(common_end)} ({common_duration} min)")
                            print(f"  Required time: {total_duration} min")
                            print(f"  WARNING: Not enough time in common window to schedule both classes!")
    
    print("\nConflict check completed.")
    