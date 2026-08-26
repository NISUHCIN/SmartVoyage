"""
amap_api.py：高德地图 API 搜索模块。

核心功能：
    POI 关键词搜索（景点、餐厅、酒店等）。
    返回结构化的地点信息（名称、地址、评分、坐标）。
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import os

import requests

from core.create_logger import logger

AMAP_KEY = os.getenv("AMAP_API_KEY", "")
SEARCH_URL = "https://restapi.amap.com/v3/place/text"
AROUND_URL = "https://restapi.amap.com/v3/place/around"


def search_pois(keywords: str, city: str = "", types: str = "",
                page: int = 1, limit: int = 10) -> dict:
    """
    按关键词搜索 POI（景点、餐厅等）。

    Args:
        keywords: 搜索关键词，如 "故宫" "火锅"
        city: 城市名，如 "北京"
        types: POI类型码（可选），如 "110000"（风景名胜）
        page: 页码
        limit: 每页数量（最大25）

    Returns:
        {"status": "success", "data": [...]} 或 {"status": "error", "message": ...}
    """
    if not AMAP_KEY:
        return {"status": "error", "message": "未配置高德API密钥(AMAP_API_KEY)"}

    try:
        params = {
            "key": AMAP_KEY,
            "keywords": keywords,
            "city": city,
            "types": types,
            "offset": min(limit, 25),
            "page": page,
            "extensions": "all",
            "output": "json"
        }
        resp = requests.get(SEARCH_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "1":
            return {"status": "error", "message": f"高德API错误: {data.get('info')}"}

        pois = data.get("pois", [])
        results = []
        for poi in pois:
            results.append({
                "name": poi.get("name", ""),
                "type": poi.get("type", ""),
                "address": poi.get("address", ""),
                "location": poi.get("location", ""),
                "tel": poi.get("tel", ""),
                "rating": poi.get("biz_ext", {}).get("rating", ""),
                "cost": poi.get("biz_ext", {}).get("cost", ""),
                "city": poi.get("cityname", city),
                "district": poi.get("adname", "")
            })

        return {"status": "success", "data": results, "count": data.get("count", 0)}

    except Exception as e:
        logger.error(f"高德POI搜索失败: {e}")
        return {"status": "error", "message": str(e)}


def search_nearby(location: str, keywords: str = "", types: str = "",
                  radius: int = 3000, limit: int = 10) -> dict:
    """
    搜索某坐标附近的 POI。

    Args:
        location: 中心坐标 "经度,纬度"
        keywords: 搜索关键词
        types: POI类型码
        radius: 搜索半径（米）
        limit: 返回数量
    """
    if not AMAP_KEY:
        return {"status": "error", "message": "未配置高德API密钥(AMAP_API_KEY)"}

    try:
        params = {
            "key": AMAP_KEY,
            "location": location,
            "keywords": keywords,
            "types": types,
            "radius": radius,
            "sortrule": "distance",
            "offset": min(limit, 25),
            "output": "json"
        }
        resp = requests.get(AROUND_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "1":
            return {"status": "error", "message": f"高德API错误: {data.get('info')}"}

        pois = data.get("pois", [])
        results = []
        for poi in pois:
            results.append({
                "name": poi.get("name", ""),
                "type": poi.get("type", ""),
                "address": poi.get("address", ""),
                "distance": poi.get("distance", ""),
                "location": poi.get("location", ""),
                "tel": poi.get("tel", "")
            })

        return {"status": "success", "data": results}

    except Exception as e:
        logger.error(f"高德附近搜索失败: {e}")
        return {"status": "error", "message": str(e)}
