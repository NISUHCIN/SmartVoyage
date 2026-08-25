"""
mcp_hotel_server.py：酒店查询 MCP 服务器，提供 hotel_rooms 表的 SELECT 查询接口。

核心功能：
    初始化 MySQL 数据库连接。
    执行 SELECT 查询，返回 JSON 格式结果。
    通过 FastMCP 提供工具，响应 MCP 工具调用。
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import mysql.connector
import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from mcp.server.fastmcp import FastMCP
from core.config import Config
from core.create_logger import logger
from utils.format import DateEncoder, default_encoder
from utils.sql_safety import validate_select_sql

conf = Config()


class HotelService:
    """酒店服务类，封装数据库操作逻辑"""

    def __init__(self) -> None:
        self.conf = conf

    def execute_query(self, sql: str) -> str:
        is_safe, reason = validate_select_sql(sql)
        if not is_safe:
            logger.warning(f"SQL 安全校验未通过: {reason}, SQL: {sql}")
            return json.dumps({"status": "error", "message": f"SQL 安全校验未通过: {reason}"}, ensure_ascii=False)

        conn = None
        try:
            conn = mysql.connector.connect(
                host=self.conf.host,
                user=self.conf.user,
                password=self.conf.password,
                database=self.conf.database,
                port=self.conf.db_port
            )
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql)
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


def create_hotel_mcp_server() -> None:
    hotel_mcp = FastMCP(
        name="HotelTools",
        instructions="酒店查询工具，基于 hotel_rooms 表。只支持查询。",
        log_level="ERROR",
        host="127.0.0.1", port=8004)

    service = HotelService()

    @hotel_mcp.tool(
        name="query_hotels",
        description="查询酒店数据，输入 SQL，如 'SELECT * FROM hotel_rooms WHERE city = \"北京\"'"
    )
    def query_hotels(sql: str) -> str:
        logger.info(f"执行酒店查询: {sql}")
        return service.execute_query(sql)

    logger.info("=== 酒店MCP服务器信息 ===")
    logger.info(f"名称: {hotel_mcp.name}")
    logger.info(f"描述: {hotel_mcp.instructions}")

    try:
        logger.info("服务器已启动，请访问 http://127.0.0.1:8004/mcp")
        hotel_mcp.run(transport="streamable-http")
    except Exception as e:
        logger.error(f"服务器启动失败: {e}")


if __name__ == "__main__":
    create_hotel_mcp_server()
