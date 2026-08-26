"""
itinerary_server.py：行程规划代理服务器，编排多Agent协作生成多日旅行行程。
保留天气功能：后台线程异步获取天气，不阻塞主行程生成，行程直接返回。
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import asyncio
import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any

import pytz
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from python_a2a import (
    A2AClient,
    A2AServer,
    AgentCard,
    AgentSkill,
    Message,
    MessageRole,
    Task,
    TaskState,
    TaskStatus,
    TextContent,
    run_server,
)

from core.config import Config
from core.create_logger import logger
from utils.china_cities import expand_province_to_capital, get_all_cities
from utils.request_id import extract_request_id, strip_request_prefix
from utils.streaming import chunk_text


def _extract_text(result: Any) -> str:
    """从 LangChain 返回结果中稳健提取文本。"""
    content = getattr(result, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                texts.append(str(block.get("text", "")))
            else:
                texts.append(str(block))
        return "\n".join(texts).strip()
    return str(content or "").strip()


conf = Config()

llm = ChatOpenAI(
    model=conf.model_name,
    base_url=conf.base_url,
    api_key=conf.api_key,
    temperature=0.2,
    max_tokens=4000,
    # 关闭思考模式，避免推理 token 耗尽后返回空正文且响应超时
    extra_body={"enable_thinking": False}
)

WEATHER_AGENT_URL = conf.a2a_weather_url
TICKET_AGENT_URL = conf.a2a_ticket_url
HOTEL_AGENT_URL = conf.a2a_hotel_url
AGENT_CALL_TIMEOUT = 15

itinerary_prompt = ChatPromptTemplate.from_template(
    """
你是一位资深旅行规划师，请根据用户的需求快速设计一份简洁的多日行程。

要求：
1. 每天只安排2‑3个核心景点，不要冗余描述，文字精简。
2. 景点地理位置就近安排，避免绕路。
3. 简要给出交通、餐饮建议，不要长篇大论。
4. 不要多余开场白，直接按下面顺序输出。
5. 严格精简，总输出控制在600字以内。
6. 交通建议必须使用“可选交通信息”中推荐的真实车次/航班，不得编造；若推荐班次时间不合适，明确提示用户并建议改期或改乘其他方式。
7. 返程班次发车时间必须晚于最后一天行程结束时间：若返程发车较早（如中午前后），最后一天只能安排上午活动，并保证发车前至少1.5小时到达车站；不得推荐与返程冲突的下午行程，也不得只写“可能赶不上”后仍保留冲突安排。
8. 住宿建议优先引用提供的真实酒店信息（酒店名、房型、价格）；若没有真实酒店信息，则给出通用住宿建议。
9. 回复必须严格按“天气 → 去程交通 → 行程安排 → 返程交通”的顺序输出，返程交通必须放在最后，不要写进最后一天的行程里。

输出必须为严格 JSON，不要输出其他内容：
{{"text": "完整行程正文，格式与下方 text 示例一致", "departure": "出发城市", "destination": "目的地",
  "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD",
  "days": [{{"day": 1, "date": "YYYY-MM-DD", "weather": "天气简述", "transport": "交通安排",
  "hotel": "住宿", "attractions": ["景点1", "景点2"]}}]}}

text 字段示例格式（正文按此顺序）：
【天气】
- 穿衣：...
- 注意：...

【去程交通】
- 推荐车次：...

【行程安排】
第一天：
- 上午：[景点]（用时）
- 午餐：[简单推荐]
- 下午：[景点]（用时）
- 晚餐：[简单推荐]
- 住宿：[真实酒店或通用建议]

【返程交通】
- 推荐车次：...

