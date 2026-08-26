"""
mcp_order_server.py：订票 MCP 服务器，通过数据库完成真实下单。

核心功能：
    火车票/飞机票/演唱会票/酒店的真实预定。
    下单与库存扣减放在同一事务，取消订单时恢复库存。
    通过 FastMCP 提供 HTTP 接口，响应 MCP 工具调用。
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import json
from typing import Optional
from mcp.server.fastmcp import FastMCP
from core.config import Config
from core.create_logger import logger
from backend.auth import create_order

conf = Config()

order_mcp = FastMCP(
    name="OrderTools",
    instructions="票务预定工具，通过数据库完成火车票、飞机票、演唱会票和酒店的真实预定，含库存扣减。",
    log_level="ERROR",
    host="127.0.0.1", port=conf.mcp_order_port
)


def _get_conn():
    from utils.db import get_connection
    return get_connection()


def _order_response(ok: bool, msg: str, data: dict = None) -> str:
    payload = {"status": "success" if ok else "error", "message": msg}
    if data:
        payload.update(data)
    return json.dumps(payload, ensure_ascii=False)


@order_mcp.tool(
    name="order_train",
    description="预定火车票。根据出发日期、车次、座位类型和数量完成预定，会扣减真实库存并创建订单。"
)
def order_train(departure_date: str, train_number: str, seat_type: str, number: int,
                user_id: Optional[int] = None, request_id: Optional[str] = None) -> str:
    logger.info(f"预定火车票: {departure_date}, {train_number}, {seat_type}, {number}, "
                f"user={user_id} rid={request_id or '-'}")
    conn = None
    try:
        conn = _get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM train_tickets WHERE train_number = %s AND seat_type = %s AND DATE(departure_time) = %s",
            (train_number, seat_type, departure_date)
        )
        ticket = cursor.fetchone()
        conn.close()
        conn = None

        if not ticket:
            return _order_response(False, f"未找到车次{train_number} {departure_date} {seat_type}")

        item_desc = json.dumps({
            "train_number": ticket["train_number"],
            "departure_city": ticket["departure_city"],
            "arrival_city": ticket["arrival_city"],
            "departure_time": str(ticket["departure_time"]),
            "arrival_time": str(ticket["arrival_time"]),
            "seat_type": seat_type,
        }, ensure_ascii=False)
        ok, msg, data = create_order(
            order_type="train", item_desc=item_desc, quantity=number,
            unit_price=float(ticket["price"]), item_id=ticket["id"], user_id=user_id
        )
        if not ok:
            return _order_response(False, msg)
        return _order_response(True, msg, {"order_no": data["order_no"]})
    except Exception as e:
        logger.error(f"火车票预定失败: {e}")
        return _order_response(False, str(e))
    finally:
        if conn and conn.is_connected():
            conn.close()


@order_mcp.tool(
    name="order_flight",
    description="预定飞机票。根据出发日期、航班号、舱位类型和数量完成预定，会扣减真实库存并创建订单。"
)
def order_flight(departure_date: str, flight_number: str, seat_type: str, number: int,
                 user_id: Optional[int] = None, request_id: Optional[str] = None) -> str:
    logger.info(f"预定飞机票: {departure_date}, {flight_number}, {seat_type}, {number}, "
                f"user={user_id} rid={request_id or '-'}")
    conn = None
    try:
        conn = _get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM flight_tickets WHERE flight_number = %s AND cabin_type = %s AND DATE(departure_time) = %s",
            (flight_number, seat_type, departure_date)
        )
        ticket = cursor.fetchone()
        conn.close()
        conn = None

        if not ticket:
            return _order_response(False, f"未找到航班{flight_number} {departure_date} {seat_type}")

        item_desc = json.dumps({
            "flight_number": ticket["flight_number"],
            "departure_city": ticket["departure_city"],
            "arrival_city": ticket["arrival_city"],
            "departure_time": str(ticket["departure_time"]),
            "arrival_time": str(ticket["arrival_time"]),
            "cabin_type": seat_type,
        }, ensure_ascii=False)
        ok, msg, data = create_order(
            order_type="flight", item_desc=item_desc, quantity=number,
            unit_price=float(ticket["price"]), item_id=ticket["id"], user_id=user_id
        )
        if not ok:
            return _order_response(False, msg)
        return _order_response(True, msg, {"order_no": data["order_no"]})
    except Exception as e:
        logger.error(f"飞机票预定失败: {e}")
        return _order_response(False, str(e))
    finally:
        if conn and conn.is_connected():
            conn.close()


@order_mcp.tool(
    name="order_concert",
    description="预定演出票。根据开始日期、艺人、场地、票类型和数量完成预定，会扣减真实库存并创建订单。"
)
def order_concert(start_date: str, artist: str, venue: str, seat_type: str, number: int,
                  user_id: Optional[int] = None, request_id: Optional[str] = None) -> str:
    logger.info(f"预定演出票: {start_date}, {artist}, {venue}, {seat_type}, {number}, "
                f"user={user_id} rid={request_id or '-'}")
    conn = None
    try:
        conn = _get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM concert_tickets WHERE artist = %s AND venue = %s AND ticket_type = %s AND DATE(start_time) = %s",
            (artist, venue, seat_type, start_date)
        )
        ticket = cursor.fetchone()
        conn.close()
        conn = None

        if not ticket:
            return _order_response(False, f"未找到{artist}在{venue}的演出 {start_date} {seat_type}")

        item_desc = json.dumps({
            "artist": artist,
            "venue": venue,
            "start_time": str(ticket["start_time"]),
            "ticket_type": seat_type,
        }, ensure_ascii=False)
        ok, msg, data = create_order(
            order_type="concert", item_desc=item_desc, quantity=number,
            unit_price=float(ticket["price"]), item_id=ticket["id"], user_id=user_id
        )
        if not ok:
            return _order_response(False, msg)
        return _order_response(True, msg, {"order_no": data["order_no"]})
    except Exception as e:
        logger.error(f"演出票预定失败: {e}")
        return _order_response(False, str(e))
    finally:
        if conn and conn.is_connected():
            conn.close()


@order_mcp.tool(
    name="order_hotel",
    description="预定酒店房间。根据酒店名称、城市、房型和数量完成预定，会扣减真实库存并创建订单。"
)
def order_hotel(hotel_name: str, city: str, room_type: str, number: int,
                user_id: Optional[int] = None, request_id: Optional[str] = None) -> str:
    logger.info(f"预定酒店: {hotel_name}, {city}, {room_type}, {number}, "
                f"user={user_id} rid={request_id or '-'}")
    conn = None
    try:
        conn = _get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM hotel_rooms WHERE hotel_name = %s AND city = %s AND room_type = %s",
            (hotel_name, city, room_type)
        )
        room = cursor.fetchone()
        conn.close()
        conn = None

        if not room:
            return _order_response(False, f"未找到{hotel_name} {room_type}")

        item_desc = json.dumps({
            "hotel_name": hotel_name,
            "city": city,
            "room_type": room_type,
        }, ensure_ascii=False)
        ok, msg, data = create_order(
            order_type="hotel", item_desc=item_desc, quantity=number,
            unit_price=float(room["price"]), item_id=room["id"], user_id=user_id
        )
        if not ok:
            return _order_response(False, msg)
        return _order_response(True, msg, {"order_no": data["order_no"]})
    except Exception as e:
        logger.error(f"酒店预定失败: {e}")
        return _order_response(False, str(e))
    finally:
        if conn and conn.is_connected():
            conn.close()


def create_order_mcp_server() -> None:
    logger.info("=== 票务预定MCP服务器信息 ===")
    logger.info(f"名称: {order_mcp.name}")
    logger.info(f"描述: {order_mcp.instructions}")

    try:
        logger.info(f"服务器已启动，请访问 http://127.0.0.1:{conf.mcp_order_port}/mcp")
        order_mcp.run(transport="streamable-http")
    except Exception as e:
        logger.error(f"服务器启动失败: {e}")


if __name__ == "__main__":
    create_order_mcp_server()
