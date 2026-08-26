"""chat_service.py：把 main.py 的意图识别与 A2A 多 Agent 编排抽成可复用服务。

供 FastAPI 的 /api/chat 接口调用，浏览器端无需直接接触 A2A 协议。
"""

import asyncio
import json
import re
import threading
import time
import uuid
from typing import Any
from datetime import datetime

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytz
from langchain_openai import ChatOpenAI
from python_a2a import A2AClient, AgentNetwork, Message, TextContent, MessageRole, Task

from core.config import Config
from core.create_logger import logger
from core.main_prompts import SmartVoyagePrompts
from backend.auth import load_session_messages, save_message, session_exists
from utils.redact import redact_sensitive


_service_conf = Config()
AGENT_URLS = {
    "WeatherQueryAssistant": _service_conf.a2a_weather_url,
    "TicketQueryAssistant": _service_conf.a2a_ticket_url,
    "TicketOrderAssistant": _service_conf.a2a_order_url,
    "HotelQueryAssistant": _service_conf.a2a_hotel_url,
    "ItineraryPlannerAssistant": _service_conf.a2a_itinerary_url,
}

AGENT_TIMEOUT = 90
MAX_HISTORY_LINES = 60


def _trim_history(text: str, max_lines: int = MAX_HISTORY_LINES) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])


def _db_history_text(session_id: str) -> str:
    """把数据库里的会话消息转成与内存历史一致的文本。"""
    rows = load_session_messages(session_id)
    lines = []
    for row in rows:
        role = "User" if row.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {row.get('content', '')}")
    return _trim_history("\n".join(lines))


def _chunk_text(text: str, size: int = 24) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


def _extract_chunk_text(chunk: Any) -> str:
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            parts.append(block.get("text", "") if isinstance(block, dict) else str(block))
        return "".join(parts)
    return str(content or "")


def _parse_agent_reply(raw_response: Any) -> str:
    if raw_response.status.state == "completed":
        try:
            artifact = raw_response.artifacts[0]
            parts = artifact["parts"] if isinstance(artifact, dict) else artifact.parts
            part = parts[0]
            return part["text"] if isinstance(part, dict) else part.text
        except Exception:
            return "代理返回数据解析失败"
    msg_raw = raw_response.status.message
    if isinstance(msg_raw, dict) and "content" in msg_raw and isinstance(msg_raw["content"], dict):
        return msg_raw["content"]["text"]
    if isinstance(msg_raw, dict) and "error" in msg_raw:
        return f"代理执行失败：{msg_raw['error']}"
    return str(msg_raw) or "代理返回空结果，请稍后重试。"


INTENT_AGENT_MAP = {
    "weather": "WeatherQueryAssistant",
    "flight": "TicketQueryAssistant",
    "train": "TicketQueryAssistant",
    "concert": "TicketQueryAssistant",
    "order": "TicketOrderAssistant",
    "hotel": "HotelQueryAssistant",
    "itinerary": "ItineraryPlannerAssistant",
}

# The itinerary agent already gathers weather, tickets, hotels and attractions,
# so routing those intents separately would duplicate the same information.
ITINERARY_COVERED_INTENTS = {"weather", "train", "flight", "hotel", "attraction"}


def collapse_redundant_intents(intents: list[str]) -> list[str]:
    """Keep itinerary routing exclusive when a trip plan is requested."""
    if not intents or "itinerary" not in intents:
        return intents
    return [intent for intent in intents if intent not in ITINERARY_COVERED_INTENTS]


def _looks_like_itinerary(query: str) -> bool:
    """LLM 意图识别不稳定时的规则兜底：行程/攻略/多日游类请求直接路由到行程 Agent。"""
    text = query or ""
    if any(k in text for k in ("游", "行程", "攻略", "安排", "几日", "日游", "天游", "周末")):
        return True
    try:
        from utils.mock_travel_provider import extract_route
        return extract_route(text) is not None
    except Exception:
        return False


def _invoke_with_retry(chain, inputs, retries=3):
    """LLM 调用自动重试，避免 DashScope 网络抖动导致对话失败。"""
    last_error = None
    for attempt in range(retries):
        try:
            return chain.invoke(inputs)
        except Exception as e:
            last_error = e
            logger.warning(f"LLM 调用失败，重试 {attempt + 1}/{retries}: {e}")
            time.sleep(1)
    raise last_error


