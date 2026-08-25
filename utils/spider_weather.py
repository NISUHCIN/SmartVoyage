from typing import Any
import logging

import requests
import mysql.connector
from datetime import datetime, timedelta
import schedule
import time
import json
import gzip
import pytz
from qianfan.trainer.configs import last_update_time

from core.config import Config
logger = logging.getLogger(__name__)

conf = Config()

# 配置
API_KEY = conf.weather_api_key
city_codes = {
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280101",
    "深圳": "101280601"
}
BASE_URL = "https://j246h349g7.re.qweatherapi.com/v7/weather/30d"
TZ = pytz.timezone('Asia/Shanghai')  # 使用上海时区

# MySQL 配置
db_config = {
    "host": conf.host,
    "port": conf.db_port,
    "user": conf.user,
    "password": conf.password,
    "database": conf.database,
    "charset": "utf8mb4"
}

def connect_db() -> Any:
    """
    目标：建立 MySQL 数据库连接。
    功能：使用 db_config 配置连接 MySQL，返回连接对象
    :return:
    """
    logger.info("正在连接数据库...")
    logger.info(db_config)
    return mysql.connector.connect(**db_config)

def fetch_weather_data(city: Any, location: Any) -> Any:
    """
    目标：从和风天气 API 获取 30 天天气预报数据。
    功能：发送 GET 请求，处理 gzip 压缩，解析 JSON 返回数据。
    :param city:
    :param location:
    :return:
    """
    headers = {
        "X-QW-Api-Key": API_KEY,
        "Accept-Encoding": "gzip"
    }
    url = f"{BASE_URL}?location={location}"
    try:
        # 请求数据, 并检查响应
        response = requests.get(url, headers=headers, timeout=10)
        # 检查响应状态码
        response.raise_for_status()
        if response.headers.get('Content-Encoding') == 'gzip':
            data = gzip.decompress(response.content).decode('utf-8')
        else:
            data = response.text
        return json.loads(data)
    except requests.RequestException as e:
        logger.info(f"请求 {city} 天气数据失败: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.info(f"{city} JSON 解析错误: {e}, 响应内容: {response.text[:500]}...")
        return None
    except gzip.BadGzipFile:
        logger.info(f"{city} 数据未正确解压，尝试直接解析: {response.text[:500]}...")
        return json.loads(response.text) if response.text else None

def get_latest_update_time(cursor: Any, city: Any) -> Any:
    """
    目标：查询数据库中指定城市的最新更新时间。
    功能：执行 SQL 查询，返回 weather_data 表中 city 的最新 update_time。
    :param cursor: 
    :param city: 
    :return: 
    """
    cursor.execute("SELECT MAX(update_time) FROM weather_data WHERE city = %s", (city,))
    result = cursor.fetchone()
    return result[0] if result[0] else None

def should_update_data(latest_time: Any, force_update: Any=False) -> Any:
    """
    目标：判断是否需要更新城市天气数据。
    功能：检查最新更新时间是否超过 1 天，或强制更新。
    :param latest_time:
    :param force_update:
    :return:
    """
    if force_update:
        return True
    if latest_time is None:
        return True

    # 时区问题：确保 latest_time 有时区信息
    if latest_time and latest_time.tzinfo is None:
        latest_time = latest_time.replace(tzinfo=TZ)

    current_time = datetime.now(TZ)
    return (current_time - latest_time) > timedelta(days=1)

def store_weather_data(conn: Any, cursor: Any, city: Any, data: Any) -> None:
    """
    目标：写入或更新天气预报数据到数据库。
    功能：循环预报数据，使用 INSERT ON DUPLICATE KEY UPDATE 插入/更新 weather_data 表。
    :param conn: MySQL 连接对象
    :param cursor: MySQL 游标对象
    :param city: 城市名称
    :param data: 天气数据 JSON 响应
    :return:
    """
    # 检查数据是否有效
    if not data or data.get("code") != "200":
        logger.info(f"{city} 数据无效，跳过存储。")
        return

    #  数据处理, 将数据处理成 INSERT 语句
    daily_data = data.get("daily", []) # 获取预报数据
    # 更新时间, 转换为上海时区
    update_time = datetime.fromisoformat(data.get("updateTime").replace("+08:00", "+08:00")).replace(tzinfo=TZ)

    for day in daily_data:
        # 处理日期格式, 转换为日期对象
        fx_date = datetime.strptime(day["fxDate"], "%Y-%m-%d").date()
        values = (
            city, # 城市名称
            fx_date, # 预报日期
            day.get("sunrise"), # 日出时间
            day.get("sunset"), # 日落时间
            day.get("moonrise"), # 月升时间
            day.get("moonset"), # 月落时间
            day.get("moonPhase"), # 月亮相
            day.get("moonPhaseIcon"), # 月亮相图标
            day.get("tempMax"), # 最高温度
            day.get("tempMin"), # 最低温度
            day.get("iconDay"), # 白天天气图标
            day.get("textDay"), # 白天天气描述
            day.get("iconNight"), # 夜间天气图标
            day.get("textNight"), # 夜间天气描述
            day.get("wind360Day"), # 白天风向360角度
            day.get("windDirDay"), # 白天风向
            day.get("windScaleDay"), # 白天风力等级
            day.get("windSpeedDay"), # 白天风速
            day.get("wind360Night"), # 夜间风向360角度
            day.get("windDirNight"), # 夜间风向
            day.get("windScaleNight"), # 夜间风力等级
            day.get("windSpeedNight"), # 夜间风速
            day.get("precip"), # 降水量
            day.get("uvIndex"), # UV指数
            day.get("humidity"), # 相对湿度
            day.get("pressure"), # 气压
            day.get("vis"), # 能见度
            day.get("cloud"), # 云量
            update_time
        )
        insert_query = """
        INSERT INTO weather_data (
            city, fx_date, sunrise, sunset, moonrise, moonset, moon_phase, moon_phase_icon,
            temp_max, temp_min, icon_day, text_day, icon_night, text_night,
            wind360_day, wind_dir_day, wind_scale_day, wind_speed_day,
            wind360_night, wind_dir_night, wind_scale_night, wind_speed_night,
            precip, uv_index, humidity, pressure, vis, cloud, update_time
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            sunrise = VALUES(sunrise), sunset = VALUES(sunset), moonrise = VALUES(moonrise),
            moonset = VALUES(moonset), moon_phase = VALUES(moon_phase), moon_phase_icon = VALUES(moon_phase_icon),
            temp_max = VALUES(temp_max), temp_min = VALUES(temp_min), icon_day = VALUES(icon_day),
            text_day = VALUES(text_day), icon_night = VALUES(icon_night), text_night = VALUES(text_night),
            wind360_day = VALUES(wind360_day), wind_dir_day = VALUES(wind_dir_day), wind_scale_day = VALUES(wind_scale_day),
            wind_speed_day = VALUES(wind_speed_day), wind360_night = VALUES(wind360_night),
            wind_dir_night = VALUES(wind_dir_night), wind_scale_night = VALUES(wind_scale_night),
            wind_speed_night = VALUES(wind_speed_night), precip = VALUES(precip), uv_index = VALUES(uv_index),
            humidity = VALUES(humidity), pressure = VALUES(pressure), vis = VALUES(vis),
            cloud = VALUES(cloud), update_time = VALUES(update_time)
        """
        try:
            cursor.execute(insert_query, values)
            logger.info(f"{city} {fx_date} 数据写入/更新成功: {day.get('textDay')}, 影响行数: {cursor.rowcount}")
            conn.commit()
            logger.info(f"{city} 事务提交完成。")
        except mysql.connector.Error as e:
            logger.info(f"{city} {fx_date} 数据库错误: {e}")
            conn.rollback()
            logger.info(f"{city} 事务回滚。")

def update_weather(force_update: Any=False) -> None:
    """
    目标：更新所有城市数据。
    功能：查看是否满足更新条件，调用数据存储与数据爬取。
    :param force_update: 是否强制更新所有数据，默认False
    :return: None
    """
    # 建立数据库连接
    conn = connect_db()
    # 创建游标对象
    cursor = conn.cursor()

    # 获取所有城市数据
    for city, location in city_codes.items():
        # 获取该城市的最新更新时间
        latest_time = get_latest_update_time(cursor, city)
        # 判断是否满足更新条件
        if should_update_data(latest_time, force_update):
            logger.info(f"开始更新 {city} 天气数据...")
            # 获取天气数据
            data = fetch_weather_data(city, location)
            if data:
                store_weather_data(conn, cursor, city, data)
        else:
            logger.info(f"{city} 数据已为最新，无需更新。最新更新时间: {latest_time}")

    cursor.close()
    conn.close()

def setup_scheduler() -> None:
    """
    目标：设置定时任务，每天在 PDT 16:00（北京时间 01:00）调用 update_weather 函数。保证数据的实时性。
    功能：
        使用 schedule 库注册每日任务。
        进入无限循环，检查并运行待执行任务，每 60 秒检查一次。
    :return: None
    """
    logger.info(schedule.__file__)  # 查看实际导入的模块路径
    # 北京时间 1:00 对应 PDT 前一天的 16:00（夏令时）
    schedule.every().day.at("16:00").do(update_weather)
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == '__main__':
    # weather_data = fetch_weather_data("北京", city_codes["北京"])
    # print(weather_data)
    # print("解析成功！")

    # 建立数据库连接
    conn = connect_db()
    cursor = conn.cursor()

    # 获取北京城市的最新更新的时间日期
    last_update_time = get_latest_update_time(cursor, '北京')
    logger.info(last_update_time)
    print(last_update_time)

    # 关闭数据库连接
    cursor.close()
    conn.close()

    from datetime import datetime, timedelta
    import pytz

    # 设置时区
    TZ = pytz.timezone('Asia/Shanghai')

    # 模拟一个2天前的更新时间
    latest = datetime.now(TZ) - timedelta(days=2)
    print("========模拟一个两天前的时间==============")
    print(latest)
    # 测试是否需要更新数据
    print(should_update_data(latest))

    # 根据更新判断结果输出相应信息
    if should_update_data(latest):
        print(f"需要更新数据，上次更新时间：{latest}")
    else:
        print("没有数据，需要更新数据！")

    conn = connect_db()
    cursor = conn.cursor()
    data = fetch_weather_data("北京", "101010100")
    store_weather_data(conn, cursor, "北京", data)
    print("数据存储完成。")
    update_weather(force_update=True)

    now = datetime.now()
    trigger_time = (now + timedelta(seconds=20)).strftime("%H:%M:%S")

    print(f"[测试日志] 当前时间: {now}")
    print(f"[测试日志] 设置任务在 {trigger_time} 触发 update_weather")

    # 使用 lambda 延迟执行, 避免 schedule.run_pending() 阻塞主线程
    """
    这段代码使用schedule库设置一个每日定时任务。功能是：每天在指定的trigger_time时间点执行一次打印"任务已触发!"的操作。
    具体说明：
        schedule.every().day - 设置每天重复执行
        .at(trigger_time) - 指定具体的执行时间
        .do(lambda: print("任务已触发!")) - 执行的具体操作是打印提示信息
    """
    schedule.every().day.at(trigger_time).do(lambda: print("任务已触发!"))

    # 运行 30 秒以观察任务触发
    end_time = now + timedelta(seconds=60)
    while datetime.now() < end_time:
        schedule.run_pending()
        print(f"[测试日志] 检查待执行任务: {datetime.now()}")
        time.sleep(1)
    setup_scheduler()
