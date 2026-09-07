"""
weather_server.py：天气代理服务器，从自然语言提取参数后调用 MCP 天气工具。
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import asyncio
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

import pytz
import requests
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
from utils.weather_resolver import get_weather_location

conf = Config()

# 同一城市天气结果缓存 3 小时，避免每次用户提问都重复查询
_weather_cache: dict[str, tuple[float, str]] = {}
_weather_cache_lock = threading.Lock()
WEATHER_CACHE_TTL = max(60, int(os.getenv("WEATHER_CACHE_TTL_SECONDS", "10800")))


def _get_cached_weather(city: str) -> str | None:
    if not city:
        return None
    with _weather_cache_lock:
        entry = _weather_cache.get(city)
        if entry and time.time() - entry[0] < WEATHER_CACHE_TTL:
            return entry[1]
    return None


def _set_cached_weather(city: str, text: str) -> None:
    if not city or not text:
        return
    with _weather_cache_lock:
        _weather_cache[city] = (time.time(), text)
        if len(_weather_cache) > 200:
            expired = [k for k, v in _weather_cache.items() if time.time() - v[0] >= WEATHER_CACHE_TTL]
            for k in expired:
                del _weather_cache[k]


def fetch_qweather(city: str) -> str | None:
    """调用和风天气真实接口（7 天预报，取前 5 天），失败返回 None。"""
    host = conf.qweather_api_host
    key = conf.weather_api_key
    location = get_weather_location(city)
    if not host or not key or not location:
        return None
    base = f"https://{host}" if not host.startswith("http") else host
    location_param = location.get("coordinate") or location.get("id")
    try:
        response = requests.get(
            f"{base}/v7/weather/7d",
            params={"location": location_param, "key": key},
            timeout=10,
        )
        data = response.json()
        if data.get("code") != "200":
            return None
        lines = []
        for day in data.get("daily", [])[:5]:
            precip = day.get("precip", "")
            precip_text = f"，降水{precip}mm" if precip else ""
            lines.append(
                f"{city} {day['fxDate']}: {day['textDay']}（夜间{day['textNight']}），"
                f"温度 {day['tempMin']}-{day['tempMax']}℃，风向{day['windDirDay']}{precip_text}"
            )
        return "\n".join(lines) if lines else None
    except Exception as e:
        logger.warning(f"和风天气接口异常: {e}")
        return None


llm = ChatOpenAI(
    model=conf.fast_model_name,
    base_url=conf.base_url,
    api_key=conf.api_key,
    temperature=0.1,
    extra_body={"enable_thinking": False}
)

params_prompt = ChatPromptTemplate.from_template(
    """
系统提示：你是天气查询参数抽取器。从对话历史中提取城市、起始日期和天数。
输出严格 JSON：{{"city": "北京", "start_date": "2026-09-01", "days": 3}}
- 日期缺失时 start_date 为空字符串 ""，days 默认 3。
- 无法识别城市时输出 {{"status": "input_required", "message": "请提供城市和日期，例如：北京未来3天天气"}}。
- 不要输出其他内容。

对话历史: {conversation}
当前日期: {current_date} (Asia/Shanghai)
    """
)


def _clean_json_output(output: str) -> str:
    return re.sub(r"^```json\s*|\s*```$", "", output.strip()).strip()


def _fallback_weather_params(conversation: str, current_date: str) -> dict:
    city = detect_city(conversation)
    if not city:
        return {"status": "input_required", "message": "请提供城市和日期，例如：北京未来3天天气"}
    start_date = current_date
    end_date = (datetime.strptime(current_date, "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d")
    return {"status": "ok", "city": city, "start_date": start_date, "end_date": end_date}


async def get_weather(city: str, start_date: str, end_date: str,
                      request_id: str = None) -> str:
    headers = {"X-Request-ID": request_id} if request_id else None
    async with streamablehttp_client(conf.mcp_weather_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("query_weather", {
                "city": city,
                "start_date": start_date,
                "end_date": end_date,
                "request_id": request_id or None,
            })
            return result.content[0].text


agent_card = AgentCard(
    name="WeatherQueryAssistant",
    description="基于LangChain提供天气查询服务的助手",
    url=conf.a2a_weather_url,
    version="1.1.0",
    capabilities={"streaming": True, "memory": True},
    skills=[
        AgentSkill(
            name="execute weather query",
            description="执行天气查询，返回天气数据，支持自然语言输入",
            examples=["北京 2026-09-01 天气", "上海未来5天", "今天天气如何"]
        )
    ]
)


class WeatherQueryServer(A2AServer):
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
                return {"status": "input_required", "message": "请提供城市和日期，例如：北京未来3天天气"}
            start_date = str(data.get("start_date", "") or current_date)
            days = max(1, min(int(data.get("days", 3)), 7))
            end_date = (datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=days - 1)).strftime("%Y-%m-%d")
            return {"status": "ok", "city": city, "start_date": start_date, "end_date": end_date}
        except Exception:
            return _fallback_weather_params(conversation, current_date)

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
        logger.info(f"[{request_id or '-'}] 天气查询请求: {conversation}")

        city = detect_city(conversation) or ""
        cached = _get_cached_weather(city) if city else None
        if cached:
            logger.info(f"天气命中缓存：{city}")
            task.artifacts = [{"parts": [{"type": "text", "text": cached}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)
            return task

        qweather_text = fetch_qweather(city) if city else None
        if qweather_text:
            qweather_text += "\n（数据来源：和风天气真实接口）"
            _set_cached_weather(city, qweather_text)
            logger.info(f"天气查询使用和风真实接口：{city}")
            task.artifacts = [{"parts": [{"type": "text", "text": qweather_text}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)
            return task

        try:
            params = self.extract_params(conversation)
            if params.get("status") == "input_required":
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={"role": "agent", "content": {"text": params["message"]}}
                )
                return task

            weather_result = asyncio.run(get_weather(
                params["city"], params["start_date"], params["end_date"],
                request_id=request_id
            ))
            response = json.loads(weather_result) if isinstance(weather_result, str) else weather_result
            logger.info(f"MCP 返回: {response}")

            if response.get("status") == "success":
                data = response.get("data", [])
                response_text = "\n".join([
                    f"{d['city']} {d['fx_date']}: {d['text_day']}（夜间{d['text_night']}），"
                    f"温度 {d['temp_min']}-{d['temp_max']}℃，湿度{d['humidity']}%，"
                    f"风向{d['wind_dir_day']}，降水{d['precip']}mm"
                    for d in data
                ])
                response_text += "\n（本地演示数据）"
                task.artifacts = [{"parts": [
                    {"type": "text", "text": response_text},
                    {"type": "text", "text": json.dumps(data, ensure_ascii=False)},
                ]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
                _set_cached_weather(city, response_text)
            elif response.get("status") == "no_data":
                response_text = response.get("message", "请重新输入查询的城市和日期。")
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
            logger.error(f"天气查询失败: {str(e)}", exc_info=True)
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={"role": "agent", "content": {"text": f"查询失败: {str(e)} 请重试或提供更多细节。"}}
            )
            return task


if __name__ == "__main__":
    weather_server = WeatherQueryServer()
    logger.info("\n=== 服务器信息 ===")
    logger.info(f"名称: {weather_server.agent_card.name}")
    logger.info(f"描述: {weather_server.agent_card.description}")
    logger.info("\n技能:")
    for skill in weather_server.agent_card.skills:
        logger.info(f"- {skill.name}: {skill.description}")
    run_server(weather_server, host="127.0.0.1", port=conf.a2a_weather_port)
