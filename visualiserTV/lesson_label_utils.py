import math
import re
import unicodedata


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
    if _is_missing_value(value):
        return ""
    return str(value).strip()


def normalize_label_text(value):
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


def should_prefix_russisch_to_group(subject, group):
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
    group = label_text_or_empty(lesson.get("group"))
    if should_prefix_russisch_to_group(lesson.get("subject"), group):
        return f"Russisch {group}"
    return group
