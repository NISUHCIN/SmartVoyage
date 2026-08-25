import logging

import asyncio
import json

from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
logger = logging.getLogger(__name__)

# 定义服务器地址
server_url = "http://127.0.0.1:8001/mcp"

async def test_ticket_mcp() -> None:
    try:
        # 启动 MCP server，通过streamable建立连接
        async with streamablehttp_client(server_url) as (read, write, _):
            # 使用读写通道创建 MCP 会话
            async with ClientSession(read, write) as session:
                try:
                    await session.initialize()
                    logger.info("会话初始化成功，可以开始调用工具。")

                    # 从 session 自动获取 MCP server 提供的工具列表。
                    tools = await load_mcp_tools(session)
                    logger.info(f"tools-->{tools}")

                    # 调用远程工具
                    # 测试1: 查询机票
                    sql_flights = "SELECT * FROM flight_tickets WHERE departure_city = '上海' AND arrival_city = '北京' AND DATE(departure_time) = '2025-12-17' AND cabin_type = '公务舱'"
                    result_flights = await session.call_tool("query_tickets", {"sql": sql_flights})
                    result_flights_data = json.loads(result_flights) if isinstance(result_flights, str) else result_flights
                    logger.info(f"机票查询结果：{result_flights_data}")

                    # 测试2: 查询火车票
                    sql_trains = "SELECT * FROM train_tickets WHERE departure_city = '北京' AND arrival_city = '上海' AND DATE(departure_time) = '2025-12-18' AND seat_type = '二等座'"
                    result_trains = await session.call_tool("query_tickets", {"sql": sql_trains})
                    result_trains_data = json.loads(result_trains) if isinstance(result_trains, str) else result_trains
                    logger.info(f"火车票查询结果：{result_trains_data}")

                    # 测试3: 查询演唱会票
                    sql_concerts = "SELECT * FROM concert_tickets WHERE city = '上海' AND artist = '刀郎' AND DATE(start_time) = '2026-01-11' AND ticket_type = '内场'"
                    result_concerts = await session.call_tool("query_tickets", {"sql": sql_concerts})
                    result_concerts_data = json.loads(result_concerts) if isinstance(result_concerts, str) else result_concerts
                    logger.info(f"演唱会票查询结果：{result_concerts_data}")
                except Exception as e:
                    logger.info(f"票务 MCP 测试出错：{str(e)}")
    except Exception as e:
        logger.info(f"连接或会话初始化时发生错误: {e}")
        logger.info("请确认服务端脚本已启动并运行在 http://127.0.0.1:8001/mcp")


if __name__ == "__main__":
    asyncio.run(test_ticket_mcp())