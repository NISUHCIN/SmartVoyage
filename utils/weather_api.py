"""
weather_api.py：和风天气 API 实时数据拉取模块。

核心功能：
    按城市名实时拉取天气预报（7天）。
    自动写入/更新数据库 weather_data 表作为缓存。
    支持 LocationID 查询和城市名映射。
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from datetime import datetime
from typing import Optional

import requests

from core.config import Config
from core.create_logger import logger

conf = Config()

BASE_URL = "https://j246h349g7.re.qweatherapi.com/v7/weather/7d"
GEO_URL = "https://j246h349g7.re.qweatherapi.com/geo/v2/city/lookup"

# 常用城市 LocationID 映射（可扩展）
CITY_LOCATION_MAP = {
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280101",
    "深圳": "101280601",
    "杭州": "101210101",
    "成都": "101270101",
    "西安": "101110101",
    "重庆": "101040100",
    "武汉": "101200101",
    "南京": "101190101",
}


def _get_location_id(city: str) -> Optional[str]:
    """通过城市名查询 LocationID"""
    if city in CITY_LOCATION_MAP:
        return CITY_LOCATION_MAP[city]

    if not conf.weather_api_key:
        logger.warning("未配置 WEATHER_API_KEY，无法查询新城市")
        return None

    try:
        resp = requests.get(
            GEO_URL,
            params={"location": city},
            headers={"X-QW-Api-Key": conf.weather_api_key},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == "200" and data.get("location"):
            location_id = data["location"][0]["id"]
            CITY_LOCATION_MAP[city] = location_id
            return location_id
    except Exception as e:
        logger.error(f"查询城市LocationID失败: {e}")
    return None


def fetch_and_cache_weather(city: str) -> dict:
    """
    从和风天气 API 拉取7天天气预报并缓存到数据库。

    Returns:
        {"status": "success", "data": [...]} 或 {"status": "error", "message": ...}
    """
    if not conf.weather_api_key:
        return {"status": "error", "message": "未配置天气API密钥"}

    location_id = _get_location_id(city)
    if not location_id:
        return {"status": "error", "message": f"无法识别城市: {city}"}

    try:
        resp = requests.get(
            f"{BASE_URL}?location={location_id}",
            headers={"X-QW-Api-Key": conf.weather_api_key},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != "200":
            return {"status": "error", "message": f"天气API返回错误: {data.get('code')}"}

        daily = data.get("daily", [])
        update_time = data.get("updateTime", datetime.now().isoformat())

        # 写入数据库缓存
        import mysql.connector
        conn = mysql.connector.connect(
            host=conf.host, user=conf.user, password=conf.password,
            database=conf.database, port=conf.db_port
        )
        cursor = conn.cursor()
        for day in daily:
            fx_date = day["fxDate"]
            values = (
                city, fx_date,
                day.get("sunrise"), day.get("sunset"),
                day.get("moonrise"), day.get("moonset"),
                day.get("moonPhase"), day.get("moonPhaseIcon"),
                int(day.get("tempMax", 0)), int(day.get("tempMin", 0)),
                day.get("iconDay"), day.get("textDay"),
                day.get("iconNight"), day.get("textNight"),
                int(day.get("wind360Day", 0)) if day.get("wind360Day") else None,
                day.get("windDirDay"), day.get("windScaleDay"),
                int(day.get("windSpeedDay", 0)) if day.get("windSpeedDay") else None,
                int(day.get("wind360Night", 0)) if day.get("wind360Night") else None,
                day.get("windDirNight"), day.get("windScaleNight"),
                int(day.get("windSpeedNight", 0)) if day.get("windSpeedNight") else None,
                float(day.get("precip", 0)) if day.get("precip") else None,
                int(day.get("uvIndex", 0)) if day.get("uvIndex") else None,
                int(day.get("humidity", 0)) if day.get("humidity") else None,
                int(day.get("pressure", 0)) if day.get("pressure") else None,
                int(day.get("vis", 0)) if day.get("vis") else None,
                int(day.get("cloud", 0)) if day.get("cloud") else None,
                update_time
            )
            cursor.execute(
                """INSERT INTO weather_data (
                    city, fx_date, sunrise, sunset, moonrise, moonset, moon_phase, moon_phase_icon,
                    temp_max, temp_min, icon_day, text_day, icon_night, text_night,
                    wind360_day, wind_dir_day, wind_scale_day, wind_speed_day,
                    wind360_night, wind_dir_night, wind_scale_night, wind_speed_night,
                    precip, uv_index, humidity, pressure, vis, cloud, update_time
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    temp_max=VALUES(temp_max), temp_min=VALUES(temp_min),
                    text_day=VALUES(text_day), text_night=VALUES(text_night),
                    humidity=VALUES(humidity), wind_dir_day=VALUES(wind_dir_day),
                    precip=VALUES(precip), update_time=VALUES(update_time)
                """,
                values
            )
        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"天气数据已缓存: {city} {len(daily)}天")
        return {"status": "success", "data": daily}

    except Exception as e:
        logger.error(f"拉取天气数据失败: {e}")
        return {"status": "error", "message": str(e)}
