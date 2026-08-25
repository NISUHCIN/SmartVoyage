import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytz

from agents import itinerary_server
from agents.itinerary_server import (
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
