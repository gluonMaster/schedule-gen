import re
from datetime import date

from gear_xls.day_constants import DAY_TO_WEEKDAY


def is_legacy_rental_subject(subject):
    """Exact compatibility marker; never used to reclassify an edited block."""
    return isinstance(subject, str) and subject.strip().casefold() == "vermietung"


def validate_rental_dates(day, dates):
    if not isinstance(dates, list):
        return "rental_dates must be a list"
    for value in dates:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return "rental_dates entries must be YYYY-MM-DD strings"
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return f"rental_dates contains invalid date: {value}"
        if parsed.weekday() != DAY_TO_WEEKDAY.get(day):
            return f"rental_dates contains date {value} not matching block day {day}"
    if day == "So" and not dates:
        return "Sunday rental must contain at least one date"
    return None


def classify_lesson_type(subject: str) -> str:
    """
    Classifies a lesson by type based on the subject string.

    Rules (case-sensitive):
      - Returns 'nachhilfe' if 'Nachhilfe' is in subject (checked first).
      - Returns 'individual' if 'Ind.' is in subject.
      - Returns 'group' otherwise (including None / empty string).

    Args:
        subject: lesson subject string, may be None or empty.

    Returns:
        One of: 'group', 'individual', 'nachhilfe'
    """
    if not subject or not isinstance(subject, str):
        return "group"
    if "Nachhilfe" in subject:
        return "nachhilfe"
    if "Ind." in subject:
        return "individual"
    return "group"


def infer_regular_type_from_subject(subject: str) -> str:
    """
    Infers the target lesson_type when converting a trial block to a regular one.

    Same rules as classify_lesson_type but returns 'individual' as fallback
    (never 'group'), since trial blocks are always non-group lessons.

    Args:
        subject: lesson subject string, may be None or empty.

    Returns:
        One of: 'individual', 'nachhilfe'
    """
    if subject and isinstance(subject, str):
        if "Nachhilfe" in subject:
            return "nachhilfe"
        if "Ind." in subject:
            return "individual"
    return "individual"
