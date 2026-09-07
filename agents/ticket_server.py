"""
ticket_server.py：票务代理服务器，从自然语言提取参数后调用 MCP 票务工具。
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import Any

import pytz
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from python_a2a import (
    A2AServer,
    AgentCard,
    AgentSkill,
    Message,
    Task,
    TaskState,
    TaskStatus,
    run_server,
)

from core.config import Config
from core.create_logger import logger
from utils.mock_travel_provider import extract_route, format_train_rows, query_trains
from utils.redact import redact_sensitive
from utils.request_id import extract_request_id, strip_request_prefix
from utils.streaming import chunk_text

conf = Config()

llm = ChatOpenAI(
    model=conf.fast_model_name,
    base_url=conf.base_url,
    api_key=conf.api_key,
    temperature=0.1,
    extra_body={"enable_thinking": False}
)

params_prompt = ChatPromptTemplate.from_template(
    """
系统提示：你是票务查询参数抽取器，支持火车/高铁票查询。
从对话历史中提取：出发城市、到达城市、日期（YYYY-MM-DD）、座位类型（可选）。
输出严格 JSON：
{{"type": "train", "departure_city": "北京", "arrival_city": "上海", "date": "2026-09-01", "seat_type": "二等座"}}
- 信息不足时输出 {{"status": "input_required", "message": "请提供出发地、目的地和日期，例如：北京到上海 2026-09-01 二等座"}}。
- 不要输出其他内容。

