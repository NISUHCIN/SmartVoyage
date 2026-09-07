"""全国城市名到和风天气位置的离线解析器。

优先使用 112 个官方 LocationID；未收录城市读取
utils/china_city_coordinates.json 中的经纬度，按 经度,纬度 调和风天气。
"""
from __future__ import annotations

import json
from pathlib import Path

from utils.qweather_cities import CITY_IDS

_COORD_PATH = Path(__file__).resolve().parent / "china_city_coordinates.json"
_coord_cache: dict | None = None


def _load_coordinates() -> dict:
    global _coord_cache
    if _coord_cache is None:
        try:
            _coord_cache = json.loads(_COORD_PATH.read_text(encoding="utf-8"))
        except Exception:
            _coord_cache = {}
    return _coord_cache


def get_weather_location(city: str | None) -> dict | None:
    """返回 {id|coordinate, source}；找不到返回 None。"""
    name = (city or "").strip()
    if not name:
        return None
    if name in CITY_IDS:
        return {"id": CITY_IDS[name], "source": "qweather_location_id"}

    coords = _load_coordinates()
    if name in coords:
        item = coords[name]
        return {
            "coordinate": f"{item['lng']},{item['lat']}",
            "source": "china_city_coordinates",
        }

    # 兼容“丽江市/阿坝州/恩施州”这类带行政区后缀的输入。
    stripped = name.rstrip("省市地区盟自治州特别行政区")
    if stripped and stripped != name and stripped in coords:
        item = coords[stripped]
        return {
            "coordinate": f"{item['lng']},{item['lat']}",
            "source": "china_city_coordinates",
        }
    return None


def count_known_cities() -> int:
    return len({*CITY_IDS, *_load_coordinates()})
