import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.hotel_server import _fallback_hotel_params
from agents.ticket_server import _fallback_params
from agents.weather_server import _fallback_weather_params
from utils.request_id import extract_request_id, strip_request_prefix


def test_ticket_fallback_params_extracts_route_and_seat():
    params = _fallback_params("北京到上海 2026-09-01 二等座")
    assert params["status"] == "ok"
    assert params["departure_city"] == "北京"
    assert params["arrival_city"] == "上海"
    assert params["date"] == "2026-09-01"
    assert params["seat_type"] == "二等座"


def test_ticket_fallback_requires_route():
    params = _fallback_params("你好")
    assert params["status"] == "input_required"


def test_weather_fallback_params_uses_city():
    params = _fallback_weather_params("北京未来5天天气", "2026-09-01")
    assert params["status"] == "ok"
    assert params["city"] == "北京"
    assert params["start_date"] == "2026-09-01"
    assert params["end_date"] == "2026-09-03"


def test_hotel_fallback_params_uses_city():
    params = _fallback_hotel_params("北京的酒店")
    assert params["status"] == "ok"
    assert params["city"] == "北京"


def test_extract_request_id_from_text():
    assert extract_request_id("[请求ID: abc-123]\n北京天气") == "abc-123"
    assert strip_request_prefix("[请求ID: abc-123]\n北京天气") == "北京天气"


def test_extract_request_id_empty():
    assert extract_request_id("北京天气") == ""
    assert strip_request_prefix("北京天气") == "北京天气"
