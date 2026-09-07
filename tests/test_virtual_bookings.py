import json
import sys
from pathlib import Path

import mysql.connector
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.virtual_bookings import (
    booking_key_for_row,
    create_virtual_hotel_order,
    create_virtual_train_order,
    release_by_order_no,
)
from core.config import Config


def _conn():
    conf = Config()
    return mysql.connector.connect(
        host=conf.host, user=conf.user, password=conf.password,
        database=conf.database, port=conf.db_port,
    )


def _db_available():
    try:
        conn = _conn()
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="MySQL 不可用")


def _sample_train() -> dict:
    return {
        "departure_city": "北京",
        "arrival_city": "上海",
        "departure_time": "2026-09-08 08:05:00",
        "arrival_time": "2026-09-08 11:12:00",
        "travel_date": "2026-09-08",
        "train_number": "G1234",
        "train_type": "高铁",
        "seat_type": "二等座",
        "price": 553.0,
        "remaining_seats": 20,
        "_booking": {
            "train_uuid": "240000G12340",
            "departure_station_code": "AOH",
            "arrival_station_code": "HGH",
        },
    }


def test_booking_key_is_stable_and_sensitive_to_train_seat_and_date():
    same = dict(_sample_train())
    assert booking_key_for_row(same) == booking_key_for_row(_sample_train())

    other_seat = dict(_sample_train())
    other_seat["seat_type"] = "一等座"
    assert booking_key_for_row(other_seat) != booking_key_for_row(_sample_train())

    other_date = dict(_sample_train())
    other_date["travel_date"] = "2026-09-09"
    assert booking_key_for_row(other_date) != booking_key_for_row(_sample_train())

    other_train = dict(_sample_train())
    other_train["train_number"] = "G5678"
    assert booking_key_for_row(other_train) != booking_key_for_row(_sample_train())


def test_virtual_hotel_order_rejects_missing_price_without_database():
    ok, message, data = create_virtual_hotel_order(
        {"price": 0},
        {"price": "--"},
        "2026-09-08",
        1,
        1,
        None,
        "张三",
        "13800000000",
    )

    assert ok is False
    assert "未返回" in message
    assert data == {}


def test_virtual_train_order_and_release_roundtrip():
    ok, message, data = create_virtual_train_order(
        _sample_train(),
        2,
        user_id=100099,
        passenger_name="张三",
        contact_phone="13800000000",
    )
    assert ok, message
    order_no = data["order_no"]

    try:
        conn = _conn()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT quantity, status FROM virtual_train_bookings WHERE order_no = %s",
            (order_no,),
        )
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row["quantity"] == 2
        assert row["status"] == "confirmed"
    finally:
        release_by_order_no(order_no)
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM virtual_train_bookings WHERE order_no = %s",
            (order_no,),
        )
        cur.execute("DELETE FROM orders WHERE order_no = %s", (order_no,))
        conn.commit()
        conn.close()


def test_virtual_hotel_order_persists_demo_order_when_database_available():
    ok, message, data = create_virtual_hotel_order(
        {
            "hotel_name": "测试酒店",
            "city": "测试城",
            "hotel_id": "H-TEST-1",
            "price": 388.0,
        },
        {"room_type": "标准房", "price": 388.0},
        "2026-09-08",
        1,
        1,
        user_id=100099,
        guest_name="张三",
        contact_phone="13800000000",
    )
    assert ok, message
    order_no = data["order_no"]

    try:
        conn = _conn()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT item_desc FROM orders WHERE order_no = %s AND status = 'confirmed'",
            (order_no,),
        )
        row = cur.fetchone()
        conn.close()
        assert row is not None
        item_desc = json.loads(row["item_desc"])
        assert item_desc["mode"] == "virtual_demo"
        assert item_desc["hotel_name"] == "测试酒店"
    finally:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM orders WHERE order_no = %s", (order_no,))
        conn.commit()
        conn.close()
