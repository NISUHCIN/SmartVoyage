"""真实车次 + 本地虚拟订票的占用服务。

聚美智数只负责真实余票查询；本模块在项目自己的 MySQL 中记录“虚拟占用”，
使再次查询时能看到余量按本地虚拟订单递减。任何代码都不会调用外部真实下单。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from core.create_logger import logger
from utils.db import get_connection


def _to_float(value) -> float:
    """兼容真实接口常见的 ¥、千分位与 --/有票 等价格占位。"""
    if value is None:
        return 0.0
    try:
        return float(str(value).replace("¥", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS virtual_train_bookings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    booking_key VARCHAR(64) NOT NULL,
    order_no VARCHAR(36) NOT NULL,
    user_id INT NULL,
    travel_date DATE NOT NULL,
    train_no VARCHAR(20) NOT NULL,
    seat_type VARCHAR(20) NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'confirmed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_booking_order (booking_key, order_no),
    KEY idx_booking_key_status (booking_key, status),
    KEY idx_order_no (order_no)
) ENGINE=INNODB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def ensure_table_with_cursor(cursor) -> None:
    cursor.execute(CREATE_TABLE_SQL)


def ensure_virtual_table() -> None:
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        ensure_table_with_cursor(cursor)
        conn.commit()
        cursor.close()
    finally:
        if conn and conn.is_connected():
            conn.close()


def booking_key_for_row(row: dict) -> str:
    """同一真实车次、同一乘车日、同一起终点、同席别对应一个沙箱占用键。"""
    departure_time = str(row.get("departure_time") or row.get("travel_date") or "")
    travel_date = str(row.get("travel_date") or departure_time[:10])
    booking = row.get("_booking") or {}
    train_uuid = str(booking.get("train_uuid") or row.get("train_number") or "")
    from_code = str(booking.get("departure_station_code") or "")
    to_code = str(booking.get("arrival_station_code") or "")
    raw = f"{travel_date}|{train_uuid}|{from_code}|{to_code}|{row.get('seat_type')}|{row.get('train_number')}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def occupied_counts(rows: list[dict]) -> dict[str, int]:
    """返回 booking_key -> 已虚拟占用张数。"""
    if not rows:
        return {}
    keys = list(dict.fromkeys(booking_key_for_row(row) for row in rows))
    conn = None
    try:
        ensure_virtual_table()
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        placeholders = ",".join(["%s"] * len(keys))
        cursor.execute(
            f"SELECT booking_key, SUM(quantity) AS total "
            f"FROM virtual_train_bookings "
            f"WHERE booking_key IN ({placeholders}) AND status = 'confirmed' "
            f"GROUP BY booking_key",
            keys,
        )
        result = {item["booking_key"]: int(item["total"] or 0) for item in cursor.fetchall()}
        cursor.close()
        return result
    except Exception as exc:
        logger.error(f"读取虚拟占用失败: {exc}")
        return {}
    finally:
        if conn and conn.is_connected():
            conn.close()


def apply_virtual_occupancy(rows: list[dict]) -> list[dict]:
    """给真实票行扣减本系统已虚拟订票数量。"""
    occupancy = occupied_counts(rows)
    for row in rows:
        key = booking_key_for_row(row)
        occupied = occupancy.get(key, 0)
        row["_booking_key"] = key
        row["virtual_occupied"] = occupied
        if occupied <= 0:
            row["virtual_occupied"] = 0
            continue
        if row.get("remaining_seats") is not None:
            remaining = max(0, int(row["remaining_seats"]) - occupied)
            row["remaining_seats"] = remaining
            row["remaining_text"] = f"{remaining}张"
        else:
            row["remaining_text"] = f"余票充足（本系统已占用{occupied}）"
    return rows


def create_virtual_train_order(
    train: dict,
    quantity: int,
    user_id: Optional[int],
    passenger_name: str,
    contact_phone: str,
) -> tuple[bool, str, dict]:
    """在同一事务中写入 orders + virtual_train_bookings。"""
    quantity = max(1, int(quantity or 1))
    price = _to_float(train.get("price"))
    if price <= 0:
        return False, "该班次未返回可虚拟订票的价格", {}

    booking_key = booking_key_for_row(train)
    order_no = str(uuid.uuid4())
    travel_date = str(train.get("travel_date") or str(train.get("departure_time") or "")[:10])
    total_price = round(price * quantity, 2)
    item_desc = json.dumps(
        {
            "order_no": order_no,
            "travel_date": travel_date,
            "train_no": train.get("train_number", ""),
            "train_uuid": (train.get("_booking") or {}).get("train_uuid", ""),
            "departure_city": train.get("departure_city", ""),
            "arrival_city": train.get("arrival_city", ""),
            "departure_time": train.get("departure_time", ""),
            "arrival_time": train.get("arrival_time", ""),
            "seat_type": train.get("seat_type", ""),
            "price": price,
            "quantity": quantity,
            "total_price": total_price,
            "booking_key": booking_key,
            "mode": "virtual_demo",
        },
        ensure_ascii=False,
    )

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        ensure_table_with_cursor(cursor)
        cursor.execute(
            """INSERT INTO orders
               (order_no, user_id, order_type, item_id, item_desc, quantity,
                unit_price, total_price, contact_name, contact_phone, status)
               VALUES (%s, %s, 'train', NULL, %s, %s, %s, %s, %s, %s, 'confirmed')""",
            (
                order_no,
                user_id,
                item_desc,
                quantity,
                price,
                total_price,
                passenger_name,
                contact_phone,
            ),
        )
        cursor.execute(
            """INSERT INTO virtual_train_bookings
               (booking_key, order_no, user_id, travel_date, train_no, seat_type, quantity, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'confirmed')""",
            (
                booking_key,
                order_no,
                user_id,
                travel_date,
                train.get("train_number", ""),
                train.get("seat_type", ""),
                quantity,
            ),
        )
        conn.commit()
        cursor.close()
        return True, "虚拟订票成功（沙箱演示，不产生真实出票）", {
            "order_no": order_no,
            "total_price": total_price,
            "status": "confirmed",
            "mode": "virtual_demo",
        }
    except Exception as exc:
        if conn:
            conn.rollback()
        logger.error(f"创建虚拟火车票订单失败: {exc}")
        return False, f"虚拟订票失败: {exc}", {}
    finally:
        if conn and conn.is_connected():
            conn.close()


def create_virtual_hotel_order(
    hotel: dict,
    room: dict,
    check_in: str,
    nights: int,
    rooms: int,
    user_id: Optional[int],
    guest_name: str,
    contact_phone: str,
) -> tuple[bool, str, dict]:
    """按真实/演示酒店与房型生成沙箱酒店订单，不调用 RollingGo 下单。"""
    nights = max(1, int(nights or 1))
    rooms = max(1, int(rooms or 1))
    price = _to_float(room.get("price") or hotel.get("price"))
    if price <= 0:
        return False, "该酒店/房型未返回可虚拟预订的价格", {}

    order_no = str(uuid.uuid4())
    check_in = str(check_in or "")
    try:
        check_out = (
            datetime.strptime(check_in, "%Y-%m-%d") + timedelta(days=nights)
        ).strftime("%Y-%m-%d")
    except ValueError:
        check_out = ""
    total_price = round(price * nights * rooms, 2)
    merged = {**hotel, **room}
    item_desc = json.dumps(
        {
            "order_no": order_no,
            "hotel_name": hotel.get("hotel_name") or room.get("hotel_name") or "",
            "city": hotel.get("city") or "",
            "district": hotel.get("district") or "",
            "address": hotel.get("address") or "",
            "hotel_id": hotel.get("hotel_id") or (hotel.get("_booking") or {}).get("hotel_id", ""),
            "room_type": room.get("room_type") or hotel.get("room_type") or "标准房",
            "rate_plan_name": room.get("rate_plan_name") or "",
            "bed_type": room.get("bed_type") or "",
            "price_per_night": price,
            "currency": room.get("currency") or hotel.get("currency") or "CNY",
            "check_in": check_in,
            "check_out": check_out,
            "nights": nights,
            "rooms": rooms,
            "guest_name": guest_name,
            "contact_phone": contact_phone,
            "meal_type": room.get("meal_type") or "",
            "cancel_policy": room.get("cancel_policy") or "",
            "source": merged.get("source") or hotel.get("source") or "RollingGo 真实接口",
            "mode": "virtual_demo",
            "booking_key": room.get("_booking_key") or hotel.get("_booking_key") or "",
        },
        ensure_ascii=False,
    )

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO orders
               (order_no, user_id, order_type, item_id, item_desc, quantity,
                unit_price, total_price, contact_name, contact_phone, status)
               VALUES (%s, %s, 'hotel', NULL, %s, %s, %s, %s, %s, %s, 'confirmed')""",
            (
                order_no,
                user_id,
                item_desc,
                rooms,
                price,
                total_price,
                guest_name,
                contact_phone,
            ),
        )
        conn.commit()
        cursor.close()
        return True, "虚拟酒店预订成功（沙箱演示，不产生真实扣款）", {
            "order_no": order_no,
            "total_price": total_price,
            "nights": nights,
            "rooms": rooms,
            "status": "confirmed",
            "mode": "virtual_demo",
        }
    except Exception as exc:
        if conn:
            conn.rollback()
        logger.error(f"创建虚拟酒店订单失败: {exc}")
        return False, f"虚拟酒店预订失败: {exc}", {}
    finally:
        if conn and conn.is_connected():
            conn.close()


def release_by_order_no(order_no: str) -> None:
    """取消订单后释放虚拟占用。"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        ensure_table_with_cursor(cursor)
        cursor.execute(
            "UPDATE virtual_train_bookings SET status = 'cancelled' "
            "WHERE order_no = %s AND status = 'confirmed'",
            (order_no,),
        )
        conn.commit()
        cursor.close()
    except Exception as exc:
        logger.error(f"释放虚拟占用失败: {exc}")
    finally:
        if conn and conn.is_connected():
            conn.close()
