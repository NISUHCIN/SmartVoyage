import json
import sys
from pathlib import Path

import mysql.connector
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.auth import cancel_order, create_order
from core.config import Config


def _conn():
    conf = Config()
    return mysql.connector.connect(
        host=conf.host, user=conf.user, password=conf.password,
        database=conf.database, port=conf.db_port
    )


def _db_available():
    try:
        conn = _conn()
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="MySQL 不可用")


@pytest.fixture()
def temp_train_row():
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO train_tickets "
        "(departure_city, arrival_city, departure_time, arrival_time, train_number, "
        "seat_type, total_seats, remaining_seats, price) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        ("测试市", "测试城", "2026-09-01 08:00:00", "2026-09-01 11:00:00",
         "TEST9999", "二等座", 100, 5, 100.0)
    )
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    yield item_id
    conn = _conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM train_tickets WHERE id = %s", (item_id,))
    cur.execute("DELETE FROM orders WHERE item_desc LIKE %s", ('%"train_number": "TEST9999"%',))
    conn.commit()
    conn.close()


def test_create_order_deducts_stock_and_cancel_restores(temp_train_row):
    conn = _conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT remaining_seats, price FROM train_tickets WHERE id = %s", (temp_train_row,))
    before = cur.fetchone()
    conn.close()

    ok, msg, data = create_order(
        user_id=7, order_type="train", item_id=temp_train_row, quantity=2,
        unit_price=before["price"],
        item_desc=json.dumps({"train_number": "TEST9999"}, ensure_ascii=False)
    )
    assert ok, msg

    conn = _conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT remaining_seats FROM train_tickets WHERE id = %s", (temp_train_row,))
    after = cur.fetchone()
    conn.close()
    assert after["remaining_seats"] == before["remaining_seats"] - 2

    ok_cancel, cancel_msg = cancel_order(data["order_no"], 7)
    assert ok_cancel, cancel_msg

    conn = _conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT remaining_seats FROM train_tickets WHERE id = %s", (temp_train_row,))
    restored = cur.fetchone()
    conn.close()
    assert restored["remaining_seats"] == before["remaining_seats"]


def test_create_order_fails_when_stock_insufficient(temp_train_row):
    ok, msg, data = create_order(
        user_id=8, order_type="train", item_id=temp_train_row, quantity=999,
        unit_price=100.0,
        item_desc=json.dumps({"train_number": "TEST9999"}, ensure_ascii=False)
    )
    assert not ok
    assert data is None

    conn = _conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT remaining_seats FROM train_tickets WHERE id = %s", (temp_train_row,))
    row = cur.fetchone()
    conn.close()
    assert row["remaining_seats"] == 5


def test_cancel_twice_restores_stock_once(temp_train_row):
    conn = _conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT remaining_seats, price FROM train_tickets WHERE id = %s", (temp_train_row,))
    before = cur.fetchone()
    conn.close()

    ok, msg, data = create_order(
        user_id=9, order_type="train", item_id=temp_train_row, quantity=2,
        unit_price=before["price"],
        item_desc=json.dumps({"train_number": "TEST9999"}, ensure_ascii=False)
    )
    assert ok, msg

    ok1, msg1 = cancel_order(data["order_no"], 9)
    ok2, msg2 = cancel_order(data["order_no"], 9)
    assert ok1, msg1
    assert not ok2

    conn = _conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT remaining_seats FROM train_tickets WHERE id = %s", (temp_train_row,))
    restored = cur.fetchone()
    conn.close()
    assert restored["remaining_seats"] == before["remaining_seats"]
