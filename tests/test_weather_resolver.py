from utils.weather_resolver import get_weather_location


def test_covered_city_uses_qweather_location_id():
    assert get_weather_location("北京") == {
        "id": "101010100",
        "source": "qweather_location_id",
    }


def test_coordinate_fallback_works_for_uncatalogued_city():
    location = get_weather_location("锡林郭勒")

    assert location is not None
    assert location["source"] == "china_city_coordinates"
    assert location["coordinate"].startswith("115.049")


def test_admin_suffix_is_stripped_before_coordinate_lookup():
    assert get_weather_location("锡林郭勒盟") == get_weather_location("锡林郭勒")


def test_unknown_and_blank_city_return_none():
    assert get_weather_location("不存在市") is None
    assert get_weather_location("") is None
    assert get_weather_location(None) is None
