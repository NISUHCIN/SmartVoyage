from typing import Any
import asyncio

from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_openai import ChatOpenAI
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from core.config import Config
from core.create_logger import logger

conf = Config()

# 初始化LLM
llm = ChatOpenAI(
    model=conf.model_name,
    base_url=conf.base_url,
    api_key=conf.api_key,
    temperature=0.1
)


async def order_tickets(query: Any) -> Any:
    try:
        # 启动 MCP server，通过streamable建立连接
        async with streamablehttp_client("http://127.0.0.1:8003/mcp") as (read, write, _):
            # 使用读写通道创建 MCP 会话
            async with ClientSession(read, write) as session:
                try:
                    await session.initialize()

                    # 从 session 自动获取 MCP server 提供的工具列表。
                    tools = await load_mcp_tools(session)
                    # print(f"tools-->{tools}")

                    # 创建 agent 的提示模板
                    prompt = ChatPromptTemplate.from_messages([
                        ("system",
                         "你是一个票务预定助手，能够调用工具来完成火车票、飞机票或演出票的预定。你需要仔细分析工具需要的参数，然后从用户提供的信息中提取信息。如果用户提供的信息不足以提取到调用工具所有必要参数，则向用户追问，以获取该信息。不能自己编撰参数。"),
                        ("human", "{input}"),
                        ("placeholder", "{agent_scratchpad}"),
                    ])

                    # 构建工具调用代理
                    agent = create_tool_calling_agent(llm, tools, prompt)

                    # 创建代理执行器
                    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

                    # 代理调用
                    response = await agent_executor.ainvoke({"input": query})

                    return response['output']
                except Exception as e:
                    logger.info(f"票务 MCP 测试出错：{str(e)}")
                    return f"票务 MCP 查询出错：{str(e)}"
    except Exception as e:
        logger.error(f"连接或会话初始化时发生错误: {e}")
        return "连接或会话初始化时发生错误"


if __name__ == "__main__":
    while True:
        query = input("请输入查询：")
        if query == "exit":
            break
        logger.info(asyncio.run(order_tickets(query)))
