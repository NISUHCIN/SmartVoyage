"""聚美智数/极速数据票源适配器的纯逻辑测试（不发起真实网络请求）。"""

import utils.train_api_aliyun as train_api
from utils.train_api_aliyun import (
    normalize_jisu_response,
    normalize_train_response,
    query_train_tickets,
)


def _sample_payload() -> dict:
    return {
        "data": {
            "date": "2026-09-08",
            "start": "上海",
            "end": "杭州",
            "updateTime": "20260907040920",
            "list": [
                {
                    "trainno": "G1234",
                    "trainno_uuid": "240000G12340",
                    "type": "高铁",
                    "departstation": "上海虹桥",
                    "departstation_code": "AOH",
                    "terminalstation": "杭州东",
                    "terminalstation_code": "HGH",
                    "departuretime": "08:05",
                    "arrivaltime": "09:11",
                    "costtime": "01时06分",
                    "ze": {"price": "73.00", "num": "有"},
                    "zy": {"price": "117.00", "num": "12"},
                    "swz": {"price": "--", "num": "--"},
                }
            ],
        }
    }


def test_normalize_train_response_keeps_available_seats_only() -> None:
    rows = normalize_train_response(_sample_payload(), "2026-09-08")
    assert len(rows) == 2
    assert rows[0]["train_number"] == "G1234"
    by_seat = {row["seat_type"]: row for row in rows}
    assert set(by_seat) == {"一等座", "二等座"}
    assert by_seat["二等座"]["price"] == 73.0
    assert by_seat["二等座"]["remaining_seats"] is None
    assert by_seat["二等座"]["remaining_text"] == "有票"
    assert by_seat["一等座"]["remaining_seats"] == 12
    assert by_seat["二等座"]["source"] == "聚美智数/阿里云"


def test_normalize_train_response_respects_seat_filter() -> None:
    rows = normalize_train_response(_sample_payload(), "2026-09-08", seat_type="一等座")
    assert len(rows) == 1
    assert rows[0]["seat_type"] == "一等座"


def _sample_jisu_payload() -> dict:
    return {
        "status": "0",
        "result": [
            {
                "train_no": "G4321",
                "trainno12306": "240000G43210",
                "typename": "高速动车",
                "station": "北京南",
                "endstation": "上海虹桥",
                "departuretime": "09:00",
                "arrivaltime": "12:30",
                "numed": "有",
                "priceed": "553.00",
                "numyd": "12",
                "priceyd": "880.00",
            }
        ],
    }


def test_normalize_jisu_response_maps_common_result_schema() -> None:
    rows = normalize_jisu_response(_sample_jisu_payload(), "2026-09-08")

    assert len(rows) == 2
    assert rows[0]["train_number"] == "G4321"
    assert rows[0]["departure_city"] == "北京南"
    assert rows[0]["arrival_city"] == "上海虹桥"
    assert rows[0]["source"] == "极速数据/阿里云"
    assert rows[0]["_provider"] == "jisu"
    by_seat = {row["seat_type"]: row for row in rows}
    assert by_seat["一等座"]["price"] == 880.0
    assert by_seat["二等座"]["price"] == 553.0


def test_query_train_tickets_falls_back_from_aliyun_to_jisu(monkeypatch) -> None:
    train_api._query_cache.clear()
    monkeypatch.setenv("ALIYUN_APPCODE", "aliyun-code")
    monkeypatch.setenv("ALIYUN_TRAIN_API_URL", "https://jmhccx.example/train-query/ticket")
    monkeypatch.setenv("JISU_APPCODE", "jisu-code")
    monkeypatch.setenv("JISU_TRAIN_API_URL", "https://jisutrain.example/train/ticket")

    calls: list[str] = []

    class _FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_post(url, data, headers, timeout):
        calls.append(url)
        if "jmhccx" in url:
            raise train_api.requests.ConnectionError("聚美接口不可用")
        return _FakeResponse(_sample_jisu_payload())

    monkeypatch.setattr(train_api.requests, "post", fake_post)

    rows = query_train_tickets("北京", "上海", "2026-09-08", seat_type="二等座")

    assert len(calls) == 2
    assert calls[1] == "https://jisutrain.example/train/ticket"
    assert rows[0]["_provider"] == "jisu"
    assert rows[0]["source"] == "极速数据/阿里云"


def test_query_train_tickets_falls_back_when_aliyun_returns_no_rows(monkeypatch) -> None:
    train_api._query_cache.clear()
    monkeypatch.setenv("ALIYUN_APPCODE", "aliyun-code")
    monkeypatch.setenv("ALIYUN_TRAIN_API_URL", "https://jmhccx.example/train-query/ticket")
    monkeypatch.setenv("JISU_APPCODE", "jisu-code")
    monkeypatch.setenv("JISU_TRAIN_API_URL", "https://jisutrain.example/train/ticket")

    calls: list[str] = []

    class _FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_post(url, data, headers, timeout):
        calls.append(url)
        if "jmhccx" in url:
            return _FakeResponse({"success": True, "data": {"list": []}})
        return _FakeResponse(_sample_jisu_payload())

    monkeypatch.setattr(train_api.requests, "post", fake_post)

    rows = query_train_tickets("上海", "北京", "2026-09-11")

    assert len(calls) == 2
    assert rows[0]["_provider"] == "jisu"
