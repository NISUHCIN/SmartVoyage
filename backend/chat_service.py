"""chat_service.py：把 main.py 的意图识别与 A2A 多 Agent 编排抽成可复用服务。

供 FastAPI 的 /api/chat 接口调用，浏览器端无需直接接触 A2A 协议。
"""

import asyncio
import json
import re
import threading
import time
import uuid
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


AGENT_URLS = {
    "WeatherQueryAssistant": "http://localhost:5005",
    "TicketQueryAssistant": "http://localhost:5006",
    "TicketOrderAssistant": "http://localhost:5007",
    "HotelQueryAssistant": "http://localhost:5008",
    "ItineraryPlannerAssistant": "http://localhost:5009",
}

AGENT_TIMEOUT = 90

INTENT_AGENT_MAP = {
    "weather": "WeatherQueryAssistant",
    "flight": "TicketQueryAssistant",
    "train": "TicketQueryAssistant",
    "concert": "TicketQueryAssistant",
    "order": "TicketOrderAssistant",
    "hotel": "HotelQueryAssistant",
    "itinerary": "ItineraryPlannerAssistant",
}


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

    def _intent_agent(self, user_input: str, session_id: str):
        chain = SmartVoyagePrompts.intent_prompt() | self.llm
        current_date = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d")
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
        logger.info(f"intents: {intents}||user_queries: {user_queries}||follow_up_message: {follow_up_message}")
        return intents, user_queries, follow_up_message

    def process(self, user_input: str, session_id: str = "default") -> str:
        """处理一条用户消息，返回助手回复文本。"""
        session_id = session_id or "default"
        with self._lock:
            history = self._session_history.setdefault(session_id, "") + f"\nUser: {user_input}"
            self._session_history[session_id] = history

        try:
            intents, user_queries, follow_up_message = self._intent_agent(user_input, session_id)

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
                        message_text = "\n".join(self._history(session_id).split("\n")[-7:-1]) + f"\nUser: {query_str}"
                    message = Message(content=TextContent(text=message_text), role=MessageRole.USER)
                    task = Task(id="task-" + str(uuid.uuid4()), message=message.to_dict())

                    try:
                        raw_response = asyncio.run(asyncio.wait_for(agent.send_task_async(task), timeout=AGENT_TIMEOUT))
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
                if routed_agents:
                    logger.info(f"路由到代理：{routed_agents}")

            with self._lock:
                self._session_history[session_id] += f"\nAssistant: {response}"
            return response

        except json.JSONDecodeError as json_err:
            logger.error("意图识别JSON解析失败")
            error_message = f"意图识别JSON解析失败：{str(json_err)}。请重试。"
            with self._lock:
                self._session_history[session_id] += f"\nAssistant: {error_message}"
            return error_message
        except Exception as e:
            logger.error(f"处理异常: {str(e)}")
            error_message = f"处理失败：{str(e)}。请重试。"
            with self._lock:
                self._session_history[session_id] += f"\nAssistant: {error_message}"
            return error_message

    def agent_cards(self) -> list[dict]:
        return [
            {"name": name, "url": url, "status": "online"}
            for name, url in AGENT_URLS.items()
        ]
