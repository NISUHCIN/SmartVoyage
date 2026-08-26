"""
mcp_ticket_server.py：票务查询 MCP 服务器，提供参数化查询接口。
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import json
from typing import Optional
from datetime import date, datetime, timedelta
from decimal import Decimal
from mcp.server.fastmcp import FastMCP
from core.config import Config
from core.create_logger import logger
from utils.format import DateEncoder, default_encoder
from utils.query_builders import (
    build_train_query,
    build_flight_query,
    build_concert_query,
)
from utils.db import get_connection

conf = Config()


class TicketService:
    def __init__(self) -> None:
        self.conf = conf

    def _execute(self, sql: str, params: list) -> str:
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params)
            results = cursor.fetchall()
            cursor.close()
            for result in results:
                for key, value in result.items():
                    if isinstance(value, (date, datetime, timedelta, Decimal)):
                        result[key] = default_encoder(value)
            return json.dumps(
                {"status": "success", "data": results} if results
                else {"status": "no_data", "message": "未找到票务数据，请确认查询条件。"},
                cls=DateEncoder, ensure_ascii=False)
        except Exception as e:
            logger.error(f"票务查询错误: {str(e)}")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
        finally:
            if conn and conn.is_connected():
                conn.close()

    def query_train(self, departure_city: str, arrival_city: str, travel_date: str,
                    seat_type: Optional[str] = None, request_id: Optional[str] = None) -> str:
        sql, params = build_train_query(departure_city, arrival_city, travel_date, seat_type)
        logger.info(f"执行火车票查询: {params} rid={request_id or '-'}")
        return self._execute(sql, params)

    def query_flight(self, departure_city: str, arrival_city: str, travel_date: str,
                     cabin_type: Optional[str] = None, request_id: Optional[str] = None) -> str:
        sql, params = build_flight_query(departure_city, arrival_city, travel_date, cabin_type)
        logger.info(f"执行机票查询: {params} rid={request_id or '-'}")
        return self._execute(sql, params)

    def query_concert(self, city: str, artist: str = None, start_date: str = None,
                      ticket_type: Optional[str] = None, request_id: Optional[str] = None) -> str:
        sql, params = build_concert_query(city, artist, start_date, ticket_type)
        logger.info(f"执行演出票查询: {params} rid={request_id or '-'}")
        return self._execute(sql, params)

def create_ticket_mcp_server(run: bool = True) -> FastMCP:
    ticket_mcp = FastMCP(
        name="TicketTools",
        instructions="票务查询工具，支持火车票/机票/演出票参数化查询。",
        log_level="ERROR",
        host="127.0.0.1", port=conf.mcp_ticket_port)

    service = TicketService()

    @ticket_mcp.tool(
        name="query_train",
        description="查询火车票。输入出发城市、到达城市、日期，可选座位类型（二等座/一等座/硬卧/软卧等）。"
    )
    def query_train(departure_city: str, arrival_city: str, travel_date: str,
                    seat_type: Optional[str] = None, request_id: Optional[str] = None) -> str:
        return service.query_train(departure_city, arrival_city, travel_date, seat_type, request_id)

    @ticket_mcp.tool(
        name="query_flight",
        description="查询机票。输入出发城市、到达城市、日期，可选舱位类型。"
    )
    def query_flight(departure_city: str, arrival_city: str, travel_date: str,
                     cabin_type: Optional[str] = None, request_id: Optional[str] = None) -> str:
        return service.query_flight(departure_city, arrival_city, travel_date, cabin_type, request_id)

    @ticket_mcp.tool(
        name="query_concert",
        description="查询演出票。输入城市，可选艺人、日期、票类型。"
    )
    def query_concert(city: str, artist: str = None, start_date: str = None,
                      ticket_type: Optional[str] = None, request_id: Optional[str] = None) -> str:
        return service.query_concert(city, artist, start_date, ticket_type, request_id)

    logger.info("=== 票务MCP服务器信息 ===")
    logger.info(f"名称: {ticket_mcp.name}")
    logger.info(f"描述: {ticket_mcp.instructions}")

    if run:
        try:
            logger.info(f"服务器已启动，请访问 http://127.0.0.1:{conf.mcp_ticket_port}/mcp")
            ticket_mcp.run(transport="streamable-http")
        except Exception as e:
            logger.error(f"服务器启动失败: {e}")
    return ticket_mcp


if __name__ == "__main__":
    create_ticket_mcp_server()
