import json
from unittest import mock

from fastapi.testclient import TestClient

import backend.api_server as api_server
from backend.trace_store import clear_traces, record_trace
from utils.train_api_aliyun import AliyunTrainAPIError

client = TestClient(api_server.app)


def test_trace_endpoint_returns_recent_records():
    clear_traces()
    record_trace(kind="chat", message="查询天气", session_id="s-trace", duration_ms=5)

    res = client.get("/api/trace?limit=5")

    assert res.status_code == 200
    assert res.json()["code"] == 0
    assert res.json()["data"][0]["message"] == "查询天气"
    clear_traces()


def test_trains_search_success_returns_rows_and_source():
    row = {
        "departure_city": "北京",
        "arrival_city": "上海",
        "travel_date": "2026-09-08",
        "departure_time": "2026-09-08 08:05:00",
        "arrival_time": "2026-09-08 11:12:00",
        "train_number": "G1234",
        "seat_type": "二等座",
        "price": 553.0,
        "remaining_seats": 20,
    }
    with mock.patch.object(api_server, "query_train_tickets", return_value=[row]), \
            mock.patch.object(api_server, "apply_virtual_occupancy", return_value=None):
        res = client.post("/api/trains/search", json={
            "departure_city": "北京",
            "arrival_city": "上海",
            "travel_date": "2026-09-08",
            "seat_type": "二等座",
        })

    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0
    assert body["data"]["rows"][0]["train_number"] == "G1234"
    assert body["data"]["source"] == "聚美智数/阿里云"
    assert body["data"]["booking_mode"] == "virtual_demo"


def test_trains_search_falls_back_to_demo_rows_when_live_api_fails():
    with mock.patch.object(
        api_server,
        "query_train_tickets",
        side_effect=AliyunTrainAPIError("上游限流，请稍后重试"),
    ), mock.patch.object(api_server, "apply_virtual_occupancy", return_value=None):
        res = client.post("/api/trains/search", json={
            "departure_city": "北京",
            "arrival_city": "上海",
            "travel_date": "2026-09-08",
        })

    assert res.status_code == 200
    body = res.json()
    assert body["data"]["source"] == "本地演示数据"
    assert body["data"]["meta"]["degraded"] is True
    assert body["data"]["rows"]
    assert body["data"]["rows"][0]["_provider"] == "demo"


def test_train_order_propagates_virtual_booking_failure():
    with mock.patch.object(
        api_server,
        "create_virtual_train_order",
        return_value=(False, "沙箱下单失败: 价格为空", {}),
    ) as create:
        res = client.post("/api/orders/train", json={
            "train": {"price": 0},
            "passenger_name": "张三",
            "contact_phone": "13800000000",
            "quantity": 1,
        })

    assert res.status_code == 400
    assert "沙箱下单失败" in res.json()["message"]
    create.assert_called_once()


def test_hotels_search_rejects_blank_city_before_external_call():
    with mock.patch.object(api_server, "search_hotels_structured") as search:
        res = client.post("/api/hotels/search", json={"city": "  "})

    assert res.status_code == 400
    assert res.json()["message"] == "请提供城市"
    search.assert_not_called()


def test_weather_search_rejects_blank_city_before_external_call():
    with mock.patch.object(api_server, "fetch_and_cache_weather") as fetch:
        res = client.post("/api/weather/search", json={"city": ""})

    assert res.status_code == 400
    assert res.json()["message"] == "请提供城市"
    fetch.assert_not_called()


def test_session_memory_endpoint_returns_chips():
    memory = {"route": "北京 → 上海", "date": "2026-09-08"}
    with mock.patch.object(api_server, "load_session_memory", return_value=memory):
        res = client.get("/api/session-memory/s-test")

    assert res.status_code == 200
    body = res.json()
    assert body["data"]["memory"] == memory
    assert body["data"]["chips"][0]["key"] == "route"
    assert json.dumps(body, ensure_ascii=False)
