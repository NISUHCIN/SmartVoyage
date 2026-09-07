"""阿里云市场火车票真实余票查询适配器（聚美智数为主，极速数据备用）。

配置（.env）：
    ALIYUN_APPCODE=你的AppCode
    ALIYUN_TRAIN_API_URL=https://jmhccx.market.alicloudapi.com/train-query/ticket
    JISU_APPCODE=你的备用AppCode
    JISU_TRAIN_API_URL=https://jisutrain.market.alicloudapi.com/train/ticket

接口为 POST 表单请求：start/end/date 均为中文城市/车站名与 YYYY-MM-DD 日期。
该接口只用于真实查询，不涉及 12306 登录、支付或出票。
"""
from __future__ import annotations

import copy
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any

import requests

from core.create_logger import logger

SEAT_FIELDS: list[tuple[str, str]] = [
    ("商务座", "swz"),
    ("一等座", "zy"),
    ("二等座", "ze"),
    ("软卧", "rw"),
    ("硬卧", "yw"),
    ("硬座", "yz"),
    ("无座", "wz"),
]

_JISU_SEAT_KEYS: dict[str, tuple[str, str]] = {
    "商务座": ("numsw", "pricesw"),
    "一等座": ("numyd", "priceyd"),
    "二等座": ("numed", "priceed"),
    "软卧": ("numrw", "pricerw"),
    "硬卧": ("numyw", "priceyw"),
    "硬座": ("numyz", "priceyz"),
    "无座": ("numwz", "pricewz"),
}

_cache_lock = threading.Lock()
_rate_lock = threading.Lock()
_query_cache: dict[tuple[str, str, str, str, str | None], tuple[float, list[dict]]] = {}
_query_stamps: dict[str, list[float]] = {}

_TRAIN_CACHE_TTL = max(20, int(os.getenv("TRAIN_CACHE_TTL_SECONDS", "120")))
_TRAIN_RATE_MAX = max(1, int(os.getenv("TRAIN_RATE_MAX_PER_MINUTE", "12")))
_TRAIN_RATE_WINDOW = 60

_PROVIDER_CONFIG = {
    "aliyun": {
        "label": "聚美智数/阿里云",
        "url_env": "ALIYUN_TRAIN_API_URL",
        "appcode_env": "ALIYUN_APPCODE",
    },
    "jisu": {
        "label": "极速数据/阿里云",
        "url_env": "JISU_TRAIN_API_URL",
        "appcode_env": "JISU_APPCODE",
    },
}


def _rate_limit_key(
    start: str,
    end: str,
    travel_date: str,
    seat_type: str | None,
    provider: str = "aliyun",
) -> str:
    return f"{provider}|{start}|{end}|{travel_date}|{seat_type or '*'}"


def _read_cache(key: tuple[str, str, str, str, str | None]) -> list[dict] | None:
    with _cache_lock:
        entry = _query_cache.get(key)
        if entry and time.time() - entry[0] < _TRAIN_CACHE_TTL:
            return copy.deepcopy(entry[1])
    return None


def _write_cache(key: tuple[str, str, str, str, str | None], rows: list[dict]) -> None:
    with _cache_lock:
        _query_cache[key] = (time.time(), copy.deepcopy(rows))
        if len(_query_cache) > 500:
            expired = [
                k for k, v in _query_cache.items()
                if time.time() - v[0] >= _TRAIN_CACHE_TTL
            ]
            for k in expired:
                del _query_cache[k]


def _allow_request(key: str) -> bool:
    now = time.time()
    with _rate_lock:
        stamps = [s for s in _query_stamps.get(key, []) if now - s < _TRAIN_RATE_WINDOW]
        if len(stamps) >= _TRAIN_RATE_MAX:
            return False
        stamps.append(now)
        _query_stamps[key] = stamps
        if len(_query_stamps) > 2000:
            for old_key in [k for k, v in _query_stamps.items() if not v]:
                del _query_stamps[old_key]
        return True


class AliyunTrainAPIError(RuntimeError):
    """阿里云市场火车票接口调用异常（聚美/极速共用）。"""