class SmartVoyageChatService:
    """按 session 维护对话历史的旅行助手服务。"""

    def __init__(self) -> None:
        self.conf = Config()
        self.llm = ChatOpenAI(
            model=self.conf.fast_model_name,
            api_key=self.conf.api_key,
            base_url=self.conf.base_url,
            temperature=0.1,
            extra_body={"enable_thinking": False},
        )
        self.agent_network = AgentNetwork(name="SmartVoyage Travel Assistant Network")
        for name, url in AGENT_URLS.items():
            self.agent_network.add(name, A2AClient(url, timeout=AGENT_TIMEOUT))
        self._session_history: dict[str, str] = {}
        self._lock = threading.Lock()

    def _history(self, session_id: str) -> str:
        return self._session_history.get(session_id, "")

    def reset_session(self, session_id: str = "default") -> None:
        with self._lock:
            self._session_history[session_id] = ""

    def _intent_agent(self, user_input: str, session_id: str, history: str = None):
        chain = SmartVoyagePrompts.intent_prompt() | self.llm
        current_date = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d")
        if history is None:
            history = self._history(session_id)
        intent_response = _invoke_with_retry(
            chain,
            {
                "conversation_history": "\n".join(history.split("\n")[-6:]),
                "query": user_input,
                "current_date": current_date,
            }
        ).content.strip()
        logger.info(f"意图识别原始响应: {intent_response}")
        intent_response = re.sub(r"^```json\s*|\s*```$", "", intent_response).strip()
        intent_output = json.loads(intent_response)
        intents = intent_output.get("intents", [])
        user_queries = intent_output.get("user_queries", {})
        follow_up_message = intent_output.get("follow_up_message", "")
        if (not intents or "out_of_scope" in intents) and _looks_like_itinerary(user_input):
            logger.info("意图识别兜底：判定为 itinerary")
            intents = ["itinerary"]
            user_queries = {"itinerary": user_input}
            follow_up_message = ""
        logger.info(f"intents: {intents}||user_queries: {user_queries}||follow_up_message: {follow_up_message}")
        return intents, user_queries, follow_up_message

    def process(self, user_input: str, session_id: str = "default",
                user_id: int = None, request_id: str = "") -> str:
        """处理一条用户消息，返回助手回复文本；登录用户会话持久化到数据库。"""
        session_id = session_id or "default"
        intent_hint = ""
        agent_hint = ""
        logger.info(f"[{request_id}] 会话 {session_id} 收到消息: {redact_sensitive(user_input[:60])}")

        persist = bool(user_id) or session_exists(session_id)
        history = _db_history_text(session_id) if persist else self._session_history.get(session_id, "")

        try:
            intents, user_queries, follow_up_message = self._intent_agent(user_input, session_id, history)
            intents = collapse_redundant_intents(intents)
            intent_hint = ",".join(intents)

            if "out_of_scope" in intents or follow_up_message:
                response = follow_up_message or "暂不支持此意图。"
            else:
                responses = []
                routed_agents = []
                for intent in intents:
                    if intent == "attraction":
                        chain = SmartVoyagePrompts.attraction_prompt() | self.llm
                        responses.append(_invoke_with_retry(chain, {"query": user_input}).content.strip())
                        continue

                    agent_name = INTENT_AGENT_MAP.get(intent)
                    if not agent_name:
                        responses.append("暂不支持此意图。")
                        continue

                    query_str = user_queries.get(intent, "")
                    logger.info(f"{agent_name} 查询：{query_str}")
                    agent = self.agent_network.get_agent(agent_name)
                    if agent_name == "ItineraryPlannerAssistant":
                        message_text = query_str
                    else:
                        message_text = "\n".join(history.split("\n")[-7:-1]) + f"\nUser: {query_str}"
                    if agent_name == "TicketOrderAssistant" and user_id:
                        message_text = f"{message_text}\n用户ID: {user_id}"
                    if request_id:
                        message_text = f"[请求ID: {request_id}]\n{message_text}"
                    message = Message(content=TextContent(text=message_text), role=MessageRole.USER)
                    task = Task(id="task-" + str(uuid.uuid4()), message=message.to_dict())

                    try:
                        agent_client = agent
                        if request_id:
                            agent_client = A2AClient(
                                AGENT_URLS[agent_name], timeout=AGENT_TIMEOUT,
                                headers={"X-Request-ID": request_id}
                            )
                        raw_response = asyncio.run(asyncio.wait_for(agent_client.send_task_async(task), timeout=AGENT_TIMEOUT))
                    except asyncio.TimeoutError:
                        logger.error(f"调用代理 {agent_name} 总等待超时90秒")
                        responses.append("调用代理服务超时（90s），服务处理过慢。")
                        routed_agents.append(agent_name)
                        continue
                    except Exception as call_e:
                        logger.error(f"调用代理 {agent_name} 网络异常: {str(call_e)}")
                        responses.append(f"调用代理服务网络异常：{str(call_e)}")
                        routed_agents.append(agent_name)
                        continue

                    if raw_response.status.state == "completed":
                        try:
                            logger.info(f"{agent_name} artifacts原始结构: {raw_response.artifacts}")
                            artifact = raw_response.artifacts[0]
                            parts = artifact["parts"] if isinstance(artifact, dict) else artifact.parts
                            part = parts[0]
                            agent_result = part["text"] if isinstance(part, dict) else part.text
                        except Exception:
                            agent_result = "代理返回数据解析失败"
                    else:
                        msg_raw = raw_response.status.message
                        if isinstance(msg_raw, dict) and "content" in msg_raw and isinstance(msg_raw["content"], dict):
                            agent_result = msg_raw["content"]["text"]
                        elif isinstance(msg_raw, dict) and "error" in msg_raw:
                            agent_result = f"代理执行失败：{msg_raw['error']}"
                        else:
                            agent_result = str(msg_raw)

                    if not agent_result or not agent_result.strip():
                        agent_result = "代理返回空结果，请稍后重试。"
                    logger.info(f"{agent_name} 响应摘要: {agent_result[:200]}")

                    if agent_name == "WeatherQueryAssistant":
                        chain = SmartVoyagePrompts.summarize_weather_prompt() | self.llm
                        final_response = _invoke_with_retry(
                            chain,
                            {"query": query_str, "raw_response": agent_result}
                        ).content.strip()
                    elif agent_name == "TicketQueryAssistant":
                        chain = SmartVoyagePrompts.summarize_ticket_prompt() | self.llm
                        final_response = _invoke_with_retry(
                            chain,
                            {"query": query_str, "raw_response": agent_result}
                        ).content.strip()
                    elif agent_name == "HotelQueryAssistant":
                        chain = SmartVoyagePrompts.summarize_hotel_prompt() | self.llm
                        final_response = _invoke_with_retry(
                            chain,
                            {"query": query_str, "raw_response": agent_result}
                        ).content.strip()
                    else:
                        final_response = agent_result

                    responses.append(final_response)
                    routed_agents.append(agent_name)

                response = "\n\n".join(responses)
                agent_hint = ",".join(routed_agents)
                if routed_agents:
                    logger.info(f"路由到代理：{routed_agents}")

            self._remember(session_id, user_input, response, user_id, intent_hint, agent_hint, persist)
            return response

        except json.JSONDecodeError as json_err:
            logger.error("意图识别JSON解析失败")
            error_message = f"意图识别JSON解析失败：{str(json_err)}。请重试。"
            self._remember(session_id, user_input, error_message, user_id, intent_hint, agent_hint, persist)
            return error_message
        except Exception as e:
            logger.error(f"处理异常: {str(e)}")
            error_message = f"处理失败：{str(e)}。请重试。"
            self._remember(session_id, user_input, error_message, user_id, intent_hint, agent_hint, persist)
            return error_message

    def _remember(self, session_id: str, user_input: str, response: str,
                  user_id: int = None, intent: str = "", agent_name: str = "",
                  persist: bool = False) -> None:
        with self._lock:
            current = self._session_history.get(session_id, "")
            self._session_history[session_id] = _trim_history(
                f"{current}\nUser: {user_input}\nAssistant: {response}"
            )
        if persist:
            save_message(session_id, "user", user_input)
            save_message(session_id, "assistant", response, intent=intent, agent_name=agent_name)

    async def stream_process(self, user_input: str, session_id: str = "default",
                             user_id: int = None, request_id: str = "") -> Any:
        """处理一条消息，逐段产出文本增量；适合 SSE 推送。"""
        session_id = session_id or "default"
        intent_hint = ""
        agent_hint = ""
        response_parts: list[str] = []
        persist = bool(user_id) or session_exists(session_id)
        history = _db_history_text(session_id) if persist else self._session_history.get(session_id, "")

        async def emit(text: str):
            if not text:
                return
            response_parts.append(text)
            for piece in _chunk_text(text):
                yield {"delta": piece}

        try:
            intents, user_queries, follow_up_message = await asyncio.to_thread(
                self._intent_agent, user_input, session_id
            )
            intents = collapse_redundant_intents(intents)
            intent_hint = ",".join(intents)

            if "out_of_scope" in intents or follow_up_message:
                response = follow_up_message or "暂不支持此意图。"
                async for event in emit(response):
                    yield event
            else:
                routed_agents = []
                for intent in intents:
                    if intent == "attraction":
                        chain = SmartVoyagePrompts.attraction_prompt() | self.llm
                        async for chunk in chain.astream({"query": user_input}):
                            async for event in emit(_extract_chunk_text(chunk)):
                                yield event
                        continue

                    agent_name = INTENT_AGENT_MAP.get(intent)
                    if not agent_name:
                        async for event in emit("暂不支持此意图。"):
                            yield event
                        continue

                    query_str = user_queries.get(intent, "")
                    logger.info(f"[{request_id or '-'}] {agent_name} 查询：{query_str}")
                    if agent_name == "ItineraryPlannerAssistant":
                        message_text = query_str
                    else:
                        message_text = "\n".join(history.split("\n")[-6:]) + f"\nUser: {query_str}"
                    if agent_name == "TicketOrderAssistant" and user_id:
                        message_text = f"{message_text}\n用户ID: {user_id}"
                    if request_id:
                        message_text = f"[请求ID: {request_id}]\n{message_text}"
                    message = Message(content=TextContent(text=message_text), role=MessageRole.USER)
                    task = Task(id="task-" + str(uuid.uuid4()), message=message.to_dict())

                    try:
                        client_headers = {"X-Request-ID": request_id} if request_id else None
                        agent_client = A2AClient(
                            AGENT_URLS[agent_name], timeout=AGENT_TIMEOUT, headers=client_headers
                        )
                        agent_result = ""
                        streamed_any = False
                        summarized = agent_name in (
                            "WeatherQueryAssistant", "TicketQueryAssistant", "HotelQueryAssistant"
                        )

                        async def stream_agent():
                            nonlocal agent_result, streamed_any
                            async for chunk in agent_client.stream_response(message):
                                text = chunk if isinstance(chunk, str) else _extract_chunk_text(chunk)
                                if not text:
                                    continue
                                agent_result += text
                                streamed_any = True
                                if not summarized:
                                    async for event in emit(text):
                                        yield event

                        gen = stream_agent()
                        while True:
                            try:
                                await asyncio.wait_for(gen.__anext__(), timeout=AGENT_TIMEOUT)
                            except StopAsyncIteration:
                                break
                        if not agent_result.strip():
                            try:
                                raw = await asyncio.wait_for(
                                    agent_client.send_task_async(task), timeout=AGENT_TIMEOUT
                                )
                                if raw.status.state == "completed" and raw.artifacts:
                                    artifact = raw.artifacts[0]
                                    parts = artifact["parts"] if isinstance(artifact, dict) else artifact.parts
                                    part = parts[0]
                                    agent_result = part["text"] if isinstance(part, dict) else part.text
                            except Exception as e:
                                logger.error(f"[{request_id or '-'}] 流式为空时非流式回退失败: {e}")
                            agent_result = agent_result or ""
                            if not agent_result.strip():
                                agent_result = "代理返回空结果，请稍后重试。"
                        if not summarized and agent_result.strip() and not streamed_any:
                            async for event in emit(agent_result):
                                yield event
                    except asyncio.TimeoutError:
                        logger.error(f"[{request_id or '-'}] 调用代理 {agent_name} 超时")
                        agent_result = "调用代理服务超时（90s），服务处理过慢。"
                    except Exception as call_e:
                        logger.error(f"[{request_id or '-'}] 调用代理 {agent_name} 网络异常: {call_e}")
                        agent_result = f"调用代理服务网络异常：{str(call_e)}"

                    routed_agents.append(agent_name)
                    if agent_name == "WeatherQueryAssistant":
                        chain = SmartVoyagePrompts.summarize_weather_prompt() | self.llm
                        async for chunk in chain.astream({"query": query_str, "raw_response": agent_result}):
                            async for event in emit(_extract_chunk_text(chunk)):
                                yield event
                    elif agent_name == "TicketQueryAssistant":
                        chain = SmartVoyagePrompts.summarize_ticket_prompt() | self.llm
                        async for chunk in chain.astream({"query": query_str, "raw_response": agent_result}):
                            async for event in emit(_extract_chunk_text(chunk)):
                                yield event
                    elif agent_name == "HotelQueryAssistant":
                        chain = SmartVoyagePrompts.summarize_hotel_prompt() | self.llm
                        async for chunk in chain.astream({"query": query_str, "raw_response": agent_result}):
                            async for event in emit(_extract_chunk_text(chunk)):
                                yield event
                    else:
                        async for event in emit(agent_result):
                            yield event

                agent_hint = ",".join(routed_agents)

            response = "".join(response_parts).strip()
            await asyncio.to_thread(
                self._remember, session_id, user_input, response or "（未返回内容）",
                user_id, intent_hint, agent_hint, persist
            )
            yield {"done": True, "session_id": session_id}
        except Exception as e:
            logger.error(f"[{request_id or '-'}] 流式处理异常: {str(e)}")
            error_message = f"处理失败：{str(e)}。请重试。"
            yield {"delta": error_message}
            await asyncio.to_thread(
                self._remember, session_id, user_input, error_message,
                user_id, intent_hint, agent_hint, persist
            )
            yield {"done": True, "session_id": session_id}

    def agent_cards(self) -> list[dict]:
        return [
            {"name": name, "url": url, "status": "online"}
            for name, url in AGENT_URLS.items()
        ]
