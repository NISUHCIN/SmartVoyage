import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.qweather_cities import CITY_IDS


def test_qweather_city_ids_format():
    assert len(CITY_IDS) >= 100
    for city, location_id in CITY_IDS.items():
        assert city.strip()
        assert location_id.isdigit() and len(location_id) == 9


def test_common_cities_covered():
    for city in ["北京", "上海", "郑州", "成都", "西安", "南京", "武汉", "杭州", "广州", "深圳"]:
        assert city in CITY_IDS
