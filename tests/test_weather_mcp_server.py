"""手动验证天气 MCP 参数化工具的脚本：python tests/test_weather_mcp_server.py"""
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from core.config import Config

conf = Config()


async def main() -> None:
    async with streamablehttp_client(conf.mcp_weather_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("query_weather", {
                "city": "北京",
                "start_date": "2026-09-01",
                "end_date": "2026-09-03",
            })
            print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
