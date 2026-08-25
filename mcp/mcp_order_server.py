"""
mcp_order_server.py：订票 MCP 服务器，通过数据库完成真实下单。

核心功能：
    火车票/飞机票/演唱会票/酒店的真实预定。
    查询余票、检查库存、创建订单、扣减库存。
    通过 FastMCP 提供 HTTP 接口，响应 MCP 工具调用。
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import json
from mcp.server.fastmcp import FastMCP
from core.config import Config
from core.create_logger import logger

conf = Config()

order_mcp = FastMCP(
    name="OrderTools",
    instructions="票务预定工具，通过数据库完成火车票、飞机票、演唱会票和酒店的真实预定，含库存扣减。",
    log_level="ERROR",
    host="127.0.0.1", port=8003
)


def _get_conn():
    import mysql.connector
    return mysql.connector.connect(
        host=conf.host, user=conf.user, password=conf.password,
        database=conf.database, port=conf.db_port
    )


def _check_and_deduct(table: str, id_col: str, stock_col: str,
                      item_id: int, quantity: int) -> dict:
    """通用库存检查与扣减"""
    conn = None
    try:
        conn = _get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (item_id,))
        item = cursor.fetchone()
        if not item:
            return {"status": "error", "message": f"未找到ID为{item_id}的记录"}

        remaining = item.get(stock_col, 0)
        if remaining < quantity:
            return {"status": "error", "message": f"库存不足，仅剩{remaining}，需要{quantity}"}

        cursor.execute(
            f"UPDATE {table} SET {stock_col} = {stock_col} - %s WHERE id = %s AND {stock_col} >= %s",
            (quantity, item_id, quantity)
        )
        conn.commit()
        return {"status": "success", "item": item}
    except Exception as e:
        logger.error(f"库存操作失败: {e}")
        if conn:
            conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        if conn and conn.is_connected():
            conn.close()


@order_mcp.tool(
    name="order_train",
    description="预定火车票。根据出发日期、车次、座位类型和数量完成预定，会扣减真实库存。"
)
def order_train(departure_date: str, train_number: str, seat_type: str, number: int) -> str:
    logger.info(f"预定火车票: {departure_date}, {train_number}, {seat_type}, {number}")
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
            return json.dumps({"status": "error", "message": f"未找到车次{train_number} {departure_date} {seat_type}"}, ensure_ascii=False)

        result = _check_and_deduct("train_tickets", "id", "remaining_seats", ticket["id"], number)
        if result["status"] == "error":
            return json.dumps(result, ensure_ascii=False)

        t = result["item"]
        return json.dumps({
            "status": "success",
            "message": f"预定成功！{t['departure_city']}到{t['arrival_city']} {t['departure_time']} 车次{train_number} {seat_type} {number}张 票价{t['price']}元/张 总价{float(t['price'])*number:.2f}元"
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"火车票预定失败: {e}")
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
    finally:
        if conn and conn.is_connected():
            conn.close()


@order_mcp.tool(
    name="order_flight",
    description="预定飞机票。根据出发日期、航班号、舱位类型和数量完成预定，会扣减真实库存。"
)
def order_flight(departure_date: str, flight_number: str, seat_type: str, number: int) -> str:
    logger.info(f"预定飞机票: {departure_date}, {flight_number}, {seat_type}, {number}")
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
            return json.dumps({"status": "error", "message": f"未找到航班{flight_number} {departure_date} {seat_type}"}, ensure_ascii=False)

        result = _check_and_deduct("flight_tickets", "id", "remaining_seats", ticket["id"], number)
        if result["status"] == "error":
            return json.dumps(result, ensure_ascii=False)

        t = result["item"]
        return json.dumps({
            "status": "success",
            "message": f"预定成功！{t['departure_city']}到{t['arrival_city']} {t['departure_time']} 航班{flight_number} {seat_type} {number}张 票价{t['price']}元/张 总价{float(t['price'])*number:.2f}元"
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"飞机票预定失败: {e}")
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
    finally:
        if conn and conn.is_connected():
            conn.close()


@order_mcp.tool(
    name="order_concert",
    description="预定演出票。根据开始日期、艺人、场地、票类型和数量完成预定，会扣减真实库存。"
)
def order_concert(start_date: str, artist: str, venue: str, seat_type: str, number: int) -> str:
    logger.info(f"预定演出票: {start_date}, {artist}, {venue}, {seat_type}, {number}")
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
            return json.dumps({"status": "error", "message": f"未找到{artist}在{venue}的演出 {start_date} {seat_type}"}, ensure_ascii=False)

        result = _check_and_deduct("concert_tickets", "id", "remaining_seats", ticket["id"], number)
        if result["status"] == "error":
            return json.dumps(result, ensure_ascii=False)

        t = result["item"]
        return json.dumps({
            "status": "success",
            "message": f"预定成功！{artist} {t['start_time']} {venue} {seat_type} {number}张 票价{t['price']}元/张 总价{float(t['price'])*number:.2f}元"
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"演出票预定失败: {e}")
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
    finally:
        if conn and conn.is_connected():
            conn.close()


@order_mcp.tool(
    name="order_hotel",
    description="预定酒店房间。根据酒店名称、城市、房型和数量完成预定，会扣减真实库存。"
)
def order_hotel(hotel_name: str, city: str, room_type: str, number: int) -> str:
    logger.info(f"预定酒店: {hotel_name}, {city}, {room_type}, {number}")
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
            return json.dumps({"status": "error", "message": f"未找到{hotel_name} {room_type}"}, ensure_ascii=False)

        result = _check_and_deduct("hotel_rooms", "id", "remaining_rooms", room["id"], number)
        if result["status"] == "error":
            return json.dumps(result, ensure_ascii=False)

        r = result["item"]
        return json.dumps({
            "status": "success",
            "message": f"预定成功！{hotel_name}（{city}）{room_type} {number}间 每晚{r['price']}元 总价{float(r['price'])*number:.2f}元/晚"
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"酒店预定失败: {e}")
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
    finally:
        if conn and conn.is_connected():
            conn.close()


def create_order_mcp_server() -> None:
    logger.info("=== 票务预定MCP服务器信息 ===")
    logger.info(f"名称: {order_mcp.name}")
    logger.info(f"描述: {order_mcp.instructions}")

    try:
        logger.info("服务器已启动，请访问 http://127.0.0.1:8003/mcp")
        order_mcp.run(transport="streamable-http")
    except Exception as e:
        logger.error(f"服务器启动失败: {e}")


if __name__ == "__main__":
    create_order_mcp_server()
