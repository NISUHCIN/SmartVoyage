"""面试演示复位：取消沙箱订单、释放虚拟占用并恢复本地库存。"""
from __future__ import annotations

from typing import Any

from core.create_logger import logger
from utils.db import get_connection

_STOCK_COLUMN = {
    "train": ("train_tickets", "remaining_seats"),
    "flight": ("flight_tickets", "remaining_seats"),
    "concert": ("concert_tickets", "remaining_seats"),
    "hotel": ("hotel_rooms", "remaining_rooms"),
}


def demo_environment_stats() -> dict[str, Any]:
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT COUNT(*) AS n FROM virtual_train_bookings WHERE status = 'confirmed'"
        )
        virtual_orders = int(cur.fetchone()["n"] or 0)
        cur.execute("SELECT COUNT(*) AS n FROM orders WHERE status = 'confirmed'")
        confirmed_orders = int(cur.fetchone()["n"] or 0)
        cur.close()
        return {
            "confirmed_orders": confirmed_orders,
            "virtual_occupancies": virtual_orders,
        }
    except Exception as exc:
        logger.warning(f"读取演示复位状态失败: {exc}")
        return {"confirmed_orders": 0, "virtual_occupancies": 0, "db": "error"}
    finally:
        if conn and conn.is_connected():
            conn.close()


def reset_demo_environment() -> dict[str, Any]:
    """复位演示数据并恢复本地库存。返回受影响数量。"""
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)

        cur.execute(
            "SELECT o.order_no, o.order_type, o.item_id, o.quantity "
            "FROM orders o "
            "LEFT JOIN users u ON o.user_id = u.id "
            "WHERE o.status = 'confirmed' AND "
            "(u.username = 'demo_user' OR o.item_desc LIKE '%virtual_demo%') "
            "FOR UPDATE"
        )
        orders = cur.fetchall()

        order_nos = [row["order_no"] for row in orders]
        restored_items = 0
        if order_nos:
            placeholders = ",".join(["%s"] * len(order_nos))
            for order in orders:
                table_info = _STOCK_COLUMN.get(order["order_type"])
                if not table_info or not order.get("item_id"):
                    continue
                table, stock_col = table_info
                cur.execute(
                    f"UPDATE {table} SET {stock_col} = {stock_col} + %s WHERE id = %s",
                    (order["quantity"], order["item_id"]),
                )
                restored_items += max(0, cur.rowcount)

            cur.execute(
                f"UPDATE orders SET status = 'cancelled' WHERE order_no IN ({placeholders}) "
                "AND status = 'confirmed'",
                order_nos,
            )
            cancelled_orders = max(0, cur.rowcount)
            cur.execute(
                f"UPDATE virtual_train_bookings SET status = 'cancelled' "
                f"WHERE order_no IN ({placeholders}) AND status = 'confirmed'",
                order_nos,
            )
            released = max(0, cur.rowcount)
        else:
            cancelled_orders = 0
            released = 0

        # 兜底清理无订单关联的孤儿占用
        cur.execute(
            "UPDATE virtual_train_bookings SET status = 'cancelled' "
            "WHERE status = 'confirmed' AND order_no NOT IN "
            "(SELECT order_no FROM orders WHERE status = 'confirmed')"
        )
        orphan_released = max(0, cur.rowcount)
        conn.commit()
        cur.close()
        return {
            "orders_cancelled": cancelled_orders,
            "occupancy_released": released + orphan_released,
            "stock_restored_rows": restored_items,
            "status": "ok",
        }
    except Exception as exc:
        if conn:
            conn.rollback()
        logger.error(f"演示数据复位失败: {exc}")
        return {"status": "error", "message": str(exc)}
    finally:
        if conn and conn.is_connected():
            conn.close()
