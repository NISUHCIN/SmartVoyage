from backend.demo_reset import demo_environment_stats, reset_demo_environment


def _broken_connection():
    raise RuntimeError("database unavailable")


def test_demo_stats_degrade_gracefully_when_database_is_down(monkeypatch):
    monkeypatch.setattr("backend.demo_reset.get_connection", _broken_connection)

    stats = demo_environment_stats()

    assert stats["db"] == "error"
    assert stats["confirmed_orders"] == 0


def test_demo_reset_degrade_gracefully_when_database_is_down(monkeypatch):
    monkeypatch.setattr("backend.demo_reset.get_connection", _broken_connection)

    result = reset_demo_environment()

    assert result["status"] == "error"
