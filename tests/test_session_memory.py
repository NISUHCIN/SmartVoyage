from backend.session_memory import extract_memory_slots, memory_chips


def test_extract_memory_slots_captures_route_date_travelers_and_seat():
    memory = extract_memory_slots("帮订 2026-09-08 从北京到上海 2人二等座", {})

    assert memory["route"] == "北京 → 上海"
    assert memory["from_city"] == "北京"
    assert memory["to_city"] == "上海"
    assert memory["date"] == "2026-09-08"
    assert memory["travelers"] == 2
    assert memory["seat_type"] == "二等座"


def test_extract_memory_slots_keeps_previous_slots_when_rebooking():
    previous = {
        "route": "北京 → 上海",
        "date": "2026-09-08",
        "travelers": 2,
        "seat_type": "二等座",
    }

    memory = extract_memory_slots("帮我再订一次", previous)

    assert memory["same_as_last"] is True
    assert memory["route"] == previous["route"]
    assert memory["date"] == previous["date"]
    assert memory["travelers"] == previous["travelers"]
    assert memory["seat_type"] == previous["seat_type"]


def test_memory_chips_maps_slots_to_labels():
    chips = memory_chips({
        "route": "北京 → 上海",
        "date": "2026-09-08",
        "travelers": 2,
        "seat_type": "二等座",
        "budget": 1500,
        "same_as_last": True,
    })

    assert ("route", "北京 → 上海") in [(c["key"], c["label"]) for c in chips]
    assert ("date", "2026-09-08") in [(c["key"], c["label"]) for c in chips]
    assert ("travelers", "2人") in [(c["key"], c["label"]) for c in chips]
    assert ("seat_type", "二等座") in [(c["key"], c["label"]) for c in chips]
    assert ("budget", "预算 ¥1500") in [(c["key"], c["label"]) for c in chips]
    assert ("same_as_last", "沿用上次") in [(c["key"], c["label"]) for c in chips]
