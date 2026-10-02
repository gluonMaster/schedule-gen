import math
import os
import sys


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT_DIR, "visualiser"))

from enhanced_export_manager_html import HtmlExportMixin  # noqa: E402
from lesson_label_utils import (  # noqa: E402
    class_age_label,
    format_pdf_group_label,
    group_name_contains_subject,
    normalize_label_text,
    should_show_subject_line,
    should_prefix_russisch_to_group,
)


def _lesson(subject, group, lesson_type="group"):
    return {
        "subject": subject,
        "group": group,
        "lesson_type": lesson_type,
    }


def test_group_subject_display_decisions():
    cases = [
        ("Kunst", "Kunst Sa StudioP", False),
        ("Tanz", "Tanz Mo 6-7J", False),
        ("Deutsch", "Deutsch ab 5J Di", False),
        ("Russish", "2D", True),
        ("Russish", "6A", True),
        ("Russisch", "3JC", True),
        ("Mathe", "6B", True),
        ("Mathe", "Mathe 10B", False),
        ("Logorithmika", "4JA_Log", True),
        ("Ukr. Mus.", "Ukrainische Musik Di 5-6J", False),
        ("Russish", "", True),
    ]

    for subject, group, expected in cases:
        actual = should_show_subject_line(_lesson(subject, group))
        assert actual is expected, (subject, group, actual, expected)


def test_non_group_and_missing_subjects():
    assert should_show_subject_line({"subject": "Ind. Mathe", "group": "Ada"}) is True
    assert should_show_subject_line(_lesson("Physik", "Probe", "trial")) is True
    assert should_show_subject_line(_lesson("", "Kunst Sa StudioP")) is False
    assert should_show_subject_line(_lesson(float("nan"), "2D")) is False
    assert should_show_subject_line(_lesson(math.nan, "2D")) is False


def test_normalization_and_short_subjects():
    assert normalize_label_text(None) == ""
    assert normalize_label_text(float("nan")) == ""
    assert normalize_label_text(" Ukr.  Mus. ") == "ukr mus"
    assert group_name_contains_subject("Ukr. Mus.", "Ukrainische Musik Di 5-6J") is True
    assert should_show_subject_line(_lesson("M", "Mathe Mo")) is True
    assert should_show_subject_line(_lesson("M", "M")) is True


def test_pdf_group_label_prefixes_russisch_for_plain_russian_group_codes():
    cases = [
        ("Russisch", "3A", "Russisch 3A"),
        ("Russisch", "10B", "Russisch 10B"),
        ("Russisch", "3-4J", "Russisch 3-4J"),
        ("Russisch", "4-5JC", "Russisch 4-5JC"),
        ("Russish", "3JC", "Russisch 3JC"),
        ("4Jahrige", "4JA", "Russisch 4JA"),
        ("4Jährige", "4JB", "Russisch 4JB"),
    ]

    for subject, group, expected in cases:
        lesson = _lesson(subject, group)
        assert should_prefix_russisch_to_group(subject, group) is True
        assert format_pdf_group_label(lesson) == expected
        assert should_show_subject_line({**lesson, "group": format_pdf_group_label(lesson)}) is False


def test_pdf_group_label_does_not_prefix_non_russian_or_marked_groups():
    cases = [
        ("Russisch", "Russisch 3A"),
        ("Russisch", "Ru 3A"),
        ("Russisch", "3-4JC Log"),
        ("4Jahrige", "4JA Log"),
        ("Russisch", "4-5J_Log"),
        ("Kunst", "Kunst Mo 3D"),
        ("Schach", "Schach Sa C"),
        ("Tanz", "Tanz Mo 7-8J"),
        ("Ukrainisch", "Ukrainisch Di 5-6J"),
        ("Deutsch", "Deutsch ab 4J Fr"),
        ("Theater", "Theater ab 11J"),
        ("Gitarre", "Gitarre A Mo"),
        ("Mathe", "Mathe 3A"),
        ("Baby", "Baby Sa"),
        ("Logorithmika", "4JA_Log"),
    ]

    for subject, group in cases:
        assert should_prefix_russisch_to_group(subject, group) is False
        assert format_pdf_group_label(_lesson(subject, group)) == group


def test_class_age_label_for_single_grade_groups():
    cases = [
        ("1B", "ab 5J"),
        ("10B", "ab 14J"),
        ("11C", "ab 15J"),
        ("Kunst Sa 12E", "ab 16J"),
        ("Kunst Di 3A", "ab 7J"),
        ("Mathe 8C", "ab 12J"),
        ("4D1", "ab 8J"),
        ("Kunst Sa 1C+1D", "ab 5J"),
    ]

    for group, expected in cases:
        assert class_age_label(group) == expected, group


def test_class_age_label_skips_mixed_grades_and_age_groups():
    groups = [
        "Kunst Fr 6D+8B",
        "Kunst Sa 4B+10D",
        "Musik Sa 2B+3C",
        "3-4JC",
        "3-4JC Log",
        "4-5JA",
        "Do 6-7JA",
        "Tanz Mi ab 7J",
        "Deutsch 1Kl Fr",
        "Schach Mi A",
        "Gitarre A Mo",
        "Kunst Mi StudioO",
        "13A",
        "",
        None,
        math.nan,
    ]

    for group in groups:
        assert class_age_label(group) == "", group


def _html_block(group):
    lesson = {
        "subject": "Kunst",
        "group": group,
        "lesson_type": "group",
        "start_time": "16:00",
        "end_time": "16:45",
        "teacher": "Teacher",
        "room": "1.05",
        "building": "Villa",
    }
    return HtmlExportMixin()._generate_lesson_block_html(lesson, "Di")


def test_html_block_shows_age_next_to_group_and_keeps_group_attribute():
    block = _html_block("Kunst Di 3A")
    assert '<div class="lesson-group">Kunst Di 3A <span class="lesson-age">· ab 7J</span></div>' in block
    assert 'data-group="Kunst Di 3A"' in block

    mixed = _html_block("Kunst Fr 6D+8B")
    assert '<div class="lesson-group">Kunst Fr 6D+8B</div>' in mixed
    assert "lesson-age" not in mixed


if __name__ == "__main__":
    test_group_subject_display_decisions()
    test_non_group_and_missing_subjects()
    test_normalization_and_short_subjects()
    print("visualiser lesson label tests passed")