用户需求：{query}
目的地天气信息：{weather_info}
可选交通信息：{ticket_info}
可选酒店信息：{hotel_info}
当前日期：{current_date}
"""
)

async def get_agent_text(url: str, query: str, request_id: str = "") -> str:
    """调用指定 A2A Agent，返回文本结果；失败时降级为占位文本。"""
    try:
        client = A2AClient(
            url, timeout=AGENT_CALL_TIMEOUT,
            headers={"X-Request-ID": request_id} if request_id else None
        )
        msg = Message(content=TextContent(text=query), role=MessageRole.USER)
        task = Task(id="task-" + str(uuid.uuid4()), message=msg.to_dict())
        result = await client.send_task_async(task)

        if result.status.state == 'completed' and result.artifacts:
            artifact = result.artifacts[0]
            parts = artifact["parts"] if isinstance(artifact, dict) else artifact.parts
            part = parts[0]
            text = part["text"] if isinstance(part, dict) else part.text
            return text or "暂不可用"
        if result.status.state == 'input_required':
            msg_raw = result.status.message
            if isinstance(msg_raw, dict) and "content" in msg_raw:
                content = msg_raw["content"]
                if isinstance(content, dict):
                    return f"需要补充信息：{content.get('text', '')}"
                return f"需要补充信息：{content}"
            return "需要补充信息"
        return "暂不可用"
    except Exception as e:
        logger.warning(f"[Itinerary] 获取代理数据失败（{url}）: {e}")
        return "暂不可用"


def run_async_agent(url: str, query: str, request_id: str = "") -> str:
    """线程内部运行异步 A2A 请求"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(get_agent_text(url, query, request_id))
    finally:
        loop.close()


def _find_cities(text: str) -> list[str]:
    """按出现顺序返回文本中命中的城市列表。"""
    hits = []
    expanded_text = expand_province_to_capital(text)
    for city in get_all_cities():
        for match in re.finditer(re.escape(city), expanded_text):
            hits.append((match.start(), city))
    hits.sort(key=lambda item: item[0])
    return [city for _, city in hits]


def extract_departure_city(text: str) -> str | None:
    """从“从上海去北京”“上海到北京”这类表述中提取出发城市。"""
    cities = _find_cities(text)
    return cities[0] if len(cities) > 1 else None


def extract_destination_city(text: str) -> str | None:
    """提取目的地：按城市出现顺序取最后一个，避免把出发城市当目的地。"""
    cities = _find_cities(text)
    return cities[-1] if cities else None


