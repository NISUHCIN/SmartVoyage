import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.query_builders import (
    build_train_query,
    build_weather_query,
    build_hotel_query,
)


def test_build_train_query_with_seat():
    sql, params = build_train_query("北京", "上海", "2026-09-01", seat_type="二等座")
    assert "WHERE departure_city = %s" in sql
    assert "seat_type = %s" in sql
    assert params == ["北京", "上海", "2026-09-01", "二等座"]


def test_build_train_query_without_seat():
    sql, params = build_train_query("北京", "上海", "2026-09-01")
    assert "seat_type = %s" not in sql
    assert params == ["北京", "上海", "2026-09-01"]


def test_build_weather_query_range():
    sql, params = build_weather_query("北京", "2026-09-01", "2026-09-03")
    assert "BETWEEN %s AND %s" in sql
    assert params == ["北京", "2026-09-01", "2026-09-03"]


def test_build_hotel_query_with_filters():
    sql, params = build_hotel_query(
        "北京", district="朝阳区", room_type="大床房",
        price_min=300, price_max=800, rating_min=4.5
    )
    assert "price >= %s" in sql
    assert "rating >= %s" in sql
    assert params == ["北京", "%朝阳区%", "%大床房%", 300, 800, 4.5]
