"""Resource and calendar rules for pairs containing an explicit rental."""
from datetime import date

from gear_xls.day_constants import DAY_TO_WEEKDAY
from gear_xls.room_name_utils import normalize_room_name
from time_utils import time_to_minutes


def is_rental(event):
    return getattr(event, "lesson_type", "") == "rental"


def teacher_resource(event):
    return "" if is_rental(event) else event.teacher


def room_keys(event):
    return {(event.building, normalize_room_name(room, event.building))
            for room in event.possible_rooms if room}


def event_dates(event):
    if is_rental(event):
        return getattr(event, "rental_dates", [])
    if getattr(event, "lesson_type", "") == "trial":
        return getattr(event, "trial_dates", [])
    return []


def active_dates(event, calculation_date):
    result = set()
    for value in event_dates(event):
        try:
            parsed = date.fromisoformat(value)
        except (TypeError, ValueError):
            continue
        if parsed >= calculation_date and (
            not event.day or parsed.weekday() == DAY_TO_WEEKDAY.get(event.day)
        ):
            result.add(parsed)
    return result


def rental_calendar_overlap(first, second, calculation_date):
    """Unknown lesson day remains possible; day_vars enforce the selected day."""
    if not (is_rental(first) or is_rental(second)):
        return True  # Leave existing non-rental trial rules alone.
    dates1, dates2 = event_dates(first), event_dates(second)
    if dates1 and dates2:
        return bool(active_dates(first, calculation_date) & active_dates(second, calculation_date))
    if dates1 or dates2:
        dated, weekly = (first, second) if dates1 else (second, first)
        return any(not weekly.day or day.weekday() == DAY_TO_WEEKDAY.get(weekly.day)
                   for day in active_dates(dated, calculation_date))
    return True


def fixed_conflict_type(first, second, calculation_date):
    """Diagnostic for fixed placements; variable rooms/time are left to the solver."""
    if first.day and second.day and first.day != second.day:
        return None
    if not rental_calendar_overlap(first, second, calculation_date):
        return None
    if not first.start_time or not second.start_time:
        return None
    start1, start2 = time_to_minutes(first.start_time), time_to_minutes(second.start_time)
    if not (start1 < start2 + second.duration and start2 < start1 + first.duration):
        return None
    if teacher_resource(first) and teacher_resource(first) == teacher_resource(second):
        return "teacher"
    if room_keys(first) & room_keys(second):
        return "room"
    if set(first.get_groups()) & set(second.get_groups()):
        return "group"
    return None