def extract_travel_date(text: str) -> str | None:
    """提取具体日期、今天/明天，或“这周五”这类相对日期。"""
    now = datetime.now(pytz.timezone("Asia/Shanghai")).date()
    match = re.search(r"(\d{4})[-年](\d{1,2})[-月](\d{1,2})日?", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if match:
        return f"{now.year:04d}-{int(match.group(1)):02d}-{int(match.group(2)):02d}"
    relative = {"今天": 0, "今日": 0, "明天": 1, "明日": 1, "后天": 2}
    for key, delta in relative.items():
        if key in text:
            return (now + timedelta(days=delta)).strftime("%Y-%m-%d")
    if "周末" in text:
        delta = (5 - now.weekday()) % 7
        return (now + timedelta(days=delta)).strftime("%Y-%m-%d")
    weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
    match = re.search(r"这?周([一二三四五六日天])", text)
    if match:
        target = weekday_map[match.group(1)]
        delta = (target - now.weekday()) % 7
        return (now + timedelta(days=delta)).strftime("%Y-%m-%d")
    return None


_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_to_int(token: str) -> int:
    if token.isdigit():
        return int(token)
    if token in _CN_NUM:
        return _CN_NUM[token]
    if token == "十":
        return 10
    if token.startswith("十") and len(token) == 2 and token[1] in _CN_NUM:
        return 10 + _CN_NUM[token[1]]
    return 3


def extract_trip_days(text: str) -> int:
    """提取行程天数，默认 3 天。"""
    match = re.search(r"([一二两三四五六七八九十]+)\s*日游", text)
    if match:
        return _cn_to_int(match.group(1))
    match = re.search(r"(\d+)\s*天", text)
    if match:
        return int(match.group(1))
    match = re.search(r"([一二两三四五六七八九十]+)\s*天", text)
    if match:
        return _cn_to_int(match.group(1))
    match = re.search(r"(\d+)\s*日游", text)
    if match:
        return int(match.group(1))
    return 3


def parse_ticket_lines(ticket_text: str) -> list[dict]:
    """把票务 Agent 的文本结果解析成结构化班次条目。"""
    entries = []
    for line in ticket_text.splitlines():
        line = line.strip()
        if not line or any(k in line for k in ("暂", "未找到", "需要补充", "暂无")):
            continue
        times = re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", line)
        number = re.search(r"(?:车次|航班)\s*([A-Za-z0-9]+)", line)
        seat = re.search(r"，(.*?)，票价", line)
        price = re.search(r"票价\s*([\d.]+)元", line)
        entries.append({
            "line": line,
            "departure": datetime.fromisoformat(times[0]) if times else None,
            "arrival": datetime.fromisoformat(times[1]) if len(times) > 1 else None,
            "number": number.group(1) if number else "",
            "seat": seat.group(1) if seat else "",
            "price": float(price.group(1)) if price else 0.0,
        })
    return entries


def select_transport(entries: list[dict], direction: str, prefer_sleeper: bool) -> tuple[dict | None, str]:
    """按偏好选择班次：卧铺优先晚间出发，高铁/飞机去程早上到、返程下午回晚上到。"""
    if not entries:
        return None, ""

    def score(entry: dict) -> float:
        dep = entry["departure"]
        if dep is None:
            return 50.0
        hour = dep.hour
        if prefer_sleeper:
            if 18 <= hour <= 23:
                return 0.0
            if 0 <= hour < 6:
                return 5.0
            return 20.0 + abs(hour - 21)
        if direction == "out":
            arr = entry["arrival"]
            if arr and arr.date() == dep.date() and arr.hour < 12:
                return 0.0
            if hour < 9:
                return 2.0
            return 20.0 + abs(hour - 8)
        arr = entry["arrival"]
        if arr and arr.date() == dep.date() and 12 <= hour <= 18 and arr.hour <= 22:
            if hour >= 15:
                return 0.0
            return 12.0
        if 12 <= hour <= 18:
            if hour >= 15:
                return 3.0
            return 15.0
        return 20.0 + abs(hour - 15)

    best = min(entries, key=score)
    note = ""
    if score(best) >= 20:
        note = "（当天可选班次均不完全符合出行偏好，建议改期或改乘其他方式）"
    return best, note


def _pick_transport(entries: list[dict], direction: str, prefer_sleeper: bool) -> tuple[dict | None, str]:
    if prefer_sleeper:
        sleeper_entries = [e for e in entries if "卧" in e["seat"]]
        if sleeper_entries:
            return select_transport(sleeper_entries, direction, True)
        best, note = select_transport(entries, direction, False)
        fallback_note = "（未找到卧铺班次，已按高铁/飞机偏好选择）"
        return best, fallback_note + note
    return select_transport(entries, direction, False)


def build_ticket_info(ticket_out_text: str, ticket_back_text: str, prefer_sleeper: bool) -> str:
    """生成去程/返程推荐文本，交给行程 LLM 使用。"""
    best_out, out_note = _pick_transport(parse_ticket_lines(ticket_out_text), "out", prefer_sleeper)
    best_back, back_note = _pick_transport(parse_ticket_lines(ticket_back_text), "back", prefer_sleeper)
    parts = []
    if best_out:
        parts.append("去程推荐：" + best_out["line"] + out_note)
    else:
        parts.append("去程：暂无合适班次，建议查询其他日期或改乘其他交通工具")
    if best_back:
        parts.append("返程推荐：" + best_back["line"] + back_note)
    else:
        parts.append("返程：暂无合适班次，建议查询其他日期或改乘其他交通工具")
    return "\n".join(parts)


def _dedupe_repeated_text(text: str) -> str:
    """LLM 偶发整段重复输出时，合并完全相同的前后半段。"""
    if not text:
        return text
    lines = text.splitlines()
    if len(lines) >= 2 and len(lines) % 2 == 0:
        half = len(lines) // 2
        if lines[:half] == lines[half:]:
            return "\n".join(lines[:half])
    stripped = text.strip()
    if len(stripped) >= 4 and len(stripped) % 2 == 0:
        half = len(stripped) // 2
        if stripped[:half] == stripped[half:]:
            return stripped[:half]
    return text


def _return_departure_time(ticket_info: str) -> tuple[int, int] | None:
    for line in ticket_info.splitlines():
        if "返程推荐" in line:
            match = re.search(r"(\d{2}):(\d{2}):\d{2}", line)
            if match:
                return int(match.group(1)), int(match.group(2))
    return None


def _last_day_has_afternoon(text: str) -> bool:
    day_sections = [
        section for section in re.split(r"(?=第[一二三四五六七八九十\d]+天)", text)
        if re.match(r"第[一二三四五六七八九十\d]+天", section)
    ]
    if day_sections:
        return "下午" in day_sections[-1]
    return "下午" in text.split("【返程交通】")[0]


def _return_conflict_note(ticket_info: str, itinerary_text: str) -> str:
    departure = _return_departure_time(ticket_info)
    if not departure:
        return ""
    hour, minute = departure
    if hour >= 15:
        return ""
    if _last_day_has_afternoon(itinerary_text):
        return (
            f"注意：返程车次 {hour:02d}:{minute:02d} 发车，"
            "最后一天必须只安排上午活动，并在发车前至少1.5小时到达车站；"
            "上一版仍安排了下午活动，请重新调整，不要保留冲突安排。"
        )
    return ""


agent_card = AgentCard(
    name="ItineraryPlannerAssistant",
    description="旅行行程规划助手，编排多Agent协作生成多日行程方案，整合天气、交通和酒店信息",
    url=conf.a2a_itinerary_url,
    version="1.0.0",
    capabilities={"streaming": True, "memory": True},
    skills=[
        AgentSkill(
            name="plan itinerary",
            description="根据目的地、日期和偏好生成多日旅行行程，整合天气、交通和酒店信息",
            examples=["帮我规划北京3天游", "上海2日游攻略", "广州5天行程安排"]
        )
    ]
)


class ItineraryPlannerServer(A2AServer):
    def __init__(self) -> None:
        super().__init__(agent_card=agent_card)
        self.llm = llm
        self._weather_executor = ThreadPoolExecutor(max_workers=3)

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
        logger.info("[Itinerary] >>> 进入handle_task")
        content = (task.message or {}).get("content", {})
        conversation = content.get("text", "") if isinstance(content, dict) else ""
        request_id = extract_request_id(conversation)
        conversation = strip_request_prefix(conversation)
        logger.info(f"[{request_id or '-'}] 行程规划请求: {conversation}")

        try:
            # 提取城市（全国地级及以上行政区列表）
            detected_city = extract_destination_city(conversation)
            if detected_city:
                logger.info(f"[Itinerary] 从全国城市列表识别城市 {detected_city}")

            weather_future = None
            ticket_future = None
            hotel_future = None
            if detected_city:
                logger.info(f"[Itinerary] 识别城市 {detected_city}，并行查询天气/酒店/交通")
                weather_future = self._weather_executor.submit(
                    run_async_agent, WEATHER_AGENT_URL, f"{detected_city}未来5天天气", request_id
                )
                hotel_future = self._weather_executor.submit(
                    run_async_agent, HOTEL_AGENT_URL, f"{detected_city}的酒店", request_id
                )

            departure_city = extract_departure_city(conversation)
            travel_date = extract_travel_date(conversation)
            trip_days = extract_trip_days(conversation)
            date_note = ""
            if detected_city and departure_city and not travel_date:
                travel_date = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d")
                date_note = "（未指定出行日期，已按今日查询）"
            prefer_sleeper = bool(re.search(r"卧铺|硬卧|软卧|绿皮|普快", conversation))
            ticket_kind = "机票" if re.search(r"飞机|航班|飞往|机票", conversation) else "火车票"

            ticket_future = None
            ticket_back_future = None
            if detected_city and departure_city and travel_date:
                ticket_future = self._weather_executor.submit(
                    run_async_agent,
                    TICKET_AGENT_URL,
                    f"{ticket_kind} {departure_city} {detected_city} {travel_date}",
                    request_id
                )
                return_date = (
                    datetime.strptime(travel_date, "%Y-%m-%d").date()
                    + timedelta(days=max(trip_days - 1, 1))
                ).strftime("%Y-%m-%d")
                ticket_back_future = self._weather_executor.submit(
                    run_async_agent,
                    TICKET_AGENT_URL,
                    f"{ticket_kind} {detected_city} {departure_city} {return_date}",
                    request_id
                )

            current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')

            agent_results = {}
            for name, future in (
                ("weather", weather_future),
                ("ticket", ticket_future),
                ("ticket_back", ticket_back_future),
                ("hotel", hotel_future),
            ):
                if future is None:
                    agent_results[name] = "暂未提供"
                    continue
                try:
                    agent_results[name] = future.result(timeout=AGENT_CALL_TIMEOUT)
                except Exception as e:
                    logger.warning(f"[Itinerary] 等待{name}结果超时或失败: {e}")
                    agent_results[name] = "暂不可用"
            weather_info = agent_results["weather"]
            hotel_info = agent_results["hotel"]
            ticket_info = build_ticket_info(
                agent_results["ticket"],
                agent_results["ticket_back"],
                prefer_sleeper
            )
            if date_note:
                ticket_info = date_note + "\n" + ticket_info
            logger.info(f"[Itinerary] 天气:{weather_info[:80]}||交通:{ticket_info[:80]}||酒店:{hotel_info[:80]}")

            logger.info("[Itinerary] 开始调用LLM融合生成行程")
            chain = itinerary_prompt | self.llm
            raw_result = chain.invoke({
                "query": conversation,
                "weather_info": weather_info,
                "ticket_info": ticket_info,
                "hotel_info": hotel_info,
                "current_date": current_date
            })
            raw_itinerary = _extract_text(raw_result)
            logger.info(f"[Itinerary] LLM原始返回: {repr(raw_result)}")
            if not raw_itinerary:
                logger.warning(
                    f"[Itinerary] LLM返回为空，自动重试一次，finish_reason="
                    f"{raw_result.response_metadata.get('finish_reason')}"
                )
                raw_result = chain.invoke({
                    "query": conversation,
                    "weather_info": weather_info,
                    "ticket_info": ticket_info,
                    "hotel_info": hotel_info,
                    "current_date": current_date
                })
                raw_itinerary = _extract_text(raw_result)
            if not raw_itinerary:
                raw_itinerary = "抱歉，暂时无法生成行程，请稍后重试。"
            logger.info(f"[Itinerary] 行程内容长度: {len(raw_itinerary)}")
            logger.info(f"[Itinerary] 行程内容前200字: {raw_itinerary[:200]}")

            structured = None
            cleaned = re.sub(r"^```json\s*|\s*```$", "", raw_itinerary.strip()).strip()
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict) and parsed.get("text"):
                    final_itinerary = str(parsed["text"]).strip()
                    structured = parsed
                else:
                    final_itinerary = raw_itinerary
            except Exception:
                final_itinerary = raw_itinerary

            conflict_note = _return_conflict_note(ticket_info, final_itinerary)
            if conflict_note:
                logger.warning("[Itinerary] 返程时间与最后一天行程冲突，重试生成一次")
                raw_result = chain.invoke({
                    "query": conversation + "\n" + conflict_note,
                    "weather_info": weather_info,
                    "ticket_info": ticket_info,
                    "hotel_info": hotel_info,
                    "current_date": current_date,
                })
                raw_itinerary = _extract_text(raw_result)
                if raw_itinerary:
                    structured = None
                    cleaned = re.sub(r"^```json\s*|\s*```$", "", raw_itinerary.strip()).strip()
                    try:
                        parsed = json.loads(cleaned)
                        if isinstance(parsed, dict) and parsed.get("text"):
                            final_itinerary = str(parsed["text"]).strip()
                            structured = parsed
                        else:
                            final_itinerary = raw_itinerary
                    except Exception:
                        final_itinerary = raw_itinerary

            final_itinerary = _dedupe_repeated_text(final_itinerary)

            logger.info("[Itinerary] LLM行程生成完成")
            if structured:
                task.artifacts = [{"parts": [
                    {"type": "text", "text": final_itinerary},
                    {"type": "text", "text": json.dumps(structured, ensure_ascii=False)},
                ]}]
            else:
                task.artifacts = [{"parts": [{"type": "text", "text": final_itinerary}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)
            logger.info("[Itinerary] task标记COMPLETED，返回结果")
            return task

        except Exception as e:
            logger.error(f"[Itinerary] 行程规划失败: {str(e)}", exc_info=True)
            task.status = TaskStatus(state=TaskState.FAILED,
                                     message={"role": "agent",
                                              "content": {"text": f"行程规划失败: {str(e)} 请提供目的地和出行天数。"}})
            return task


if __name__ == "__main__":
    server = ItineraryPlannerServer()
    logger.info("\n=== 服务器信息 ===")
    logger.info(f"名称: {server.agent_card.name}")
    logger.info(f"描述: {server.agent_card.description}")
    for skill in server.agent_card.skills:
        logger.info(f"- {skill.name}: {skill.description}")
    run_server(server, host="127.0.0.1", port=conf.a2a_itinerary_port)
