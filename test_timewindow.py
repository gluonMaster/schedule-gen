"""
Тестовый скрипт для проверки улучшений по обработке временных окон.

Этот скрипт загружает данные из Excel-файла, анализирует занятия с временными окнами
и проверяет возможность их последовательного размещения.
"""

import sys
import argparse
from reader import ScheduleReader, ScheduleClass
from sequential_scheduling import analyze_tanz_classes, can_schedule_sequentially
from time_utils import time_to_minutes, minutes_to_time

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Test timewindow scheduling improvements')
    
    parser.add_argument('input_file', help='Path to the Excel file with schedule planning data')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose output')
    
    return parser.parse_args()

def analyze_timewindows(classes):
    """Analyze classes with time windows."""
    print("\n=== Classes with Time Windows ===")
    
    window_classes = []
    fixed_classes = []
    
    for idx, c in enumerate(classes):
        if c.start_time and c.end_time:
            window_classes.append((idx, c))
        elif c.start_time:
            fixed_classes.append((idx, c))
    
    print(f"Total classes: {len(classes)}")
    print(f"Classes with time windows: {len(window_classes)}")
    print(f"Classes with fixed times: {len(fixed_classes)}")
    
    if window_classes:
        print("\nDetailed time window classes:")
        for idx, c in window_classes:
            window_start = time_to_minutes(c.start_time)
            window_end = time_to_minutes(c.end_time)
            window_duration = window_end - window_start
            required_time = c.duration + c.pause_before + c.pause_after
            
            print(f"Class {idx}: {c.subject} - {c.group} - {c.teacher}")
            print(f"  Time window: {c.start_time}-{c.end_time} ({window_duration} min)")
            print(f"  Duration: {c.duration} min (+ pause before: {c.pause_before} min, pause after: {c.pause_after} min)")
            print(f"  Total required time: {required_time} min")
            print(f"  Window flexibility: {window_duration - required_time} min")
            print(f"  Room(s): {', '.join(c.possible_rooms)}")
            
    return window_classes, fixed_classes

def find_potential_sequential_pairs(classes, window_classes, fixed_classes):
    """Find potential sequential scheduling pairs."""
    print("\n=== Potential Sequential Scheduling Pairs ===")
    
    sequential_pairs = []
    
    # Проверка пар "фиксированное + окно"
    for idx_i, c_i in fixed_classes:
        for idx_j, c_j in window_classes:
            # Проверяем общие ресурсы
            same_teacher = c_i.teacher == c_j.teacher and c_i.teacher
            shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
            shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
            
            # Если есть общие ресурсы, проверяем возможность последовательного размещения
            if (same_teacher or shared_rooms) and not shared_groups:
                can_schedule, info = can_schedule_sequentially(c_i, c_j)
                
                if can_schedule:
                    sequential_pairs.append({
                        'class1_idx': idx_i,
                        'class2_idx': idx_j,
                        'class1': c_i,
                        'class2': c_j,
                        'info': info,
                        'same_teacher': same_teacher,
                        'shared_rooms': shared_rooms
                    })
    
    # Проверка пар "окно + окно"
    for i, (idx_i, c_i) in enumerate(window_classes):
        for j, (idx_j, c_j) in enumerate(window_classes[i+1:], i+1):
            # Проверяем общие ресурсы
            same_teacher = c_i.teacher == c_j.teacher and c_i.teacher
            shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
            shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
            
            # Если есть общие ресурсы, проверяем возможность последовательного размещения
            if (same_teacher or shared_rooms) and not shared_groups:
                can_schedule, info = can_schedule_sequentially(c_i, c_j)
                
                if can_schedule:
                    sequential_pairs.append({
                        'class1_idx': idx_i,
                        'class2_idx': idx_j,
                        'class1': c_i,
                        'class2': c_j,
                        'info': info,
                        'same_teacher': same_teacher,
                        'shared_rooms': shared_rooms
                    })
    
    print(f"Found {len(sequential_pairs)} potential sequential scheduling pairs")
    
    if sequential_pairs:
        print("\nDetailed sequential pairs:")
        for i, pair in enumerate(sequential_pairs):
            c1 = pair['class1']
            c2 = pair['class2']
            idx1 = pair['class1_idx']
            idx2 = pair['class2_idx']
            info = pair['info']
            
            print(f"\nPair {i+1}:")
            print(f"  Class {idx1}: {c1.subject} - {c1.group} - {c1.teacher}")
            print(f"  Class {idx2}: {c2.subject} - {c2.group} - {c2.teacher}")
            
            if pair['same_teacher']:
                print(f"  Same teacher: {c1.teacher}")
            
            if pair['shared_rooms']:
                print(f"  Shared rooms: {', '.join(pair['shared_rooms'])}")
            
            print(f"  Scheduling reason: {info['reason']}")
            
            if info['reason'] == 'fits_after_fixed':
                print(f"  Sequential after fixed class")
                print(f"  Required time: {info['required_time']} min")
                print(f"  Available time: {info['available_time']} min")
            elif info['reason'] == 'fits_in_common_window':
                print(f"  Common window: {info['common_window']}")
                print(f"  Required time: {info['required_time']} min")
                print(f"  Available time: {info['available_time']} min")
    
    return sequential_pairs

