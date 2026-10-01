import pytest

from gear_xls import base_schedule_manager


def _sample_group_block(subject="Math"):
    return {
        "subject": subject,
        "students": "G1",
        "teacher": "Teacher",
        "room": "2.03",
        "room_display": "2.03",
        "building": "Villa",
        "day": "Mo",
        "start_time": "09:00",
        "end_time": "10:00",
        "duration": 60,
        "color": "#fffbd3",
        "lesson_type": "group",
    }


@pytest.fixture()
def isolated_base_schedule(tmp_path, monkeypatch):
    base_path = tmp_path / "base_schedule.json"
    monkeypatch.setattr(base_schedule_manager, "BASE_SCHEDULE_PATH", str(base_path))
    monkeypatch.setattr(base_schedule_manager, "BASE_LOCK_PATH", str(base_path) + ".lock")
    yield base_path


def test_publish_base_rejects_stale_revision_atomically(isolated_base_schedule):
    first = base_schedule_manager.publish_base([_sample_group_block()], "admin", None)

    with pytest.raises(base_schedule_manager.BaseRevisionConflict) as exc_info:
        base_schedule_manager.publish_base(
            [_sample_group_block("Physics")],
            "admin",
            "older-revision",
        )

    assert exc_info.value.current_revision == first["published_at"]
    after_conflict = base_schedule_manager.get_base_schedule()
    assert after_conflict["published_at"] == first["published_at"]
    assert after_conflict["blocks"][0]["subject"] == "Math"


def test_publish_base_noop_preserves_revision(isolated_base_schedule):
    first = base_schedule_manager.publish_base([_sample_group_block()], "admin", None)
    second = base_schedule_manager.publish_base(
        [_sample_group_block()],
        "admin",
        first["published_at"],
    )

    assert second["changed"] is False
    assert second["published_at"] == first["published_at"]
    assert base_schedule_manager.get_base_schedule()["published_at"] == first["published_at"]


def test_publish_route_requires_active_lock(monkeypatch):
    from gear_xls import server_routes

    called = False

    def fail_publish(*args, **kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(server_routes.lock_manager, "get_lock_status", lambda: {"holder": None})
    monkeypatch.setattr(server_routes.state_manager, "publish_base", fail_publish)

    client = server_routes.app.test_client()
    with client.session_transaction() as sess:
        sess["login"] = "admin"
        sess["display_name"] = "Admin"
        sess["role"] = "admin"

    response = client.post(
        "/api/schedule/publish",
        json={"blocks": [], "expected_base_revision": None},
    )

    assert response.status_code == 403
    assert response.get_json()["code"] == "NO_LOCK"
    assert called is False
