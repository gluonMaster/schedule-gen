"""
Shared lesson label helpers for PDF and HTML visualisation.
"""

import math
import re
import unicodedata

from lesson_type_utils import classify_lesson_type


SUBJECT_GROUP_ALIASES = {
    "russish": ("russisch",),
    "russisch": ("russish",),
    "ukr mus": ("ukrainische musik",),
    "ukrainische musik": ("ukr mus",),
}

_SEPARATOR_RE = re.compile(r"[\s\._\-/+(),]+")
_RUSSIAN_GROUP_CODE_RE = re.compile(r"^\d{1,2}(?:-\d{1,2})?[A-Z]{1,3}$", re.IGNORECASE)
_RUSSIAN_MARKER_RE = re.compile(r"(^|[\s\._\-/+(),])(?:ru|russisch)(?=$|[\s\._\-/+(),])", re.IGNORECASE)
_RUSSIAN_SUBJECT_PREFIXES = ("ru", "russ")
_RUSSIAN_TODDLER_SUBJECT_MARKERS = ("jahrige", "jährige", "jaehrige")
_NON_RUSSIAN_GROUP_PREFIXES = (
    "kunst",
    "schach",
    "tanz",
    "ukrainisch",
    "deutsch",
    "theater",
    "gitarre",
    "mathe",
    "baby",
    "log",
)


def _is_missing_value(value):
    if value is None:
        return True

    if value.__class__.__name__ in {"NAType", "NaTType"}:
        return True

    try:
        if isinstance(value, float) and math.isnan(value):
            return True
    except (TypeError, ValueError):
        pass

    try:
        return bool(value != value)
    except (TypeError, ValueError):
        return False


def label_text_or_empty(value):
    """Return display text while keeping missing values out of labels."""
    if _is_missing_value(value):
        return ""
    return str(value).strip()


def normalize_label_text(value):
    """
    Normalize subject/group text for conservative token-aware comparisons.
    """
    text = label_text_or_empty(value)
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text).casefold()
    text = _SEPARATOR_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_russian_subject_text(subject_text):
    return (
        subject_text.startswith(_RUSSIAN_SUBJECT_PREFIXES)
        or any(marker in subject_text for marker in _RUSSIAN_TODDLER_SUBJECT_MARKERS)
    )


def get_lesson_type(lesson):
    """
    Resolve lesson type using explicit lesson_type first, then subject rules.
    """
    raw_lesson_type = label_text_or_empty(lesson.get("lesson_type"))
    if raw_lesson_type:
        return raw_lesson_type.casefold()
    return classify_lesson_type(label_text_or_empty(lesson.get("subject")))


def _contains_normalized_phrase(group_text, subject_text, allow_short=False):
    if not group_text or not subject_text:
        return False
    if not allow_short and len(subject_text) < 3:
        return False

    group_tokens = group_text.split()
    subject_tokens = subject_text.split()
    if not group_tokens or not subject_tokens:
        return False

    if len(subject_tokens) == 1 and not allow_short and len(subject_tokens[0]) < 3:
        return False

    max_start = len(group_tokens) - len(subject_tokens)
    for start in range(max_start + 1):
        if group_tokens[start:start + len(subject_tokens)] == subject_tokens:
            return True
    return False


def group_name_contains_subject(subject, group):
    """
    Return True when the group name already communicates the subject.
    """
    subject_text = normalize_label_text(subject)
    group_text = normalize_label_text(group)
    if not subject_text or not group_text:
        return False

    if _is_russian_subject_text(subject_text):
        if _contains_normalized_phrase(group_text, "russisch", allow_short=True):
            return True
        if _contains_normalized_phrase(group_text, "ru", allow_short=True):
            return True

    if _contains_normalized_phrase(group_text, subject_text):
        return True

    for alias in SUBJECT_GROUP_ALIASES.get(subject_text, ()):
        alias_text = normalize_label_text(alias)
        if _contains_normalized_phrase(group_text, alias_text, allow_short=True):
            return True

    return False


def should_show_subject_line(lesson):
    """
    Decide whether a lesson block should render a separate subject line.
    """
    subject = lesson.get("subject")
    if not normalize_label_text(subject):
        return False

    if get_lesson_type(lesson) != "group":
        return True

    return not group_name_contains_subject(subject, lesson.get("group"))


def should_prefix_russisch_to_group(subject, group):
    """
    Return True when a PDF group label should be shown as 'Russisch <group>'.
    """
    subject_text = normalize_label_text(subject)
    group_text = label_text_or_empty(group)
    group_normalized = normalize_label_text(group)
    if not subject_text or not group_text:
        return False

    if not _is_russian_subject_text(subject_text):
        return False
    if "log" in group_normalized:
        return False
    if _RUSSIAN_MARKER_RE.search(group_text):
        return False
    if group_normalized.startswith(_NON_RUSSIAN_GROUP_PREFIXES):
        return False

    return bool(_RUSSIAN_GROUP_CODE_RE.fullmatch(group_text))


def format_pdf_group_label(lesson):
    """
    Return the group label used in PDF lesson blocks.
    """
    group = label_text_or_empty(lesson.get("group"))
    if should_prefix_russisch_to_group(lesson.get("subject"), group):
        return f"Russisch {group}"
    return group
