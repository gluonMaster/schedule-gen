from visualiserTV.lesson_label_utils import format_pdf_group_label, should_prefix_russisch_to_group


def test_tv_pdf_group_label_prefixes_russisch_for_plain_russian_group_codes():
    cases = [
        {"subject": "Russisch", "group": "4-5JC", "expected": "Russisch 4-5JC"},
        {"subject": "4Jahrige", "group": "4JA", "expected": "Russisch 4JA"},
        {"subject": "4Jährige", "group": "4JB", "expected": "Russisch 4JB"},
    ]

    for lesson in cases:
        assert should_prefix_russisch_to_group(lesson["subject"], lesson["group"]) is True
        assert format_pdf_group_label(lesson) == lesson["expected"]


def test_tv_pdf_group_label_excludes_log_and_existing_language_markers():
    cases = [
        {"subject": "Russisch", "group": "3-4JC Log"},
        {"subject": "4Jahrige", "group": "4JA Log"},
        {"subject": "Russisch", "group": "4-5J_Log"},
        {"subject": "Russisch", "group": "Russisch 3A"},
        {"subject": "Russisch", "group": "Ru 3A"},
        {"subject": "Mathe", "group": "3A"},
    ]

    for lesson in cases:
        assert should_prefix_russisch_to_group(lesson["subject"], lesson["group"]) is False
        assert format_pdf_group_label(lesson) == lesson["group"]
