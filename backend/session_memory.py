"""跨消息会话记忆：保存路线、日期、人数、席别等槽位并显示为 chips。"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from core.create_logger import logger
from utils.db import get_connection

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS session_memories (
    session_id VARCHAR(36) NOT NULL PRIMARY KEY,
    memory_json TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=INNODB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def ensure_session_memory_table() -> None:
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(CREATE_TABLE_SQL)
        conn.commit()
        cur.close()
    except Exception as exc:
        logger.debug(f"创建 session_memories 表失败: {exc}")
    finally:
        if conn and conn.is_connected():
            conn.close()


def load_session_memory(session_id: str) -> dict[str, Any]:
    if not session_id:
        return {}
    conn = None
    try:
        ensure_session_memory_table()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT memory_json FROM session_memories WHERE session_id = %s",
            (session_id,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return {}
        data = json.loads(row[0])
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.debug(f"读取会话记忆失败: {exc}")
        return {}
    finally:
        if conn and conn.is_connected():
            conn.close()


def save_session_memory(session_id: str, memory: dict[str, Any]) -> bool:
    if not session_id:
        return False
    conn = None
    try:
        ensure_session_memory_table()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO session_memories (session_id, memory_json) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE memory_json = VALUES(memory_json)",
            (session_id, json.dumps(memory, ensure_ascii=False)),
        )
        conn.commit()
        cur.close()
        return True
    except Exception as exc:
        logger.debug(f"保存会话记忆失败: {exc}")
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def delete_session_memory(session_id: str) -> None:
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM session_memories WHERE session_id = %s", (session_id,))
        conn.commit()
        cur.close()
    except Exception as exc:
        logger.debug(f"删除会话记忆失败: {exc}")
    finally:
        if conn and conn.is_connected():
            conn.close()


_CITY_NAME_RE = re.compile(r"[一-龥]{2,}")
_DATE_RE = re.compile(r"(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})日?")
_MONTH_DAY_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")
_RELATIVE_DAY = {"今天": 0, "今日": 0, "明天": 1, "明日": 1, "后天": 2}
_TRAVELER_CN = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _resolve_date(text: str, today: date) -> str | None:
    match = _DATE_RE.search(text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = _MONTH_DAY_RE.search(text)
    if match:
        return f"{today.year:04d}-{int(match.group(1)):02d}-{int(match.group(2)):02d}"
    for key, delta in _RELATIVE_DAY.items():
        if key in text:
            return (today + timedelta(days=delta)).isoformat()
    if "周末" in text:
        return (today + timedelta(days=(5 - today.weekday()) % 7)).isoformat()
    return None


def _travelers_from_text(text: str) -> int | None:
    match = re.search(r"(\d+)\s*(?:个)?\s*(?:大人|成人|人|位|张|间)", text)
    if match:
        value = int(match.group(1))
        return max(1, min(value, 20))
    match = re.search(r"([一二两三四五六七八九])\s*(?:位|人|个)", text)
    if match:
        return _TRAVELER_CN.get(match.group(1), 1)
    if "两位" in text or "两个" in text:
        return 2
    return None


def _seat_from_text(text: str) -> str | None:
    match = re.search(r"(商务座|一等座|二等座|软卧|硬卧|硬座|无座)", text)
    return match.group(1) if match else None


def _route_cities(text: str) -> tuple[str, str] | None:
    """复用票务 Agent 的全国城市识别能力，不引入额外城市字典。"""
    try:
        from utils.mock_travel_provider import extract_route
        route = extract_route(text)
        if route:
            return route[0], route[1]
    except Exception:
        pass
    return None


def extract_memory_slots(user_input: str, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """从一条用户消息中增量抽取路线、日期、人数、席别等槽位。"""
    text = user_input or ""
    memory = dict(previous or {})
    route = _route_cities(text)
    if route:
        memory["from_city"] = route[0]
        memory["to_city"] = route[1]
        memory["route"] = f"{route[0]} → {route[1]}"

    resolved = _resolve_date(text, date.today())
    if resolved:
        memory["date"] = resolved
    if "上次" in text or "续订" in text or "再订" in text or "还订" in text:
        memory.setdefault("same_as_last", True)

    travelers = _travelers_from_text(text)
    if travelers:
        memory["travelers"] = travelers

    seat = _seat_from_text(text)
    if seat:
        memory["seat_type"] = seat

    budget = re.search(r"预算\s*(\d{3,7})", text)
    if budget:
        memory["budget"] = int(budget.group(1))
    elif "预算" in text:
        budget = re.search(r"(\d{3,7})\s*元", text)
        if budget:
            memory["budget"] = int(budget.group(1))
    return memory


def memory_chips(memory: dict[str, Any] | None) -> list[dict[str, str]]:
    """把记忆槽位转成前端可展示的 chip 列表。"""
    if not memory:
        return []
    chips = []
    if memory.get("route"):
        chips.append({"label": memory["route"], "key": "route"})
    if memory.get("date"):
        chips.append({"label": memory["date"], "key": "date"})
    if memory.get("travelers"):
        chips.append({"label": f"{memory['travelers']}人", "key": "travelers"})
    if memory.get("seat_type"):
        chips.append({"label": memory["seat_type"], "key": "seat_type"})
    if memory.get("budget"):
        chips.append({"label": f"预算 ¥{memory['budget']}", "key": "budget"})
    if memory.get("same_as_last"):
        chips.append({"label": "沿用上次", "key": "same_as_last"})
    return chips
