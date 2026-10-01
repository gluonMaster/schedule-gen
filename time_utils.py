"""
Вспомогательные функции для работы с временем.
"""

def time_to_minutes(time_str):
    """Convert time string (HH:MM) to minutes since midnight."""
    if not time_str:
        return 0
    hours, minutes = map(int, time_str.split(':'))
    return hours * 60 + minutes

def minutes_to_time(minutes):
    """Convert minutes since midnight to time string (HH:MM)."""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def pause_to_slots(pause_minutes: int, interval: int) -> int:
    """Convert pause minutes to slot count using ceil division."""
    return (pause_minutes + interval - 1) // interval
