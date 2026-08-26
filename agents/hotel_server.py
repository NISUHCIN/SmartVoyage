"""
hotel_server.py：酒店代理服务器，优先调用 RollingGo 真实接口，失败后参数化查询本地 MCP。
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import asyncio
import json
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
from utils.china_cities import detect_city
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
系统提示：你是酒店查询参数抽取器。从对话历史中提取城市、区域、房型、价格范围和最低评分。
输出严格 JSON：
{{"city": "北京", "district": "朝阳区", "room_type": "大床房", "price_min": 300, "price_max": 800, "rating_min": 4.5}}
- 没有明确提到的字段填空字符串或 null。
- 无法识别城市时输出 {{"status": "input_required", "message": "请提供城市，例如：北京的酒店"}}。
- 不要输出其他内容。

对话历史: {conversation}
当前日期: {current_date} (Asia/Shanghai)
    """
)


def _clean_json_output(output: str) -> str:
    import re
    return re.sub(r"^```json\s*|\s*```$", "", output.strip()).strip()


def _fallback_hotel_params(conversation: str) -> dict:
    city = detect_city(conversation)
    if not city:
        return {"status": "input_required", "message": "请提供城市，例如：北京的酒店"}
    return {"status": "ok", "city": city, "district": None, "room_type": None,
            "price_min": None, "price_max": None, "rating_min": None}


def _rollinggo_hotel_conf():
    cfg_path = Path(__file__).resolve().parent.parent / ".mcp.json"
    if not cfg_path.exists():
        return None
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        for conf_item in data.get("mcpServers", {}).values():
            if conf_item.get("url", "").rstrip("/") == "https://mcp.rollinggo.cn/mcp":
                return conf_item
    except Exception as e:
        logger.warning(f"读取 .mcp.json 失败: {e}")
    return None


async def search_rollinggo_hotels(conversation: str) -> str | None:
    """调用 RollingGo 酒店 MCP 搜索真实酒店，失败返回 None。"""
    mcp_conf = _rollinggo_hotel_conf()
    if not mcp_conf:
        return None
    city = detect_city(conversation)
    if not city:
        return None
    try:
        async with streamablehttp_client(mcp_conf["url"], headers=mcp_conf.get("headers", {})) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("searchHotels", {
                    "place": city,
                    "originQuery": conversation,
                })
                text = result.content[0].text
                data = json.loads(text)
                if not data.get("success"):
                    return None
                hotels = data.get("hotelInformationList", [])[:10]
                lines = []
                for hotel in hotels:
                    price = (hotel.get("price") or {}).get("lowestPrice")
                    price_text = f"{price}元/晚" if price else "价格待查"
                    lines.append(
                        f"{hotel.get('name', '')}（{city}）：{hotel.get('starRating', '')}星，"
                        f"{price_text}，地址：{hotel.get('address', '')}"
                    )
                return "\n".join(lines) if lines else None
    except Exception as e:
        logger.warning(f"RollingGo 酒店接口异常: {e}")
        return None


async def get_hotel(city: str, district: str = None, room_type: str = None,
                    price_min: float = None, price_max: float = None,
                    rating_min: float = None, request_id: str = None) -> str:
    headers = {"X-Request-ID": request_id} if request_id else None
    async with streamablehttp_client(conf.mcp_hotel_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("query_hotels", {
                "city": city,
                "district": district,
                "room_type": room_type,
                "price_min": price_min,
                "price_max": price_max,
                "rating_min": rating_min,
                "request_id": request_id or None,
            })
            return result.content[0].text


agent_card = AgentCard(
    name="HotelQueryAssistant",
    description="基于LangChain提供酒店查询服务的助手",
    url=conf.a2a_hotel_url,
    version="1.1.0",
    capabilities={"streaming": True, "memory": True},
    skills=[
        AgentSkill(
            name="execute hotel query",
            description="执行酒店查询，返回酒店房间信息，支持自然语言输入",
            examples=["北京的酒店", "上海500到1000元的酒店", "广州天河区的大床房"]
        )
    ]
)


class HotelQueryServer(A2AServer):
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
            city = str(data.get("city", "")).strip() or (detect_city(conversation) or "")
            if not city:
                return {"status": "input_required", "message": "请提供城市，例如：北京的酒店"}
            return {
                "status": "ok",
                "city": city,
                "district": data.get("district") or None,
                "room_type": data.get("room_type") or None,
                "price_min": data.get("price_min"),
                "price_max": data.get("price_max"),
                "rating_min": data.get("rating_min"),
            }
        except Exception:
            return _fallback_hotel_params(conversation)

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
        logger.info(f"[{request_id or '-'}] 酒店查询请求: {conversation}")

        try:
            rollinggo_text = asyncio.run(search_rollinggo_hotels(conversation))
            if rollinggo_text:
                rollinggo_text += "\n（数据来源：RollingGo 真实接口）"
                logger.info("酒店查询使用 RollingGo 真实接口结果")
                task.artifacts = [{"parts": [{"type": "text", "text": rollinggo_text}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
                return task
        except Exception as e:
            logger.warning(f"RollingGo 酒店查询失败，回退本地库: {e}")

        try:
            params = self.extract_params(conversation)
            if params.get("status") == "input_required":
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={"role": "agent", "content": {"text": params["message"]}}
                )
                return task

            hotel_result = asyncio.run(get_hotel(
                params["city"], params.get("district"), params.get("room_type"),
                params.get("price_min"), params.get("price_max"), params.get("rating_min"),
                request_id=request_id
            ))
            response = json.loads(hotel_result) if isinstance(hotel_result, str) else hotel_result
            logger.info(f"MCP 返回: {response}")

            if response.get("status") == "success":
                data = response.get("data", [])
                response_text = "\n".join([
                    f"{d['hotel_name']}（{d['city']}{d.get('district', '')}）：{d['room_type']}，"
                    f"{d.get('bed_type', '')}，每晚{d['price']}元，剩余{d['remaining_rooms']}间，"
                    f"评分{d['rating']}{'，含早' if d.get('has_breakfast') else ''}"
                    for d in data
                ])
                response_text += "\n（本地演示数据）"
                task.artifacts = [{"parts": [
                    {"type": "text", "text": response_text},
                    {"type": "text", "text": json.dumps(data, ensure_ascii=False)},
                ]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
            elif response.get("status") == "no_data":
                response_text = response.get("message", "请重新输入查询的城市。")
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
            logger.error(f"酒店查询失败: {str(e)}", exc_info=True)
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={"role": "agent", "content": {"text": f"查询失败: {str(e)} 请重试或提供更多细节。"}}
            )
            return task


if __name__ == "__main__":
    hotel_server = HotelQueryServer()
    logger.info("\n=== 服务器信息 ===")
    logger.info(f"名称: {hotel_server.agent_card.name}")
    logger.info(f"描述: {hotel_server.agent_card.description}")
    logger.info("\n技能:")
    for skill in hotel_server.agent_card.skills:
        logger.info(f"- {skill.name}: {skill.description}")
    run_server(hotel_server, host="127.0.0.1", port=conf.a2a_hotel_port)