对话历史: {conversation}
当前日期: {current_date} (Asia/Shanghai)
    """
)


def _clean_json_output(output: str) -> str:
    return re.sub(r"^```json\s*|\s*```$", "", output.strip()).strip()


def _fallback_params(conversation: str) -> dict:
    route = extract_route(conversation)
    if route:
        seat_match = re.search(r"(一等座|二等座|硬卧|软卧|硬座|商务座|卧铺|无座)", conversation)
        return {
            "status": "ok",
            "type": "train",
            "departure_city": route[0],
            "arrival_city": route[1],
            "date": route[2],
            "seat_type": seat_match.group(1) if seat_match else "",
        }
    return {"status": "input_required", "message": "请提供出发地、目的地和日期，例如：北京到上海 2026-09-01"}


async def get_ticket_info(departure_city: str, arrival_city: str, travel_date: str,
                          seat_type: str = None, request_id: str = None) -> str:
    headers = {"X-Request-ID": request_id} if request_id else None
    async with streamablehttp_client(conf.mcp_ticket_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("query_train", {
                "departure_city": departure_city,
                "arrival_city": arrival_city,
                "travel_date": travel_date,
                "seat_type": seat_type or None,
                "request_id": request_id or None,
            })
            return result.content[0].text


agent_card = AgentCard(
    name="TicketQueryAssistant",
    description="基于 LangChain 提供票务查询服务的助手",
    url=conf.a2a_ticket_url,
    version="1.1.0",
    capabilities={"streaming": True, "memory": True},
    skills=[
        AgentSkill(
            name="execute ticket query",
            description="根据客户端提供的输入执行票务查询，返回数据库结果，支持自然语言输入",
            examples=["火车票 北京 上海 2026-09-01 二等座", "北京到上海的高铁"]
        )
    ]
)


class TicketQueryServer(A2AServer):
    def __init__(self) -> None:
        super().__init__(agent_card=agent_card)
        self.llm = llm
        self.params_prompt = params_prompt

    def extract_params(self, conversation: str) -> dict:
        current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
        try:
            output = _clean_json_output(
                (self.params_prompt | self.llm).invoke(
                    {"conversation": conversation, "current_date": current_date}
                ).content
            )
            data = json.loads(output)
            if data.get("status") == "input_required":
                return data
            departure = str(data.get("departure_city", "")).strip()
            arrival = str(data.get("arrival_city", "")).strip()
            travel_date = str(data.get("date", "")).strip()
            if departure and arrival and travel_date:
                return {
                    "status": "ok",
                    "type": str(data.get("type", "train")),
                    "departure_city": departure,
                    "arrival_city": arrival,
                    "date": travel_date,
                    "seat_type": str(data.get("seat_type", "")).strip(),
                }
            return {"status": "input_required", "message": "请提供出发地、目的地和日期，例如：北京到上海 2026-09-01"}
        except Exception:
            return _fallback_params(conversation)

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

    def handle_task(self, task: Any) -> Any:
        content = (task.message or {}).get("content", {})
        conversation = content.get("text", "") if isinstance(content, dict) else ""
        request_id = extract_request_id(conversation)
        conversation = strip_request_prefix(conversation)
        logger.info(f"[{request_id or '-'}] 票务查询请求: {redact_sensitive(conversation)}")

        try:
            params = self.extract_params(conversation)
            if params.get("status") == "input_required":
                route = extract_route(conversation)
                if route:
                    mock_text = format_train_rows(query_trains(route[0], route[1], route[2]))
                    mock_text += "\n（演示数据，非实时票务）"
                    logger.info("参数不完整，使用模拟火车/高铁工具兜底")
                    task.artifacts = [{"parts": [{"type": "text", "text": mock_text}]}]
                    task.status = TaskStatus(state=TaskState.COMPLETED)
                    return task
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={"role": "agent", "content": {"text": params["message"]}}
                )
                return task

            if params.get("type") != "train":
                task.artifacts = [{"parts": [{"type": "text", "text": "当前版本仅支持火车/高铁票查询与预订，暂不支持机票。"}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
                return task

            ticket_result = asyncio.run(get_ticket_info(
                params["departure_city"],
                params["arrival_city"],
                params["date"],
                params.get("seat_type") or None,
                request_id=request_id,
            ))
            response = json.loads(ticket_result) if isinstance(ticket_result, str) else ticket_result
            logger.info(f"MCP 返回: {response}")

            route = extract_route(conversation)
            live_source = response.get("source")
            is_live = live_source in ("aliyun", "jisu")
            if response.get("status") in ("no_data", "error") and route and not is_live:
                mock_rows = query_trains(route[0], route[1], route[2])
                mock_text = format_train_rows(mock_rows)
                mock_text += "\n（演示数据，非实时票务）"
                logger.info("本地票务无数据，使用模拟火车/高铁工具")
                task.artifacts = [{"parts": [{"type": "text", "text": mock_text}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
                return task

            if response.get("status") == "success":
                response_text = format_train_rows(response.get("data", []))
                if live_source == "jisu":
                    source_note = "\n（数据来源：极速数据/阿里云 真实余票接口）"
                elif is_live:
                    source_note = "\n（数据来源：聚美智数/阿里云 真实余票接口）"
                else:
                    source_note = "\n（本地演示数据）"
                response_text += source_note
                task.artifacts = [{"parts": [
                    {"type": "text", "text": response_text},
                    {"type": "text", "text": json.dumps(response.get("data", []), ensure_ascii=False)},
                ]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
            elif response.get("status") == "no_data":
                response_text = response.get("message", "未找到票务数据，请确认查询条件。")
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={"role": "agent", "content": {"text": response_text}}
                )
            else:
                response_text = response.get("message", "查询失败，请重试或提供更多细节。")
                task.status = TaskStatus(
                    state=TaskState.FAILED,
                    message={"role": "agent", "content": {"text": response_text}}
                )
            return task
        except Exception as e:
            logger.error(f"票务查询失败: {str(e)}", exc_info=True)
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={"role": "agent", "content": {"text": f"查询失败: {str(e)} 请重试或提供更多细节。"}}
            )
            return task


if __name__ == "__main__":
    ticket_server = TicketQueryServer()
    logger.info("\n=== 服务器信息 ===")
    logger.info(f"名称: {ticket_server.agent_card.name}")
    logger.info(f"描述: {ticket_server.agent_card.description}")
    logger.info("\n技能:")
    for skill in ticket_server.agent_card.skills:
        logger.info(f"- {skill.name}: {skill.description}")
    run_server(ticket_server, host="127.0.0.1", port=conf.a2a_ticket_port)
