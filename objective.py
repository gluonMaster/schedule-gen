"""
Module for defining the objective function.
"""

from time_utils import pause_to_slots

def add_objective_function(optimizer):
    """Define the objective function to optimize the schedule."""
    num_classes = len(optimizer.classes)
    time_slot_count = len(optimizer.time_slots)
    zero_gap = optimizer.model.NewConstant(0)
    
    # 1. Minimize the number of teacher room changes
    teacher_changes = []
    
    # Group classes by teacher and day
    teacher_day_classes = {}
    for idx, c in enumerate(optimizer.classes):
        if not c.teacher:
            continue
            
        teacher = c.teacher
        if teacher not in teacher_day_classes:
            teacher_day_classes[teacher] = {}
        
        day_var = optimizer.day_vars[idx]
        if isinstance(day_var, int):
            day = day_var
            if day not in teacher_day_classes[teacher]:
                teacher_day_classes[teacher][day] = []
            teacher_day_classes[teacher][day].append(idx)
        else:
            # For classes with variable days, we need to consider all possibilities
            for day in range(len(optimizer.day_indices)):
                day_match = optimizer.model.NewBoolVar(f"day_match_{idx}_{day}")
                optimizer.model.Add(day_var == day).OnlyEnforceIf(day_match)
                optimizer.model.Add(day_var != day).OnlyEnforceIf(day_match.Not())
                
                if day not in teacher_day_classes[teacher]:
                    teacher_day_classes[teacher][day] = []
                
                # Add the class to this day's list (conditional on day_match)
                teacher_day_classes[teacher][day].append((idx, day_match))
    
    # For each teacher and day, count room changes
    for teacher, days in teacher_day_classes.items():
        for day, classes in days.items():
            # Skip if only one class
            if len(classes) <= 1:
                continue
            
            # Sort classes by start time
            if all(isinstance(item, int) for item in classes):
                # All fixed day classes
                sorted_classes = sorted(classes, key=lambda idx:
                                  optimizer.start_vars[idx] if isinstance(optimizer.start_vars[idx], int)
                                  else time_slot_count)  # Put variable starts after fixed
                
                # Count room changes
                for i in range(len(sorted_classes) - 1):
                    curr_idx = sorted_classes[i]
                    next_idx = sorted_classes[i + 1]
                    
                    room_change = optimizer.model.NewBoolVar(f"room_change_{curr_idx}_{next_idx}")
                    if isinstance(optimizer.room_vars[curr_idx], int) and isinstance(optimizer.room_vars[next_idx], int):
                        # Both rooms are fixed - создаем явное сравнение
                        if optimizer.room_vars[curr_idx] != optimizer.room_vars[next_idx]:
                            optimizer.model.Add(room_change == 1)
                        else:
                            optimizer.model.Add(room_change == 0)
                    elif isinstance(optimizer.room_vars[curr_idx], int):
                        optimizer.model.Add(optimizer.room_vars[next_idx] != optimizer.room_vars[curr_idx]).OnlyEnforceIf(room_change)
                        optimizer.model.Add(optimizer.room_vars[next_idx] == optimizer.room_vars[curr_idx]).OnlyEnforceIf(room_change.Not())
                    elif isinstance(optimizer.room_vars[next_idx], int):
                        optimizer.model.Add(optimizer.room_vars[curr_idx] != optimizer.room_vars[next_idx]).OnlyEnforceIf(room_change)
                        optimizer.model.Add(optimizer.room_vars[curr_idx] == optimizer.room_vars[next_idx]).OnlyEnforceIf(room_change.Not())
                    else:
                        optimizer.model.Add(optimizer.room_vars[curr_idx] != optimizer.room_vars[next_idx]).OnlyEnforceIf(room_change)
                        optimizer.model.Add(optimizer.room_vars[curr_idx] == optimizer.room_vars[next_idx]).OnlyEnforceIf(room_change.Not())
                    
                    teacher_changes.append(room_change)
            else:
                # Some classes have variable days
                # This is more complex and depends on the specific problem constraints
                # For now, we'll simplify and just count potential changes
                pass
    
    # 2. Minimize empty time slots ("gaps") for teachers and groups
    gaps = []
    
    # For teachers
    for teacher, days in teacher_day_classes.items():
        for day, classes in days.items():
            # Skip if only one class
            if len(classes) <= 1:
                continue
            
            # Sort classes by start time (simplified for now)
            if all(isinstance(item, int) for item in classes):
                sorted_classes = sorted(classes, key=lambda idx:
                                  optimizer.start_vars[idx] if isinstance(optimizer.start_vars[idx], int)
                                  else time_slot_count)
                
                # Measure gaps between consecutive classes
                for i in range(len(sorted_classes) - 1):
                    curr_idx = sorted_classes[i]
                    next_idx = sorted_classes[i + 1]
                    
                    # Calculate expected gap size
                    if isinstance(optimizer.start_vars[curr_idx], int) and isinstance(optimizer.start_vars[next_idx], int):
                        # Both start times are fixed
                        curr_end = (
                            optimizer.start_vars[curr_idx]
                            + (optimizer.classes[curr_idx].duration // optimizer.time_interval)
                            + pause_to_slots(optimizer.classes[curr_idx].pause_after, optimizer.time_interval)
                        )
                        next_start = optimizer.start_vars[next_idx] - pause_to_slots(optimizer.classes[next_idx].pause_before, optimizer.time_interval)
                        
                        gap_size = next_start - curr_end
                        if gap_size > 0:
                            # We only care about minimizing gaps, not eliminating them
                            gaps.append(optimizer.model.NewConstant(gap_size))
                    else:
                        # For variable start times, model positive part of the gap:
                        # gap = max(0, next_start - curr_end)
                        curr_duration = (
                            (optimizer.classes[curr_idx].duration // optimizer.time_interval)
                            + pause_to_slots(optimizer.classes[curr_idx].pause_after, optimizer.time_interval)
                        )

                        if isinstance(optimizer.start_vars[curr_idx], int):
                            curr_end_val = optimizer.start_vars[curr_idx] + curr_duration
                            curr_end_lb = curr_end_val
                            curr_end_ub = curr_end_val
                            curr_end = optimizer.model.NewIntVar(
                                curr_end_lb, curr_end_ub, f"end_{curr_idx}_{next_idx}"
                            )
                            optimizer.model.Add(curr_end == curr_end_val)
                        else:
                            curr_end_lb = curr_duration
                            curr_end_ub = time_slot_count + curr_duration
                            curr_end = optimizer.model.NewIntVar(
                                curr_end_lb, curr_end_ub, f"end_{curr_idx}_{next_idx}"
                            )
                            optimizer.model.Add(curr_end == optimizer.start_vars[curr_idx] + curr_duration)

                        next_pause = pause_to_slots(optimizer.classes[next_idx].pause_before, optimizer.time_interval)
                        if isinstance(optimizer.start_vars[next_idx], int):
                            next_start_val = optimizer.start_vars[next_idx] - next_pause
                            next_start_lb = next_start_val
                            next_start_ub = next_start_val
                            next_start = optimizer.model.NewIntVar(
                                next_start_lb, next_start_ub, f"effective_start_{curr_idx}_{next_idx}"
                            )
                            optimizer.model.Add(next_start == next_start_val)
                        else:
                            next_start_lb = -time_slot_count
                            next_start_ub = time_slot_count
                            next_start = optimizer.model.NewIntVar(
                                next_start_lb, next_start_ub, f"effective_start_{curr_idx}_{next_idx}"
                            )
                            optimizer.model.Add(next_start == optimizer.start_vars[next_idx] - next_pause)

                        gap_raw_lb = next_start_lb - curr_end_ub
                        gap_raw_ub = next_start_ub - curr_end_lb
                        gap_raw = optimizer.model.NewIntVar(
                            gap_raw_lb, gap_raw_ub, f"gap_raw_{curr_idx}_{next_idx}"
                        )
                        optimizer.model.Add(gap_raw == next_start - curr_end)

                        gap = optimizer.model.NewIntVar(
                            0, max(0, gap_raw_ub), f"gap_{curr_idx}_{next_idx}"
                        )
                        optimizer.model.AddMaxEquality(gap, [gap_raw, zero_gap])
                        gaps.append(gap)
    
    # 3. Define the objective function
    # We'll give more weight to room changes than to gaps
    objective_terms = []
    
    # Add teacher room changes (weight 10)
    for change in teacher_changes:
        objective_terms.append(change * 10)
    
    # Add gaps (weight 1)
    for gap in gaps:
        objective_terms.append(gap)
    
    # Добавляем веса для улучшения планирования с временными окнами
    try:
        from timewindow_adapter import add_objective_weights_for_timewindows
        additional_terms = add_objective_weights_for_timewindows(optimizer)
        objective_terms.extend(additional_terms)
    except ImportError:
        # Если модуль не найден, продолжаем без дополнительных весов
        pass

    # Minimize the sum
    optimizer.model.Minimize(sum(objective_terms))
