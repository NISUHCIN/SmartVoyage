import logging

import asyncio
import json

from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
logger = logging.getLogger(__name__)

# 定义服务器地址
server_url = "http://127.0.0.1:8002/mcp"

async def test_weather_mcp() -> None:
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

                    # 测试1: 查询指定日期天气
                    sql = "SELECT * FROM weather_data WHERE city = '北京' AND fx_date = '2025-12-24'"
                    result = await session.call_tool("query_weather", {"sql": sql})
                    result_data = json.loads(result) if isinstance(result, str) else result
                    logger.info(f"指定日期天气结果：{result_data}")

                    # 测试2: 查询未来3天天气
                    sql_range = "SELECT * FROM weather_data WHERE city = '北京' AND fx_date BETWEEN '2025-12-24' AND '2025-12-27'"
                    result_range = await session.call_tool("query_weather", {"sql": sql_range})
                    result_range_data = json.loads(result_range) if isinstance(result_range, str) else result_range
                    logger.info(f"天气范围查询结果：{result_range_data}")
                except Exception as e:
                    logger.info(f"天气 MCP 测试出错：{str(e)}")
    except Exception as e:
        logger.info(f"连接或会话初始化时发生错误: {e}")
        logger.info("请确认服务端脚本已启动并运行在 http://127.0.0.1:8002/mcp")

if __name__ == "__main__":
    asyncio.run(test_weather_mcp())