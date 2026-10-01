from ortools.sat.python import cp_model
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Set, Any

# Импорт из локальных модулей
from reader import ScheduleReader, ScheduleClass

class ScheduleOptimizer:
    """
    Class that uses OR-Tools CP-SAT solver to create an optimized schedule
    based on the input constraints.
    """
    
    def __init__(self, classes: List[ScheduleClass], time_interval: int = 15):
        """
        Initialize the scheduler with the given classes and time interval.
        
        Args:
            classes: List of ScheduleClass objects to schedule
            time_interval: Time interval in minutes for scheduling (default: 15)
        """
        self.classes = classes
        self.time_interval = time_interval
        
        # Primary lookup by object identity avoids collisions for similar classes.
        self.class_index = {id(c): idx for idx, c in enumerate(classes)}

        print(f"Created class_index with {len(self.class_index)} entries.")
        print(f"Classes list has {len(classes)} elements.")
        
        # Extract all unique resources
        self.teachers = sorted(set(c.teacher for c in classes if c.teacher))
        self.rooms = sorted(set(room for c in classes for room in c.possible_rooms if room))
        self.groups = sorted(set(group for c in classes for group in c.get_groups() if group))
        self.days = sorted(set(c.day for c in classes if c.day))

        # Map days to a dense 0..N-1 domain while preserving Mo->Sa ordering.
        day_order = ["Mo", "Di", "Mi", "Do", "Fr", "Sa"]
        present_days = [day for day in day_order if day in self.days]
        extra_days = sorted(day for day in self.days if day not in day_order)
        self.days = present_days + extra_days

        # If no class has a fixed day, allow assignment across the standard week.
        if not self.days:
            self.days = day_order.copy()

        self.day_indices = {day: idx for idx, day in enumerate(self.days)}
        self.index_to_day = {idx: day for day, idx in self.day_indices.items()}
        
        # Generate time slots
        self.time_slots = self._generate_time_slots()
        self.time_slot_indices = {slot: idx for idx, slot in enumerate(self.time_slots)}
        self.time_slot_minutes = [self._time_to_minutes(slot) for slot in self.time_slots]
        
        # Initialize the model and variables
        self.model = None
        self.assigned_vars = {}
        self.start_vars = {}
        self.room_vars = {}
        self.day_vars = {}
        
        # Results
        self.solution = None
        self.last_status = None
        self.last_status_name = "NOT_SOLVED"
    
    def _generate_time_slots(self) -> List[str]:
        """Generate time slots for the schedule."""
        time_slots = []
        start_time = datetime.strptime("08:00", "%H:%M")
        end_time = datetime.strptime("20:00", "%H:%M")
        
        current = start_time
        while current <= end_time:
            time_slots.append(current.strftime("%H:%M"))
            current += timedelta(minutes=self.time_interval)
        
        return time_slots
    
    def _time_to_minutes(self, time_str: str) -> int:
        """Convert a time string (HH:MM) to minutes since midnight."""
        if not time_str:
            return 0
        
        hours, minutes = map(int, time_str.split(':'))
        return hours * 60 + minutes
    
    def slot_to_minutes(self, slot_idx: int) -> int:
        """Convert a slot index to absolute minutes since midnight."""
        if not self.time_slot_minutes:
            return 0
        bounded_idx = max(0, min(slot_idx, len(self.time_slot_minutes) - 1))
        return self.time_slot_minutes[bounded_idx]

    def minutes_to_slot_ceil(self, minutes: int) -> int:
        """Return first slot index whose time is >= provided minutes."""
        for i, slot_minutes in enumerate(self.time_slot_minutes):
            if slot_minutes >= minutes:
                return i
        return len(self.time_slots) - 1

    def minutes_to_slot_floor(self, minutes: int) -> int:
        """Return last slot index whose time is <= provided minutes."""
        for i in range(len(self.time_slot_minutes) - 1, -1, -1):
            if self.time_slot_minutes[i] <= minutes:
                return i
        return 0

    def time_to_slot_ceil(self, time_str: str) -> int:
        """Return first slot index whose time is >= provided time string."""
        return self.minutes_to_slot_ceil(self._time_to_minutes(time_str))

    def time_to_slot_floor(self, time_str: str) -> int:
        """Return last slot index whose time is <= provided time string."""
        return self.minutes_to_slot_floor(self._time_to_minutes(time_str))

    def minutes_to_slot(self, minutes: int, rounding: str = "ceil") -> int:
        """Compatibility helper for minutes->slot conversion with explicit rounding."""
        if rounding == "floor":
            return self.minutes_to_slot_floor(minutes)
        return self.minutes_to_slot_ceil(minutes)

    def _get_time_slot_index(self, time_str: str) -> int:
        """Backward-compatible alias for ceil conversion (first slot >= time)."""
        return self.time_to_slot_ceil(time_str)
    
    def _calculate_overlapping_intervals(self, start1: int, duration1: int, start2: int, duration2: int) -> int:
        """Calculate the overlap between two intervals."""
        end1 = start1 + duration1
        end2 = start2 + duration2
        return max(0, min(end1, end2) - max(start1, start2))
    
    def _find_class_index(self, c: ScheduleClass) -> int:
        """Find class index using identity first, then a strict attribute fallback."""
        idx = self.class_index.get(id(c))
        if idx is not None:
            return idx

        # Fallback for copied/recreated objects.
        for idx, cls in enumerate(self.classes):
            if (
                cls.subject == c.subject
                and cls.teacher == c.teacher
                and cls.day == c.day
                and cls.start_time == c.start_time
                and getattr(cls, "section_index", None) == getattr(c, "section_index", None)
                and getattr(cls, "column", None) == getattr(c, "column", None)
            ):
                return idx
        
        # If we can't find the class, print details and raise an error
        print(f"ERROR: Could not find linked class in the classes list:")
        print(f"  Subject: {c.subject}")
        print(f"  Teacher: {c.teacher}")
        print(f"  Day: {c.day}")
        print(f"  Start Time: {c.start_time}")
        print(f"Available classes:")
        for idx, cls in enumerate(self.classes):
            print(f"  {idx}: {cls.subject} - {cls.teacher} - {cls.day} - {cls.start_time}")
        
        raise ValueError(f"Could not find linked class {c} in the classes list")
    
    def build_model(self):
        """Build the constraint programming model."""
        from model_variables import create_variables
        from constraints import add_linked_constraints, add_resource_conflict_constraints
        from objective import add_objective_function
        
        self.model = cp_model.CpModel()
        
        # Create variables for classes
        create_variables(self)
        
        # Add constraints for linked classes
        add_linked_constraints(self)
        
        # Add constraints to prevent resource conflicts
        add_resource_conflict_constraints(self)
   
        # Add objective function
        add_objective_function(self)
    
    def solve(self, time_limit_seconds=60):
        """
        Solve the scheduling problem.
        
        Args:
            time_limit_seconds: Maximum solving time in seconds
            
        Returns:
            True if a solution was found, False otherwise
        """
        if self.model is None:
            self.build_model()

        # Применение улучшений для временных окон
        try:
            from timewindow_adapter import apply_timewindow_improvements
            apply_timewindow_improvements(self)
            self.timewindow_already_processed = True
        except ImportError:
            print("Warning: timewindow_adapter module not found, skipping timewindow improvements")
        
        # Create the solver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds
        
        # Добавляем логирование
        print("\nAttempting to solve model...")
        
        # Solve the model
        status = solver.Solve(self.model)
        self.last_status = status
        self.last_status_name = solver.StatusName(status)
        
        # Инициализация solution перед любым использованием
        solution = []
        
        # Детальное логирование статуса
        # Technical status log; user-facing summary is handled in main_sch.py.
        print(f"\nSolver status: {status} ({self.last_status_name})")
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            # Store the solution
            for idx, c in enumerate(self.classes):
                # Get assigned values
                day = self.day_vars[idx]
                if not isinstance(day, int):
                    day = solver.Value(day)
                    
                start_slot = self.start_vars[idx]
                if not isinstance(start_slot, int):
                    start_slot = solver.Value(start_slot)
                    
                room_idx = self.room_vars[idx]
                if not isinstance(room_idx, int):
                    room_idx = solver.Value(room_idx)
                
                day_name = self.index_to_day.get(day, f"UNKNOWN_DAY_{day}")
                room_name = self.rooms[room_idx]
                start_time = self.time_slots[start_slot]
                
                # Calculate end time
                time_obj = datetime.strptime(start_time, "%H:%M")
                time_obj += timedelta(minutes=c.duration)
                end_time = time_obj.strftime("%H:%M")

                raw_lesson_type = str(getattr(c, "lesson_type", "") or "").strip().lower()
                if raw_lesson_type in {"group", "individual", "nachhilfe", "trial"}:
                    lesson_type = raw_lesson_type
                else:
                    lesson_type = ""

                raw_trial_dates = getattr(c, "trial_dates", [])
                if lesson_type == "trial" and isinstance(raw_trial_dates, list):
                    trial_dates_json = json.dumps(
                        [str(item) for item in raw_trial_dates if item is not None],
                        ensure_ascii=False,
                    )
                else:
                    trial_dates_json = ""
                
                # Store the assignment
                solution.append({
                    "subject": c.subject,
                    "group": c.group,
                    "teacher": c.teacher,
                    "room": room_name,
                    "building": c.building,
                    "day": day_name,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": c.duration,
                    "pause_before": c.pause_before,
                    "pause_after": c.pause_after,
                    "lesson_type": lesson_type,
                    "trial_dates_json": trial_dates_json,
                })
            
        # В случае INFEASIBLE, вызвать анализ конфликтов
        if status == cp_model.INFEASIBLE:
            linked_chains = getattr(self, "linked_chains", [])
            fixed_start_classes = sum(1 for c in self.classes if c.start_time and not c.end_time)
            window_classes = sum(1 for c in self.classes if c.start_time and c.end_time)
            any_time_classes = sum(1 for c in self.classes if not c.start_time)
            fixed_room_classes = sum(
                1 for c in self.classes if len(getattr(c, "possible_rooms", []) or []) == 1
            )

            print("\nInfeasibility diagnostics summary:")
            print("Note: SufficientAssumptionsForInfeasibility() requires model.AddAssumptions().")
            print("This model uses model.Add() constraints; detailed conflict extraction is not available.")
            print(f"  - Total classes: {len(self.classes)}")
            print(f"  - Linked chains: {linked_chains}")
            print(f"  - Fixed start classes: {fixed_start_classes}")
            print(f"  - Window classes: {window_classes}")
            print(f"  - Any-time classes: {any_time_classes}")
            print(f"  - Fixed-room classes: {fixed_room_classes}")
            
        # Сохраняем solution независимо от результата
        self.solution = solution
        
        # Возвращаем True только если найдено оптимальное или допустимое решение
        return status == cp_model.OPTIMAL or status == cp_model.FEASIBLE
