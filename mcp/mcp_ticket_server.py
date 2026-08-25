"""
mcp_ticket_server.py：票务查询 MCP 服务器，提供票务表的 SELECT 查询接口。
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


class TicketService:
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
                {"status": "success", "data": results} if results else {"status": "no_data", "message": "未找到票务数据，请确认查询条件。"},
                cls=DateEncoder, ensure_ascii=False)
        except Exception as e:
            logger.error(f"票务查询错误: {str(e)}")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
        finally:
            if conn and conn.is_connected():
                conn.close()


def create_ticket_mcp_server() -> None:
    ticket_mcp = FastMCP(
        name="TicketTools",
        instructions="票务查询工具，基于 train_tickets, flight_tickets, concert_tickets 表。只支持查询。",
        log_level="ERROR",
        host="127.0.0.1", port=8001)

    service = TicketService()

    @ticket_mcp.tool(
        name="query_tickets",
        description="查询票务数据，输入 SQL，如 'SELECT * FROM train_tickets WHERE departure_city = \"北京\" AND arrival_city = \"上海\"'"
    )
    def query_tickets(sql: str) -> str:
        logger.info(f"执行票务查询: {sql}")
        return service.execute_query(sql)

    logger.info("=== 票务MCP服务器信息 ===")
    logger.info(f"名称: {ticket_mcp.name}")
    logger.info(f"描述: {ticket_mcp.instructions}")

    try:
        logger.info("服务器已启动，请访问 http://127.0.0.1:8001/mcp")
        ticket_mcp.run(transport="streamable-http")
    except Exception as e:
        logger.error(f"服务器启动失败: {e}")


if __name__ == "__main__":
    create_ticket_mcp_server()
