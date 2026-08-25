"""模拟火车/高铁票务与订票工具，确保整条 Agent 流程不依赖外部接口也能跑通。"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta

import pytz

from utils.china_cities import expand_province_to_capital, get_all_cities


def extract_route(text: str) -> tuple[str, str, str] | None:
    """从自然语言中提取 出发城市、到达城市、日期，提取不到日期时使用今天。"""
    hits = []
    expanded_text = expand_province_to_capital(text)
    for city in get_all_cities():
        for match in re.finditer(re.escape(city), expanded_text):
            hits.append((match.start(), city))
    hits.sort(key=lambda item: item[0])
    cities = [city for _, city in hits]
    if len(cities) < 2:
        return None
    departure, arrival = cities[0], cities[-1]
    match = re.search(r"(\d{4})[-年](\d{1,2})[-月](\d{1,2})日?", text)
    if match:
        travel_date = f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    else:
        travel_date = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d")
    return departure, arrival, travel_date


def query_trains(departure: str, arrival: str, travel_date: str) -> list[dict]:
    """生成模拟火车/高铁班次：白天高铁 + 夜间卧铺，任何城市/日期都有结果。"""
    day = datetime.strptime(travel_date, "%Y-%m-%d").date()
    seed = int(hashlib.md5(f"{departure}-{arrival}-{travel_date}".encode("utf-8")).hexdigest()[:8], 16)
    options = [
        ("08:30", "11:30", "G", "二等座", 553.5),
        ("12:10", "15:20", "G", "一等座", 880.0),
        ("20:09", None, "Z", "硬卧", 428.0),
        ("21:40", None, "D", "软卧", 720.0),
    ]
    rows = []
    for index, (dep_time, arr_time, prefix, seat, price) in enumerate(options, start=1):
        departure_dt = datetime(day.year, day.month, day.day, *map(int, dep_time.split(":")))
        if arr_time:
            arrival_dt = datetime(day.year, day.month, day.day, *map(int, arr_time.split(":")))
        else:
            arrival_dt = departure_dt + timedelta(hours=10)
        rows.append({
            "departure_city": departure,
            "arrival_city": arrival,
            "departure_time": departure_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "arrival_time": arrival_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "train_number": f"{prefix}{1000 + (seed % 9000) + index * 3}",
            "seat_type": seat,
            "price": round(price + (seed % 150), 2),
            "remaining_seats": 15 + (seed % 100),
        })
    return rows


def format_train_rows(rows: list[dict]) -> str:
    """把模拟班次转成与本地票务 Agent 相同的文本格式。"""
    lines = []
    for row in rows:
        lines.append(
            f"{row['departure_city']} 到 {row['arrival_city']} "
            f"{row['departure_time']} {row['arrival_time']}: "
            f"车次 {row['train_number']}，{row['seat_type']}，"
            f"票价 {row['price']}元，剩余 {row['remaining_seats']} 张"
        )
    return "\n".join(lines)


def create_ticket_order(departure: str, arrival: str, travel_date: str, train_number: str, quantity: int = 1) -> str:
    """模拟订票成功结果，不调用任何外部接口。"""
    return (
        f"恭喜！模拟订票成功：{departure} → {arrival}，{travel_date}，"
        f"{train_number}，{quantity}张。订单已生成（模拟数据，未调用外部接口）。"
    )
