import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.china_cities import ALL_CITIES, detect_city, get_cities_by_province


def test_detect_common_cities():
    assert detect_city("帮我规划北京3天游") == "北京"
    assert detect_city("我想去南京玩两天") == "南京"
    assert detect_city("张家界4日游") == "张家界"
    assert detect_city("大理洱海三日游") == "大理"


def test_province_not_confused_with_city():
    assert detect_city("我想去吉林省旅游") is None
    assert detect_city("吉林省吉林市") == "吉林"


def test_province_city_list():
    assert "北京" in ALL_CITIES
    assert "上海" in ALL_CITIES
    assert "大理" in get_cities_by_province("云南省")
    assert len(ALL_CITIES) >= 300
