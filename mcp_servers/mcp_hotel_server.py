"""
mcp_hotel_server.py：酒店查询 MCP 服务器，提供参数化查询接口。
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from mcp.server.fastmcp import FastMCP

from core.config import Config
from core.create_logger import logger
from utils.db import get_connection
from utils.format import DateEncoder, default_encoder
from utils.query_builders import build_hotel_query

conf = Config()


class HotelService:
    """酒店服务类，封装数据库查询逻辑"""

    def __init__(self) -> None:
        self.conf = conf

    def query(self, city: str, district: Optional[str] = None, room_type: Optional[str] = None,
              price_min: Optional[float] = None, price_max: Optional[float] = None,
              rating_min: Optional[float] = None, request_id: Optional[str] = None) -> str:
        sql, params = build_hotel_query(city, district, room_type, price_min, price_max, rating_min)
        logger.info(f"执行酒店查询: {params} rid={request_id or '-'}")
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
                else {"status": "no_data", "message": "未找到酒店数据，请确认查询条件。"},
                cls=DateEncoder, ensure_ascii=False)
        except Exception as e:
            logger.error(f"酒店查询错误: {str(e)}")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
        finally:
            if conn and conn.is_connected():
                conn.close()


def create_hotel_mcp_server(run: bool = True) -> FastMCP:
    hotel_mcp = FastMCP(
        name="HotelTools",
        instructions="酒店查询工具，基于 hotel_rooms 表，支持城市、区域、房型、价格和评分筛选。",
        log_level="ERROR",
        host="127.0.0.1", port=conf.mcp_hotel_port)

    service = HotelService()

    @hotel_mcp.tool(
        name="query_hotels",
        description="查询酒店数据。输入城市，可选区域、房型、最低价、最高价、最低评分。"
    )
    def query_hotels(city: str, district: Optional[str] = None, room_type: Optional[str] = None,
                     price_min: Optional[float] = None, price_max: Optional[float] = None,
                     rating_min: Optional[float] = None, request_id: Optional[str] = None) -> str:
        return service.query(city, district, room_type, price_min, price_max, rating_min, request_id)

    logger.info("=== 酒店MCP服务器信息 ===")
    logger.info(f"名称: {hotel_mcp.name}")
    logger.info(f"描述: {hotel_mcp.instructions}")

    if run:
        try:
            logger.info(f"服务器已启动，请访问 http://127.0.0.1:{conf.mcp_hotel_port}/mcp")
            hotel_mcp.run(transport="streamable-http")
        except Exception as e:
            logger.error(f"服务器启动失败: {e}")
    return hotel_mcp


if __name__ == "__main__":
    create_hotel_mcp_server()
