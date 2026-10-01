import pandas as pd

from visualiserTV import data_processor


def test_load_data_accepts_russian_schedule_headers(tmp_path):
    path = tmp_path / "schedule.xlsx"
    source = pd.DataFrame(
        [
            {
                "Занятие": "Deutsch",
                "Группа": "G1",
                "Преподаватель": "Teacher",
                "Кабинет": "A101",
                "Здание": "Villa",
                "День": "Mo",
                "Начало": "10:00",
                "Конец": "11:00",
                "Продолжительность": 60,
                "Тип занятия": "group",
                "Даты (JSON)": "",
            }
        ]
    )
    source.to_excel(path, sheet_name="Schedule", index=False)

    loaded = data_processor.load_data(path)

    assert list(loaded.columns) == [
        "subject",
        "group",
        "teacher",
        "room",
        "building",
        "day",
        "start_time",
        "end_time",
        "duration",
        "lesson_type",
        "trial_dates_json",
    ]
    assert loaded.loc[0, "subject"] == "Deutsch"
    assert loaded.loc[0, "lesson_type"] == "group"


def test_filter_by_lesson_type_group_removes_explicit_non_group_types():
    df = pd.DataFrame(
        [
            {"subject": "Deutsch", "lesson_type": "group"},
            {"subject": "Ind. Mathe", "lesson_type": "individual"},
            {"subject": "Nachhilfe Deutsch", "lesson_type": "nachhilfe"},
            {"subject": "Trial", "lesson_type": "trial"},
        ]
    )

    filtered = data_processor.filter_by_lesson_type(df, "group")

    assert filtered["subject"].tolist() == ["Deutsch"]


def test_filter_by_lesson_type_group_uses_subject_fallback_without_lesson_type():
    df = pd.DataFrame(
        [
            {"subject": "Ind. Mathe"},
            {"subject": "Nachhilfe Deutsch"},
            {"subject": "Deutsch"},
        ]
    )

    filtered = data_processor.filter_by_lesson_type(df, "group")

    assert filtered["subject"].tolist() == ["Deutsch"]
