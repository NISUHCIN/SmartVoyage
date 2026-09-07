"""RollingGo 真实酒店搜索与房型查询适配器，失败时回退本地 hotel_rooms。"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from core.create_logger import logger

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _rollinggo_conf() -> dict | None:
    cfg_path = _PROJECT_ROOT / ".mcp.json"
    if not cfg_path.exists():
        return None
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        for item in data.get("mcpServers", {}).values():
            if item.get("url", "").rstrip("/") == "https://mcp.rollinggo.cn/mcp":
                return item
    except Exception as exc:
        logger.warning(f"读取 .mcp.json 失败: {exc}")
    return None


def _hash_key(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(str(value).replace("¥", "").replace(",", "").strip())
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _as_local_row(row: dict[str, Any], city: str) -> dict[str, Any]:
    """把 MySQL hotel_rooms 的一行规范成酒店候选行。"""
    price = _num(row.get("price"))
    row_id = str(row.get("id") or row.get("hotel_name") or "")
    booking = {
        "source": "local_db",
        "hotel_ref": row_id,
        "room_type": str(row.get("room_type") or "标准房"),
    }
    return {
        "hotel_name": str(row.get("hotel_name") or ""),
        "city": str(row.get("city") or city),
        "district": str(row.get("district") or ""),
        "address": str(row.get("address") or ""),
        "room_type": str(row.get("room_type") or ""),
        "bed_type": str(row.get("bed_type") or ""),
        "price": price,
        "star_rating": float(row["rating"]) if row.get("rating") is not None else None,
        "remaining_rooms": int(row["remaining_rooms"]) if row.get("remaining_rooms") is not None else None,
        "has_breakfast": bool(row.get("has_breakfast")),
        "has_wifi": bool(row.get("has_wifi")),
        "has_parking": bool(row.get("has_parking")),
        "source": "本地演示数据",
        "degraded": True,
        "needs_room_detail": False,
        "_booking_key": _hash_key("local", city, row_id),
        "_booking": booking,
    }


def search_local_hotels(
    city: str,
    district: str | None = None,
    room_type: str | None = None,
    max_price: float | None = None,
) -> list[dict[str, Any]]:
    from utils.db import get_connection

    sql = """
        SELECT hotel_name, city, district, address, room_type, bed_type, price,
               remaining_rooms, rating, has_breakfast, has_wifi, has_parking
        FROM hotel_rooms WHERE city = %s
    """
    params: list[Any] = [city]
    if district:
        sql += " AND district LIKE %s"
        params.append(f"%{district}%")
    if room_type:
        sql += " AND room_type LIKE %s"
        params.append(f"%{room_type}%")
    if max_price:
        sql += " AND price <= %s"
        params.append(max_price)
    sql += " ORDER BY price ASC LIMIT 30"

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return [_as_local_row(row, city) for row in rows]
    except Exception as exc:
        logger.warning(f"本地酒店查询失败: {exc}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def _result_looks_related(city: str, hotel: dict[str, Any]) -> bool:
    """防真实接口对不支持的国内城市静默返回默认目的地。"""
    if not city or not any("\u4e00" <= ch <= "\u9fff" for ch in city):
        return True
    haystack = " ".join([
        str(hotel.get("name") or ""),
        str(hotel.get("address") or ""),
        str(hotel.get("areaCode") or ""),
        str(hotel.get("destinationName") or ""),
    ])
    if city in haystack:
        return True
    return False


async def rollinggo_search_hotels(
    city: str,
    check_in: str | None = None,
    nights: int = 1,
    adults: int = 2,
    max_price: float | None = None,
    request_id: str = "",
) -> tuple[list[dict[str, Any]], bool]:
    """调用 RollingGo searchHotels，返回真实酒店候选行与是否成功。"""
    conf = _rollinggo_conf()
    if not conf:
        return [], False
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    check_in = check_in or (date.today() + timedelta(days=1)).isoformat()
    try:
        async with streamablehttp_client(
            conf["url"], headers=conf.get("headers", {})
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("searchHotels", {
                    "originQuery": f"{city}的酒店，{adults}人{nights}晚",
                    "place": city,
                    "placeType": "城市",
                    "checkInParam": {
                        "checkInDate": check_in,
                        "stayNights": max(1, min(int(nights or 1), 28)),
                        "adultCount": max(1, int(adults or 2)),
                    },
                    "hotelTags": {"maxPricePerNight": max_price} if max_price else {},
                    "size": 20,
                })
                text = result.content[0].text
                data = json.loads(text) if isinstance(text, str) else text
                hotels = data.get("hotelInformationList") or []
                logger.info(
                    f"RollingGo 酒店搜索 city={city} 返回 {len(hotels)} 家 "
                    f"rid={request_id or '-'}"
                )
                rows = []
                for hotel in hotels[:20]:
                    if not isinstance(hotel, dict) or not hotel.get("name"):
                        continue
                    if not _result_looks_related(city, hotel):
                        logger.info(f"RollingGo 结果与 {city} 不相关，忽略 {hotel.get('name')}")
                        continue
                    price_obj = hotel.get("price") or {}
                    price = _num(price_obj.get("lowestPrice"))
                    if price is None:
                        continue
                    hotel_id = str(hotel.get("hotelId") or "")
                    rows.append({
                        "hotel_name": str(hotel.get("name") or ""),
                        "hotel_name_en": str(hotel.get("nameEn") or ""),
                        "city": city,
                        "district": str(hotel.get("areaName") or hotel.get("district") or ""),
                        "address": str(hotel.get("address") or ""),
                        "star_rating": hotel.get("starRating"),
                        "price": price,
                        "currency": str(price_obj.get("currency") or "CNY"),
                        "price_message": str(price_obj.get("message") or ""),
                        "image_url": str(hotel.get("imageUrl") or ""),
                        "description": str(hotel.get("description") or "")[:220],
                        "source": "RollingGo 真实接口",
                        "degraded": False,
                        "needs_room_detail": True,
                        "room_type": "",
                        "hotel_id": hotel_id,
                        "booking_url": str(hotel.get("bookingUrl") or ""),
                        "check_in": check_in,
                        "nights": int(nights or 1),
                        "_booking_key": _hash_key("rollinggo", city, hotel_id, check_in, nights),
                        "_booking": {
                            "source": "rollinggo",
                            "hotel_id": hotel_id,
                            "booking_url": str(hotel.get("bookingUrl") or ""),
                            "check_in": check_in,
                            "nights": int(nights or 1),
                        },
                    })
                return rows, True
    except Exception as exc:
        logger.warning(f"RollingGo 酒店搜索异常，准备回退本地: {exc}")
        return [], False


async def rollinggo_hotel_rooms(
    hotel: dict[str, Any],
    check_in: str,
    check_out: str,
    adults: int = 2,
    rooms: int = 1,
    request_id: str = "",
) -> tuple[list[dict[str, Any]], bool]:
    """根据真实酒店 ID 拉取可售房型与价税明细。"""
    conf = _rollinggo_conf()
    if not conf:
        return [], False
    hotel_id = hotel.get("hotel_id") or (hotel.get("_booking") or {}).get("hotel_id")
    if not hotel_id:
        return [], False
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    try:
        async with streamablehttp_client(
            conf["url"], headers=conf.get("headers", {})
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("getHotelDetail", {
                    "hotelId": int(hotel_id),
                    "dateParam": {"checkInDate": check_in, "checkOutDate": check_out},
                    "occupancyParam": {
                        "adultCount": max(1, int(adults or 2)),
                        "childCount": 0,
                        "roomCount": max(1, int(rooms or 1)),
                    },
                })
                text = result.content[0].text
                data = json.loads(text) if isinstance(text, str) else text
                plans = data.get("roomRatePlans") or []
                logger.info(
                    f"RollingGo 房型查询 hotel={hotel.get('hotel_name')} 返回 {len(plans)} 个房型 "
                    f"rid={request_id or '-'}"
                )
                rows = []
                for plan in plans:
                    if not isinstance(plan, dict):
                        continue
                    if plan.get("isOnRequest"):
                        continue
                    price = _num(plan.get("averagePrice"))
                    if price is None:
                        continue
                    room_info = plan.get("roomInfo") or {}
                    room_name = str(plan.get("roomName") or plan.get("ratePlanName") or "标准房")
                    rate_plan_id = str(plan.get("ratePlanId") or room_name)
                    rows.append({
                        "hotel_name": str(data.get("name") or hotel.get("hotel_name") or ""),
                        "hotel_id": str(data.get("hotelId") or hotel_id),
                        "city": hotel.get("city") or "",
                        "room_type": room_name,
                        "rate_plan_name": str(plan.get("ratePlanName") or ""),
                        "bed_type": str(plan.get("bedTypeDescription") or ""),
                        "price": price,
                        "currency": str(plan.get("currency") or "CNY"),
                        "meal_type": str(plan.get("mealTypeStr") or "不含早餐"),
                        "meal_amount": plan.get("mealAmount"),
                        "cancel_policy": str(plan.get("cancelPolicy") or "不可免费取消"),
                        "cancelable": bool(plan.get("cancelable")),
                        "room_size": str(room_info.get("size") or ""),
                        "max_occupancy": room_info.get("maxOccupancy"),
                        "has_wifi": bool(room_info.get("hasWifi")),
                        "available": True,
                        "source": "RollingGo 真实接口",
                        "degraded": False,
                        "needs_room_detail": False,
                        "check_in": check_in,
                        "check_out": check_out,
                        "rate_plan_id": rate_plan_id,
                        "_booking_key": _hash_key(
                            "rollinggo_room", hotel_id, rate_plan_id, check_in, check_out
                        ),
                        "_booking": {
                            "source": "rollinggo_room",
                            "hotel_id": str(data.get("hotelId") or hotel_id),
                            "rate_plan_id": rate_plan_id,
                            "check_in": check_in,
                            "check_out": check_out,
                        },
                    })
                return rows, True
    except Exception as exc:
        logger.warning(f"RollingGo 房型查询异常: {exc}")
        return [], False


async def search_hotels_structured(
    city: str,
    check_in: str | None = None,
    nights: int = 1,
    adults: int = 2,
    district: str | None = None,
    room_type: str | None = None,
    max_price: float | None = None,
    request_id: str = "",
) -> dict[str, Any]:
    """真实酒店优先、本地演示数据兜底的结构化酒店搜索。"""
    nights = max(1, min(int(nights or 1), 28))
    live_rows, live_ok = await rollinggo_search_hotels(
        city, check_in, nights, adults, max_price, request_id=request_id
    )
    if live_rows:
        return {
            "rows": live_rows,
            "source": "RollingGo 真实接口",
            "degraded": False,
            "booking_mode": "virtual_demo",
        }

    local_rows = search_local_hotels(city, district, room_type, max_price)
    return {
        "rows": local_rows,
        "source": "本地演示数据",
        "degraded": bool(not live_ok or not live_rows),
        "booking_mode": "virtual_demo",
        "message": "真实接口暂无可订结果，已降级为本地演示房型数据。",
    } if local_rows else {
        "rows": [],
        "source": "无可用数据",
        "degraded": True,
        "booking_mode": "virtual_demo",
        "message": "未找到符合该城市的酒店，请更换城市或日期后重试。",
    }


async def get_hotel_rooms_structured(
    hotel: dict[str, Any],
    check_in: str,
    nights: int,
    adults: int,
    rooms: int,
    request_id: str = "",
) -> dict[str, Any]:
    check_in = check_in or (date.today() + timedelta(days=1)).isoformat()
    check_out = (
        datetime.strptime(check_in, "%Y-%m-%d").date()
        + timedelta(days=max(1, int(nights or 1)))
    ).isoformat()
    if hotel.get("source") == "RollingGo 真实接口" or hotel.get("needs_room_detail"):
        live_rows, ok = await rollinggo_hotel_rooms(
            hotel, check_in, check_out, adults, rooms, request_id=request_id
        )
        if live_rows:
            return {
                "rows": live_rows,
                "check_in": check_in,
                "check_out": check_out,
                "source": "RollingGo 真实接口",
                "degraded": False,
            }
        if ok:
            return {
                "rows": [],
                "check_in": check_in,
                "check_out": check_out,
                "source": "RollingGo 真实接口",
                "degraded": False,
                "message": "该酒店当前日期暂无可用房型，请更换日期。",
            }

    city = hotel.get("city") or ""
    local_rows = search_local_hotels(
        city, hotel.get("district") or "", hotel.get("room_type") or "", None
    )
    if not local_rows:
        # 已选真实酒店但本地没有同名数据时，给一条“最低价可订”候选以便沙箱下单。
        price = _num(hotel.get("price"))
        if price:
            return {
                "rows": [{
                    **hotel,
                    "room_type": hotel.get("room_type") or "标准房",
                    "price": price,
                    "source": "本地演示数据",
                    "degraded": True,
                    "needs_room_detail": False,
                    "check_in": check_in,
                    "check_out": check_out,
                    "_booking_key": _hash_key(
                        "local_fallback", hotel.get("_booking_key", hotel.get("hotel_name")),
                        check_in,
                    ),
                }],
                "check_in": check_in,
                "check_out": check_out,
                "source": "本地演示数据",
                "degraded": True,
                "message": "真实房型查询失败，已生成最低价沙箱候选供演示下单。",
            }
    return {
        "rows": local_rows,
        "check_in": check_in,
        "check_out": check_out,
        "source": "本地演示数据",
        "degraded": True,
    }
