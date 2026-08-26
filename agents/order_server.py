"""
order_server.py：
    订票代理服务器，首先根据用户的意图去调用票务Agent服务器查询余票信息，然后进行调用订票MCP服务器完成订票。
    作用：对用户的订票需求进行分析，先调用票务Agent服务器查询余票信息，如果有余票则完成订票，否则让用户修改需求。
    项目中的定位：执行层，接收路由任务，查询余票并完成订票。
核心功能：
    根据用户的意图去调用票务Agent服务器查询余票信息。
    根据余票信息调用订票MCP服务器完成订票。
"""
import sys
from pathlib import Path

# 将项目根目录添加到模块搜索路径
sys.path.append(str(Path(__file__).parent.parent))


from typing import Any
import asyncio
import uuid

from langchain_openai import ChatOpenAI
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from python_a2a import AgentCard, AgentSkill, run_server, TaskStatus, TaskState, A2AServer, A2AClient, Message, \
    TextContent, MessageRole, Task
from core.create_logger import logger
from core.config import Config
from utils.mock_travel_provider import create_ticket_order, extract_route
from utils.request_id import extract_request_id, strip_request_prefix
from utils.streaming import chunk_text

conf = Config()

# 初始化LLM
llm = ChatOpenAI(
    model=conf.fast_model_name,
    base_url=conf.base_url,
    api_key=conf.api_key,
    temperature=0.1,
    extra_body={"enable_thinking": False}
)

# 定义订票函数
async def order_tickets(query: Any) -> Any:
    try:
        # 启动 MCP server，通过streamable建立连接
        rid = extract_request_id(str(query))
        headers = {"X-Request-ID": rid} if rid else None
        async with streamablehttp_client(conf.mcp_order_url, headers=headers) as (read, write, _):
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
                    return {"status": "success", "message": f"{response['output']}"}
                except Exception as e:
                    logger.error(f"票务 MCP 测试出错：{str(e)}")
                    return {"status": "error", "message": f"票务 MCP 查询出错：{str(e)}"}
    except Exception as e:
        logger.error(f"连接或会话初始化时发生错误: {e}")
        return {"status": "error", "message": "连接或会话初始化时发生错误"}

# Agent 卡片定义
agent_card = AgentCard(
    name="TicketOrderAssistant",
    description="通过MCP提供票务预定服务的助手",
    url=conf.a2a_order_url,
    version="1.0.4",
    capabilities={"streaming": True, "memory": True},
    skills=[
        AgentSkill(
            name="execute ticket order",
            description="根据客户端提供的输入执行票务预定，返回执行结果",
            examples=["北京 到 上海 2025-11-15 火车票 二等座 1张",
                      "上海 到 北京 2025-12-11 飞机票 公务舱 2张"]
        )
    ]
)

# 票务预定服务器类
class TicketOrderServer(A2AServer):
    def __init__(self) -> None:
        super().__init__(agent_card=agent_card)
        self.llm = llm
        self.ticket_client = A2AClient(conf.a2a_ticket_url, timeout=90)

    async def stream_response(self, message: Any) -> Any:
        """A2A 流式响应：复用 handle_task，分块返回文本。"""
        msg = message if isinstance(message, Message) else Message.from_dict(message)
        task = Task(id="stream-" + str(uuid.uuid4().hex), message=msg.to_dict())
        result = await asyncio.to_thread(self.handle_task, task)
        text = ""
        try:
            if result.artifacts:
                artifact = result.artifacts[0]
                parts = artifact["parts"] if isinstance(artifact, dict) else artifact.parts
                if parts:
                    part = parts[0]
                    text = part["text"] if isinstance(part, dict) else part.text
        except Exception:
            text = ""
        for piece in chunk_text(text or "暂不可用"):
            yield piece

    # 处理任务：提取输入，查询余票，调用MCP，结果输出
    def handle_task(self, task: Any) -> Any:
        # 1 提取输入
        content = (task.message or {}).get("content", {})  # 从消息中获取内容
        # 提取conversation，即客户端发起的任务中的query语句
        conversation = content.get("text", "") if isinstance(content, dict) else ""
        request_id = extract_request_id(conversation)
        conversation = strip_request_prefix(conversation)
        logger.info(f"[{request_id or '-'}] 对话历史及用户问题: {conversation}")

        if "机票" in conversation or "飞机" in conversation:
            task.artifacts = [{"parts": [{"type": "text", "text": "当前版本仅支持火车/高铁票预订，暂不支持机票预订。"}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)
            return task

        try:
            # 2 调用票务查询agent查询余票
            message_ticket = Message(content=TextContent(text=conversation), role=MessageRole.USER)
            task_ticket = Task(id="task-" + str(uuid.uuid4()), message=message_ticket.to_dict())

            # 发送任务并获取最终结果
            ticket_client = A2AClient(
                conf.a2a_ticket_url, timeout=90,
                headers={"X-Request-ID": request_id} if request_id else None
            )
            ticket_result_task = asyncio.run(ticket_client.send_task_async(task_ticket))
            logger.info(f"原始响应: {ticket_result_task}")

            # 处理结果：未查到余票信息时，则返回提示信息
            if ticket_result_task.status.state != 'completed':
                required_message = ticket_result_task.status.message['content']['text']
                logger.info(f'余票未查到：{required_message}')
                task.status = TaskStatus(state=TaskState.INPUT_REQUIRED,
                                         message={"role": "agent", "content": {"text": required_message}})
                return task
            # 处理结果：查到余票信息时，进行订票
            ticket_result = ticket_result_task.artifacts[0]["parts"][0]["text"]
            logger.info(f"余票信息: {ticket_result}")

            # 3 调用MCP订票
            order_result = asyncio.run(order_tickets(conversation + '\n余票信息：' + ticket_result))
            logger.info(f"MCP 返回: {order_result}")

            # 4 结果输出
            data = order_result.get("message", '')
            logger.info(f"订票结果: {data}")
            # 检查响应状态
            if order_result.get("status") == "success":
                result = '余票信息：' + ticket_result + '\n订票结果：' + data
                # 设置任务产物为文本部分，并设置任务状态为完成
                task.artifacts = [{"parts": [{"type": "text", "text": result}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
            else:
                route = extract_route(conversation)
                if route:
                    mock_msg = create_ticket_order(route[0], route[1], route[2], "模拟班次")
                    task.artifacts = [{"parts": [{"type": "text", "text": mock_msg}]}]
                    task.status = TaskStatus(state=TaskState.COMPLETED)
                    return task
                # 设置任务状态为失败，添加错误信息
                task.status = TaskStatus(state=TaskState.FAILED,
                                         message={"role": "agent", "content": {"text": data}})
            return task
        except Exception as e:  # 捕获异常
            logger.error(f"查询失败: {str(e)}")

            # 设置任务状态为失败，添加错误信息
            task.status = TaskStatus(state=TaskState.FAILED,
                                     message={"role": "agent", "content": {"text": f"查询失败: {str(e)} 请重试或提供更多细节。"}})
            return task

if __name__ == "__main__":
    # 创建并运行服务器
    # 实例化票务查询服务器
    ticket_server = TicketOrderServer()
    # 打印服务器信息
    logger.info("\n=== 服务器信息 ===")
    logger.info(f"名称: {ticket_server.agent_card.name}")
    logger.info(f"描述: {ticket_server.agent_card.description}")
    logger.info("\n技能:")
    for skill in ticket_server.agent_card.skills:
        logger.info(f"- {skill.name}: {skill.description}")
    # 运行服务器
    run_server(ticket_server, host="127.0.0.1", port=conf.a2a_order_port)
