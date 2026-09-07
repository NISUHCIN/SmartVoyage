from utils.hotel_provider import _num, _result_looks_related


def test_num_parses_currency_and_rejects_unavailable_prices():
    assert _num("¥1,234.50") == 1234.5
    assert _num("--") is None
    assert _num("0") is None
    assert _num(None) is None


def test_result_looks_related_accepts_city_match_and_rejects_foreign_hotel():
    related = {
        "name": "北京香格里拉饭店",
        "address": "北京朝阳区",
        "areaCode": "110000",
        "destinationName": "",
    }
    foreign = {
        "name": "Tokyo Palace Hotel",
        "address": "Tokyo",
        "areaCode": "JP",
        "destinationName": "Tokyo",
    }

    assert _result_looks_related("北京", related) is True
    assert _result_looks_related("北京", foreign) is False
