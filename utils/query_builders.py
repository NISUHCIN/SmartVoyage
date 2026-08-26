"""参数化查询构建器：只生成带占位符的 SQL，参数由调用方传入，避免拼接用户输入。"""


def build_train_query(departure_city: str, arrival_city: str, travel_date: str,
                      seat_type: str = None) -> tuple[str, list]:
    sql = (
        "SELECT id, departure_city, arrival_city, departure_time, arrival_time, "
        "train_number, seat_type, price, remaining_seats FROM train_tickets "
        "WHERE departure_city = %s AND arrival_city = %s AND DATE(departure_time) = %s"
    )
    params = [departure_city, arrival_city, travel_date]
    if seat_type:
        sql += " AND seat_type = %s"
        params.append(seat_type)
    sql += " ORDER BY departure_time"
    return sql, params


def build_flight_query(departure_city: str, arrival_city: str, travel_date: str,
                       cabin_type: str = None) -> tuple[str, list]:
    sql = (
        "SELECT id, departure_city, arrival_city, departure_time, arrival_time, "
        "flight_number, cabin_type, price, remaining_seats FROM flight_tickets "
        "WHERE departure_city = %s AND arrival_city = %s AND DATE(departure_time) = %s"
    )
    params = [departure_city, arrival_city, travel_date]
    if cabin_type:
        sql += " AND cabin_type = %s"
        params.append(cabin_type)
    sql += " ORDER BY departure_time"
    return sql, params


def build_concert_query(city: str, artist: str = None, start_date: str = None,
                        ticket_type: str = None) -> tuple[str, list]:
    sql = (
        "SELECT id, artist, city, venue, start_time, end_time, ticket_type, "
        "price, remaining_seats FROM concert_tickets WHERE city = %s"
    )
    params = [city]
    if artist:
        sql += " AND artist = %s"
        params.append(artist)
    if start_date:
        sql += " AND DATE(start_time) = %s"
        params.append(start_date)
    if ticket_type:
        sql += " AND ticket_type = %s"
        params.append(ticket_type)
    sql += " ORDER BY start_time"
    return sql, params


def build_weather_query(city: str, start_date: str = None, end_date: str = None) -> tuple[str, list]:
    from datetime import date, timedelta

    start = start_date or date.today().isoformat()
    end = end_date or (date.fromisoformat(start) + timedelta(days=6)).isoformat()
    sql = (
        "SELECT city, fx_date, temp_max, temp_min, text_day, text_night, "
        "humidity, wind_dir_day, precip FROM weather_data "
        "WHERE city = %s AND fx_date BETWEEN %s AND %s ORDER BY fx_date"
    )
    return sql, [city, start, end]


def build_hotel_query(city: str, district: str = None, room_type: str = None,
                      price_min: float = None, price_max: float = None,
                      rating_min: float = None) -> tuple[str, list]:
    sql = (
        "SELECT hotel_name, city, district, room_type, bed_type, price, "
        "remaining_rooms, rating, has_breakfast FROM hotel_rooms WHERE city = %s"
    )
    params = [city]
    if district:
        sql += " AND district LIKE %s"
        params.append(f"%{district}%")
    if room_type:
        sql += " AND room_type LIKE %s"
        params.append(f"%{room_type}%")
    if price_min is not None:
        sql += " AND price >= %s"
        params.append(price_min)
    if price_max is not None:
        sql += " AND price <= %s"
        params.append(price_max)
    if rating_min is not None:
        sql += " AND rating >= %s"
        params.append(rating_min)
    sql += " ORDER BY price ASC"
    return sql, params
