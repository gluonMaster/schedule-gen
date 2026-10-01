"""Shared day constants for web-editor and public schedule flows."""

WEB_EDITOR_DAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
PUBLIC_SCHEDULE_DAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa")
TRIAL_ONLY_DAYS = frozenset({"So"})

DAY_TO_WEEKDAY = {
    "Mo": 0,
    "Di": 1,
    "Mi": 2,
    "Do": 3,
    "Fr": 4,
    "Sa": 5,
    "So": 6,
}

WEB_EDITOR_DAY_SET = frozenset(WEB_EDITOR_DAYS)
PUBLIC_SCHEDULE_DAY_SET = frozenset(PUBLIC_SCHEDULE_DAYS)
