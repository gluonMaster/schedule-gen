"""
Module for output utilities.
"""

import pandas as pd
import re

_INVALID_EXCEL_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
_MAX_EXCEL_SHEET_NAME_LEN = 31


def make_safe_sheet_name(prefix, value, used_names=None):
    """
    Build an Excel-compatible sheet name.

    Excel sheet names cannot contain []:*?/\\ and must be 31 characters or less.
    openpyxl can auto-deduplicate some names, but doing it explicitly keeps
    exports deterministic.
    """
    used_names = used_names if used_names is not None else set()
    raw_value = str(value or "").strip()
    safe_value = _INVALID_EXCEL_SHEET_CHARS.sub("_", raw_value).strip("' ")
    if not safe_value:
        safe_value = "empty"

    base_name = (
        f"{prefix}_{safe_value}" if prefix else safe_value
    )[:_MAX_EXCEL_SHEET_NAME_LEN]
    candidate = base_name
    suffix = 2
    used_lower = {name.lower() for name in used_names}

    while candidate.lower() in used_lower:
        suffix_text = f"_{suffix}"
        candidate = base_name[: _MAX_EXCEL_SHEET_NAME_LEN - len(suffix_text)] + suffix_text
        suffix += 1

    used_names.add(candidate)
    return candidate

def get_schedule_dataframe(optimizer):
    """
    Get the schedule as a pandas DataFrame.
    
    Returns:
        DataFrame with the schedule or None if no solution exists
    """
    if not optimizer.solution:
        return None
        
    return pd.DataFrame(optimizer.solution)

def get_teacher_schedule(optimizer, teacher):
    """
    Get the schedule for a specific teacher.
    
    Args:
        teacher: Name of the teacher
        
    Returns:
        DataFrame with the teacher's schedule or None if no solution exists
    """
    if not optimizer.solution:
        return None
        
    df = pd.DataFrame(optimizer.solution)
    return df[df["teacher"] == teacher].sort_values(by=["day", "start_time"])

def get_group_schedule(optimizer, group):
    """
    Get the schedule for a specific group.
    
    Args:
        group: Name of the group
        
    Returns:
        DataFrame with the group's schedule or None if no solution exists
    """
    if not optimizer.solution:
        return None
        
    df = pd.DataFrame(optimizer.solution)
    # Filter for classes that have this group
    return df[df["group"].str.contains(group, na=False, regex=False)].sort_values(by=["day", "start_time"])

def get_room_schedule(optimizer, room):
    """
    Get the schedule for a specific room.
    
    Args:
        room: Name of the room
        
    Returns:
        DataFrame with the room's schedule or None if no solution exists
    """
    if not optimizer.solution:
        return None
        
    df = pd.DataFrame(optimizer.solution)
    return df[df["room"] == room].sort_values(by=["day", "start_time"])

def export_to_excel(optimizer, filename="schedule.xlsx"):
    """
    Export the schedule to an Excel file.
    
    Args:
        filename: Path to the output Excel file
        
    Returns:
        True if export was successful, False otherwise
    """
    if not optimizer.solution:
        return False
    
    # Используем контекстный менеджер для автоматического закрытия файла
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        used_sheet_names = set()

        # Main schedule
        main_df = pd.DataFrame(optimizer.solution)
        main_sheet_name = make_safe_sheet_name("", "Schedule", used_sheet_names)
        main_df.to_excel(writer, sheet_name=main_sheet_name, index=False)
        
        # Teacher schedules
        for teacher in optimizer.teachers:
            teacher_df = get_teacher_schedule(optimizer, teacher)
            if teacher_df is not None and not teacher_df.empty:
                sheet_name = make_safe_sheet_name("T", teacher, used_sheet_names)
                teacher_df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        # Group schedules
        for group in optimizer.groups:
            group_df = get_group_schedule(optimizer, group)
            if group_df is not None and not group_df.empty:
                sheet_name = make_safe_sheet_name("G", group, used_sheet_names)
                group_df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        # Room schedules
        for room in optimizer.rooms:
            room_df = get_room_schedule(optimizer, room)
            if room_df is not None and not room_df.empty:
                sheet_name = make_safe_sheet_name("R", room, used_sheet_names)
                room_df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    # Файл уже закрыт благодаря контекстному менеджеру
    return True