def _configured_providers() -> list[str]:
    names = []
    for name in ("aliyun", "jisu"):
        conf = _PROVIDER_CONFIG[name]
        if os.getenv(conf["appcode_env"], "").strip() and os.getenv(
            conf["url_env"], ""
        ).strip():
            names.append(name)
    return names


def _seat_remaining(num: Any) -> tuple[int | None, str | None]:
    """把接口的余票值转成 (数字余票, 展示文本)。"""
    if num is None:
        return None, None
    text = str(num).strip()
    if text in ("", "--", "无", "-"):
        return None, None
    if text == "有":
        return None, "有票"
    try:
        value = int(text)
        return value, f"{value}张"
    except ValueError:
        return None, text


def _parse_price(price: Any) -> float | None:
    if price is None:
        return None
    text = str(price).strip()
    if text in ("", "--", "-", "无"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _resolve_datetime(travel_date: str, dep_time: str, arr_time: str) -> datetime:
    dep_dt = datetime.strptime(f"{travel_date} {dep_time}", "%Y-%m-%d %H:%M")
    arr_dt = datetime.strptime(f"{travel_date} {arr_time}", "%Y-%m-%d %H:%M")
    if arr_dt <= dep_dt:
        arr_dt += timedelta(days=1)
    return arr_dt


def normalize_train_response(
    payload: dict,
    travel_date: str,
    seat_type: str | None = None,
    limit: int = 120,
) -> list[dict]:
    """把聚美智数返回的 JSON 规范成 SmartVoyage 票务行格式。"""
    data = payload.get("data") or {}
    rows = []
    update_time = data.get("updateTime", "")
    for item in data.get("list") or []:
        if not isinstance(item, dict):
            continue
        dep_time = str(item.get("departuretime") or "")
        arr_time = str(item.get("arrivaltime") or "")
        train_no = str(item.get("trainno") or "").strip()
        if not dep_time or not arr_time or not train_no:
            continue
        try:
            dep_dt = datetime.strptime(f"{travel_date} {dep_time}", "%Y-%m-%d %H:%M")
            arr_dt = _resolve_datetime(travel_date, dep_time, arr_time)
        except ValueError:
            continue

        for seat_name, seat_key in SEAT_FIELDS:
            if seat_type and seat_type not in seat_name:
                continue
            seat_info = item.get(seat_key)
            if not isinstance(seat_info, dict):
                continue
            remaining, remaining_text = _seat_remaining(seat_info.get("num"))
            if remaining_text is None:
                continue
            price = _parse_price(seat_info.get("price"))
            if price is None:
                continue
            rows.append({
                "departure_city": item.get("departstation") or item.get("start"),
                "arrival_city": item.get("terminalstation") or item.get("end"),
                "departure_time": dep_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "arrival_time": arr_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "train_number": train_no,
                "train_type": item.get("type", ""),
                "seat_type": seat_name,
                "price": price,
                "remaining_seats": remaining,
                "remaining_text": remaining_text,
                "source": "聚美智数/阿里云",
                "_provider": "aliyun",
                "_booking": {
                    "train_uuid": item.get("trainno_uuid", ""),
                    "departure_station_code": item.get("departstation_code", ""),
                    "arrival_station_code": item.get("terminalstation_code", ""),
                    "api_updated_at": str(update_time),
                },
            })
            if len(rows) >= limit:
                return rows
    return rows


def _payload_train_rows(payload: Any, depth: int = 0) -> list[dict]:
    """兼容聚美/极速常见 JSON 容器，找到带车次字段的火车数组。"""
    train_keys = (
        "trainno", "train_no", "trainCode", "train_code",
        "trainNumber", "train_num", "checi",
    )
    if isinstance(payload, dict):
        for key in ("list", "result", "trains", "trainList", "train_list", "rows", "data"):
            value = payload.get(key)
            if (
                isinstance(value, list)
                and value
                and isinstance(value[0], dict)
                and any(k in value[0] for k in train_keys)
            ):
                return value
        if depth < 4:
            for value in payload.values():
                found = _payload_train_rows(value, depth + 1)
                if found:
                    return found
    elif (
        isinstance(payload, list)
        and payload
        and all(isinstance(item, dict) for item in payload)
        and any(k in payload[0] for k in train_keys)
    ):
        return payload
    return []


def _first_value(item: dict, keys: tuple[str, ...], default: str = "") -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return default


def _clock_text(value: Any) -> str:
    text = str(value or "").strip()
    if " " in text:
        text = text.rsplit(" ", 1)[-1]
    return text[:5] if len(text) >= 5 else ""


def _seat_cell(item: dict, seat_short: str) -> tuple[tuple[int | None, str | None], float | None]:
    direct = item.get(seat_short)
    if isinstance(direct, dict):
        return (
            _seat_remaining(direct.get("num")),
            _parse_price(direct.get("price")),
        )
    remaining: Any = None
    price: Any = None
    for key in (f"{seat_short}_num", f"{seat_short}Num", seat_short):
        if item.get(key) is not None:
            remaining = item[key]
            break
    for key in (f"{seat_short}_price", f"{seat_short}Price"):
        if item.get(key) is not None:
            price = item[key]
            break
    return _seat_remaining(remaining), _parse_price(price)


def normalize_jisu_response(
    payload: dict,
    travel_date: str,
    seat_type: str | None = None,
    limit: int = 120,
) -> list[dict]:
    """把极速数据返回的常见字段规范成 SmartVoyage 票务行格式。"""
    rows: list[dict] = []
    for item in _payload_train_rows(payload):
        if not isinstance(item, dict):
            continue
        train_no = _first_value(
            item,
            ("trainno", "train_no", "trainCode", "train_code", "trainNumber", "checi"),
        )
        dep_clock = _clock_text(
            _first_value(
                item,
                ("departuretime", "departTime", "start_time", "startTime", "starttime"),
            )
        )
        arr_clock = _clock_text(
            _first_value(
                item,
                ("arrivaltime", "arriveTime", "end_time", "endTime", "arrive_time"),
            )
        )
        if not train_no or not dep_clock or not arr_clock:
            continue
        try:
            dep_dt = datetime.strptime(f"{travel_date} {dep_clock}", "%Y-%m-%d %H:%M")
            arr_dt = _resolve_datetime(travel_date, dep_clock, arr_clock)
        except ValueError:
            continue

        departure_city = _first_value(
            item,
            (
                "station", "start_station", "startStation", "from_station",
                "fromStation", "departure_city", "start", "startCity",
            ),
        )
        arrival_city = _first_value(
            item,
            (
                "endstation", "end_station", "endStation", "to_station",
                "toStation", "arrival_city", "end", "arrive_city",
            ),
        )
        train_type = _first_value(item, ("typename", "type", "train_type", "trainType"))
        train_uuid = _first_value(
            item,
            (
                "trainno12306", "trainno_uuid", "train_no_uuid", "train_uuid",
                "trainCode", "train_code",
            ),
        )
        dep_code = _first_value(
            item,
            (
                "stationcode", "departstation_code", "start_station_code", "from_station_code",
                "startStationCode",
            ),
        )
        arr_code = _first_value(
            item,
            (
                "endstationcode", "terminalstation_code", "end_station_code", "to_station_code",
                "endStationCode",
            ),
        )

        for seat_name, _seat_short in SEAT_FIELDS:
            if seat_type and seat_type not in seat_name:
                continue
            num_key, price_key = _JISU_SEAT_KEYS[seat_name]
            remaining, remaining_text = _seat_remaining(item.get(num_key))
            if remaining_text is None:
                continue
            price = _parse_price(item.get(price_key))
            rows.append({
                "departure_city": departure_city,
                "arrival_city": arrival_city,
                "departure_time": dep_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "arrival_time": arr_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "train_number": train_no,
                "train_type": train_type,
                "seat_type": seat_name,
                "price": price,
                "remaining_seats": remaining,
                "remaining_text": remaining_text,
                "source": "极速数据/阿里云",
                "_provider": "jisu",
                "_booking": {
                    "train_uuid": train_uuid,
                    "departure_station_code": dep_code,
                    "arrival_station_code": arr_code,
                    "api_updated_at": str(item.get("updateTime") or item.get("update_time") or ""),
                },
            })
            if len(rows) >= limit:
                return rows
    return rows


def query_train_tickets(
    start_city: str,
    end_city: str,
    travel_date: str,
    seat_type: str | None = None,
    request_id: str | None = None,
    limit: int = 120,
) -> list[dict]:
    """按配置顺序调用真实票源：聚美智数失败时自动回退极速数据。"""
    providers = _configured_providers()
    if not providers:
        raise AliyunTrainAPIError(
            "未配置聚美智数或极速数据票源，请检查 ALIYUN_*/JISU_* 环境变量。"
        )

    errors: list[str] = []
    any_provider_succeeded = False
    for provider_name in providers:
        conf = _PROVIDER_CONFIG[provider_name]
        try:
            rows = _query_single_provider(
                provider_name,
                start_city,
                end_city,
                travel_date,
                seat_type=seat_type,
                request_id=request_id,
                limit=limit,
            )
            if rows:
                return rows
            any_provider_succeeded = True
            logger.warning(
                f"{conf['label']} 返回空结果，尝试备用票源 "
                f"rid={request_id or '-'}"
            )
            continue
        except AliyunTrainAPIError as exc:
            errors.append(f"{conf['label']}: {exc}")
            logger.warning(
                f"{conf['label']} 查询失败，尝试备用票源: {exc} "
                f"rid={request_id or '-'}"
            )

    if errors and not any_provider_succeeded:
        raise AliyunTrainAPIError("；".join(errors))
    return []


def _query_single_provider(
    provider_name: str,
    start_city: str,
    end_city: str,
    travel_date: str,
    seat_type: str | None = None,
    request_id: str | None = None,
    limit: int = 120,
) -> list[dict]:
    conf = _PROVIDER_CONFIG[provider_name]
    label = conf["label"]
    cache_key = (provider_name, start_city, end_city, travel_date, seat_type)
    rate_key = _rate_limit_key(
        start_city, end_city, travel_date, seat_type, provider_name
    )
    cached = _read_cache(cache_key)
    if cached is not None:
        logger.info(
            f"{label} 火车票查询命中短缓存 start={start_city} end={end_city} "
            f"date={travel_date} rid={request_id or '-'}"
        )
        return cached
    if not _allow_request(rate_key):
        raise AliyunTrainAPIError(
            f"{label} 查询过于频繁，已触发限流；请稍后重试。"
        )

    url = os.getenv(conf["url_env"], "").strip()
    appcode = os.getenv(conf["appcode_env"], "").strip()
    if not url or not appcode:
        raise AliyunTrainAPIError(f"{label} 未配置 {conf['url_env']} 或 {conf['appcode_env']}")

    headers = {
        "Authorization": f"APPCODE {appcode}",
        "User-Agent": "Mozilla/5.0 SmartVoyage/2.0",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "start": start_city,
        "end": end_city,
        "date": travel_date,
    }
    logger.info(
        f"{label} 火车票查询 start={start_city} end={end_city} "
        f"date={travel_date} rid={request_id or '-'}"
    )
    try:
        resp = requests.post(url, data=data, headers=headers, timeout=25)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        raise AliyunTrainAPIError(f"{label} 接口网络异常: {exc}") from exc
    except ValueError as exc:
        raise AliyunTrainAPIError(f"{label} 接口返回非 JSON: {resp.text[:200]}") from exc

    if isinstance(payload, dict) and payload.get("success") is False:
        message = str(payload.get("msg") or payload.get("message") or "查询失败")
        if payload.get("code") in (201, 400) and "查无数据" in message:
            return []
        raise AliyunTrainAPIError(message)

    if provider_name == "aliyun":
        rows = normalize_train_response(
            payload, travel_date, seat_type=seat_type, limit=limit
        )
    else:
        rows = normalize_jisu_response(
            payload, travel_date, seat_type=seat_type, limit=limit
        )
    if rows:
        _write_cache(cache_key, rows)
    return rows
