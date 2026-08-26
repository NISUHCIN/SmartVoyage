import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytz

from agents import itinerary_server
from agents.itinerary_server import (
    _dedupe_repeated_text,
    _last_day_has_afternoon,
    _return_conflict_note,
    extract_departure_city,
    extract_destination_city,
    extract_travel_date,
    extract_trip_days,
    parse_ticket_lines,
    select_transport,
)
from backend.chat_service import AGENT_TIMEOUT


def test_itinerary_llm_disables_thinking():
    assert itinerary_server.llm.extra_body == {"enable_thinking": False}


def test_chat_service_agent_timeout_is_aligned():
    assert AGENT_TIMEOUT == 90


def test_extract_travel_elements():
    assert extract_departure_city("8月30日从上海去北京三日游") == "上海"
    assert extract_departure_city("上海到北京三日游") == "上海"
    assert extract_destination_city("8月30日从上海去北京三日游") == "北京"
    assert extract_destination_city("上海到北京三日游") == "北京"
    assert extract_destination_city("上海去北京三日游") == "北京"
    assert extract_destination_city("北京三日游") == "北京"
    assert extract_trip_days("8月30日从上海去北京三日游") == 3
    assert extract_trip_days("云南五日游") == 5
    current_year = datetime.now(pytz.timezone("Asia/Shanghai")).year
    assert extract_travel_date("8月30日从上海去北京三日游") == f"{current_year}-08-30"
    assert extract_travel_date("2026-08-30从上海去北京") == "2026-08-30"


def test_select_transport_prefers_morning_arrival_outbound():
    lines = (
        "上海 到 北京 2026-08-28 20:09:00 2026-08-29 04:30:00: 车次 G276，一等座，票价 628.64元，剩余 8 张\n"
        "上海 到 北京 2026-08-28 08:30:00 2026-08-28 11:30:00: 车次 G100，二等座，票价 553.50元，剩余 20 张"
    )
    entries = parse_ticket_lines(lines)
    best, _ = select_transport(entries, "out", False)
    assert best is not None
    assert best["number"] == "G100"


def test_select_transport_prefers_late_afternoon_return():
    lines = (
        "北京 到 上海 2026-08-30 12:10:00 2026-08-30 15:20:00: 车次 G3159，一等座，票价 933.00元，剩余 8 张\n"
        "北京 到 上海 2026-08-30 16:00:00 2026-08-30 19:00:00: 车次 G100，二等座，票价 553.50元，剩余 20 张"
    )
    entries = parse_ticket_lines(lines)
    best, _ = select_transport(entries, "back", False)
    assert best is not None
    assert best["number"] == "G100"


def test_dedupe_repeated_text_collapses_exact_duplicate():
    assert _dedupe_repeated_text("A\nB\nA\nB") == "A\nB"
    assert _dedupe_repeated_text("同一段行程内容") == "同一段行程内容"


def test_last_day_afternoon_detection():
    text = (
        "第一天：\n- 下午：故宫\n"
        "第二天：\n- 上午：天坛\n- 下午：颐和园"
    )
    assert _last_day_has_afternoon(text)
    assert not _last_day_has_afternoon("第一天：\n- 下午：故宫\n第二天：\n- 上午：天坛")


def test_return_conflict_note_only_for_early_return_with_afternoon_plan():
    ticket_info = "返程推荐：北京 到 上海 2026-08-30 12:10:00 2026-08-30 15:20:00: 车次 G3159"
    conflict_text = "第二天：\n- 下午：颐和园"
    safe_text = "第二天：\n- 上午：天坛"
    late_ticket = "返程推荐：北京 到 上海 2026-08-30 16:00:00 2026-08-30 19:00:00: 车次 G100"
    assert _return_conflict_note(ticket_info, conflict_text)
    assert not _return_conflict_note(ticket_info, safe_text)
    assert not _return_conflict_note(late_ticket, conflict_text)