def analyze_tanz_classes_detailed(classes):
    """Special analysis for Tanz classes."""
    print("\n=== Special Analysis for Tanz Classes ===")
    
    tanz_indices = []
    for idx, c in enumerate(classes):
        if c.subject == "Tanz" and c.teacher == "Melnikov Olga":
            tanz_indices.append(idx)
    
    if not tanz_indices:
        print("No Tanz classes with Melnikov Olga found.")
        return
    
    print(f"Found {len(tanz_indices)} Tanz classes with Melnikov Olga:")
    
    for idx in tanz_indices:
        c = classes[idx]
        print(f"\nClass {idx}: {c.subject} - {c.group} - {c.teacher}")
        print(f"  Day: {c.day}")
        if c.start_time and c.end_time:
            window_start = time_to_minutes(c.start_time)
            window_end = time_to_minutes(c.end_time)
            window_duration = window_end - window_start
            print(f"  Time window: {c.start_time}-{c.end_time} ({window_duration} min)")
        elif c.start_time:
            print(f"  Fixed time: {c.start_time}")
        else:
            print("  No time constraints")
        print(f"  Duration: {c.duration} min (+ pause before: {c.pause_before} min, pause after: {c.pause_after} min)")
        print(f"  Room(s): {', '.join(c.possible_rooms)}")
    
    # Проверяем возможность последовательного размещения
    for i, idx_i in enumerate(tanz_indices):
        c_i = classes[idx_i]
        
        for j, idx_j in enumerate(tanz_indices[i+1:], i+1):
            c_j = classes[idx_j]
            
            print(f"\nChecking sequential scheduling for Tanz classes {idx_i} and {idx_j}:")
            can_schedule, info = can_schedule_sequentially(c_i, c_j)
            
            if can_schedule:
                print(f"  SUCCESS: Classes can be scheduled sequentially")
                print(f"  Reason: {info['reason']}")
                
                if info['reason'] == 'fits_after_fixed':
                    print(f"  Sequential after fixed class")
                    print(f"  Required time: {info['required_time']} min")
                    print(f"  Available time: {info['available_time']} min")
                elif info['reason'] == 'fits_in_common_window':
                    print(f"  Common window: {info['common_window']}")
                    print(f"  Required time: {info['required_time']} min")
                    print(f"  Available time: {info['available_time']} min")
            else:
                print(f"  FAILED: Classes cannot be scheduled sequentially")
                print(f"  Reason: {info['reason']}")

def main():
    """Main function."""
    args = parse_arguments()
    
    try:
        print(f"Reading schedule data from '{args.input_file}'...")
        reader = ScheduleReader(args.input_file)
        classes = reader.read_excel()
        
        print(f"\nLoaded {len(classes)} classes.")
        
        # Analyze time windows
        window_classes, fixed_classes = analyze_timewindows(classes)
        
        # Find potential sequential pairs
        sequential_pairs = find_potential_sequential_pairs(classes, window_classes, fixed_classes)
        
        # Special analysis for Tanz classes
        analyze_tanz_classes_detailed(classes)
        
        # Create a dummy optimizer for testing with analyze_tanz_classes
        class DummyOptimizer:
            def __init__(self, classes):
                self.classes = classes
                self.time_slots = []
                
        dummy_optimizer = DummyOptimizer(classes)
        tanz_analysis = analyze_tanz_classes(dummy_optimizer)
        
        print("\n=== Tanz Analysis Result ===")
        print(f"Number of Tanz classes: {tanz_analysis['num_classes']}")
        print(f"Sequential scheduling possible: {tanz_analysis['sequential_possible']}")
        
        return 0
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
