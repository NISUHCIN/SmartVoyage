import logging

import requests
import json
logger = logging.getLogger(__name__)

# 配置（使用自己的密钥）
API_KEY = "918272564eb14cd99caa0e1081894c5d"
url = "https://j246h349g7.re.qweatherapi.com/v7/weather/30d?location=101010100"  # 北京30天预报
headers = {
    "X-QW-Api-Key": API_KEY,
    "Accept-Encoding": "gzip"  # 请求gzip，但不强制
}
try:
    logger.info("正在请求API...")
    response = requests.get(url, headers=headers, timeout=10)
    data = response.text
    parsed_data = json.loads(data)
    logger.info("直接解析成功！")
    logger.info(parsed_data)
except requests.RequestException as e:
    logger.info(f"直接解析失败哦: {e}")