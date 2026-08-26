"""
mcp_weather_server.py：天气查询 MCP 服务器，提供参数化查询接口。
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import mysql.connector
import json
from typing import Optional
from datetime import date, datetime, timedelta
from decimal import Decimal
from mcp.server.fastmcp import FastMCP
from core.config import Config
from core.create_logger import logger
from utils.format import DateEncoder, default_encoder
from utils.query_builders import build_weather_query

conf = Config()


class WeatherService:
    def __init__(self) -> None:
        self.conf = conf

    def query(self, city: str, start_date: Optional[str] = None, end_date: Optional[str] = None,
              request_id: Optional[str] = None) -> str:
        sql, params = build_weather_query(city, start_date, end_date)
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
            cursor.execute(sql, params)
            results = cursor.fetchall()
            cursor.close()
            for result in results:
                for key, value in result.items():
                    if isinstance(value, (date, datetime, timedelta, Decimal)):
                        result[key] = default_encoder(value)
            return json.dumps(
                {"status": "success", "data": results} if results
                else {"status": "no_data", "message": "未找到天气数据，请确认城市和日期。"},
                cls=DateEncoder, ensure_ascii=False)
        except Exception as e:
            logger.error(f"天气查询错误: {str(e)}")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
        finally:
            if conn and conn.is_connected():
                conn.close()


def create_weather_mcp_server(run: bool = True) -> FastMCP:
    weather_mcp = FastMCP(
        name="WeatherTools",
        instructions="天气查询工具，基于 weather_data 表，支持按城市和日期范围查询。",
        log_level="ERROR",
        host="127.0.0.1", port=conf.mcp_weather_port)

    service = WeatherService()

    @weather_mcp.tool(
        name="query_weather",
        description="查询天气数据。输入城市、起始日期和结束日期（YYYY-MM-DD）。"
    )
    def query_weather(city: str, start_date: Optional[str] = None, end_date: Optional[str] = None,
                      request_id: Optional[str] = None) -> str:
        return service.query(city, start_date, end_date, request_id)

    logger.info("=== 天气MCP服务器信息 ===")
    logger.info(f"名称: {weather_mcp.name}")
    logger.info(f"描述: {weather_mcp.instructions}")

    if run:
        try:
            logger.info(f"服务器已启动，请访问 http://127.0.0.1:{conf.mcp_weather_port}/mcp")
            weather_mcp.run(transport="streamable-http")
        except Exception as e:
            logger.error(f"服务器启动失败: {e}")
    return weather_mcp


if __name__ == "__main__":
    create_weather_mcp_server()
