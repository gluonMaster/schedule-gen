"""
Модуль для добавления ограничений ресурсов (преподаватели, аудитории, группы).
"""

from conflict_detector import check_potential_conflicts
from time_conflict_constraints import _add_time_conflict_constraints
from time_utils import time_to_minutes

def _in_same_linked_chain(optimizer, i: int, j: int) -> bool:
    """Return True when both class indices belong to the same linked chain."""
    for chain in getattr(optimizer, "linked_chains", []):
        if i in chain and j in chain:
            return True
    return False

def times_overlap(c1, c2):
    """Проверяет пересечение по времени двух занятий."""
    if not c1.start_time or not c2.start_time:
        # Одно из занятий не имеет фиксированного времени — считаем пересекающимся
        return True
    start1 = time_to_minutes(c1.start_time)
    end1 = start1 + c1.duration
    start2 = time_to_minutes(c2.start_time)
    end2 = start2 + c2.duration
    return (start1 < end2) and (start2 < end1)

def add_resource_conflict_constraints(optimizer):
    """Add constraints to prevent conflicts in resources (teachers, rooms, groups)."""
    # Напечатать подробную информацию о занятиях для отладки
    print("\nDetailed class information:")
    for idx, c in enumerate(optimizer.classes):
        time_info = f"{c.start_time}"
        if c.end_time:
            time_info += f"-{c.end_time}"
        
        room_info = ", ".join(c.possible_rooms)
        print(f"Class {idx}: {c.subject} - {c.group} - {c.teacher} - {c.day} {time_info}")
        print(f"  Duration: {c.duration} min, Pause before: {c.pause_before} min, Pause after: {c.pause_after} min")
        print(f"  Room(s): {room_info}")
        
    # Предварительная проверка конфликтов
    check_potential_conflicts(optimizer)

    # For each pair of classes
    num_classes = len(optimizer.classes)
    for i in range(num_classes):
        c_i = optimizer.classes[i]
        
        for j in range(i + 1, num_classes):
            c_j = optimizer.classes[j]

            # Пропускаем сравнение только если оба дня фиксированы и различаются.
            day_i = optimizer.day_vars[i]
            day_j = optimizer.day_vars[j]
            if isinstance(day_i, int) and isinstance(day_j, int) and day_i != day_j:
                continue

            # Skip if classes are linked (already handled)
            if hasattr(c_i, 'linked_classes') and c_j in c_i.linked_classes:
                continue
            if hasattr(c_j, 'linked_classes') and c_i in c_j.linked_classes:
                continue
            
            # Skip all pairs within the same linked chain (already handled).
            if _in_same_linked_chain(optimizer, i, j):
                continue

            # Пропускаем fixed/fixed пары, которые точно не пересекаются по времени.
            # Для оконных и переменных стартов такой pre-filter небезопасен.
            if getattr(c_i, 'fixed_start_time', False) and getattr(c_j, 'fixed_start_time', False):
                if not times_overlap(c_i, c_j):
                    continue
            
            # Check if both classes share resources (teacher, room, group)
            resource_conflict = False
            conflict_description = []
            
            # Проверка конфликта преподавателя
            if c_i.teacher == c_j.teacher and c_i.teacher:
                # Проверяем, есть ли общие группы
                shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
                if shared_groups:
                    # Если есть общие группы, всегда считаем конфликтом
                    resource_conflict = True
                    conflict_description.append(f"teacher '{c_i.teacher}' and shared groups {shared_groups}")
                else:
                    # Разные группы: конфликт по учителю все равно должен
                    # приводить к non-overlap (порядок выберет solver).
                    resource_conflict = True
                    conflict_description.append(f"teacher '{c_i.teacher}' (different groups, same day)")
            
            # Проверка конфликта аудитории
            shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
            if shared_rooms:
                resource_conflict = True
                conflict_description.append(f"rooms {shared_rooms}")
            
            # Проверка конфликта групп
            shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
            if shared_groups:
                resource_conflict = True
                conflict_description.append(f"groups {shared_groups}")
            
            # Если обнаружен потенциальный конфликт, добавляем ограничения по времени
            if resource_conflict:
                conflict_str = ", ".join(conflict_description)
                print(f"Detected potential conflict between '{c_i.subject}' and '{c_j.subject}' (shared {conflict_str})")
                
                _add_time_conflict_constraints(optimizer, i, j, c_i, c_j)
