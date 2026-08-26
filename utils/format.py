import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

# ---------- 关键：先配置日志，才能看到 info ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]  # 输出到控制台
)
logger = logging.getLogger(__name__)


def default_encoder(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(obj, date):
        return obj.strftime('%Y-%m-%d')
    if isinstance(obj, timedelta):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    return obj


class DateEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (date, datetime)):
            return obj.strftime('%Y-%m-%d %H:%M:%S') if isinstance(obj, datetime) else obj.strftime('%Y-%m-%d')
        if isinstance(obj, timedelta):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


if __name__ == '__main__':
    logger.info(default_encoder(datetime(2025, 8, 11, 8, 0)))
    logger.info(default_encoder(date(2025, 8, 11)))
    logger.info(default_encoder(timedelta(days=1)))
    logger.info(default_encoder(Decimal('123.45')))
    logger.info('*' * 80)

    encoder = DateEncoder()
    logger.info(encoder.default(datetime(2025, 8, 11, 8, 0)))
    logger.info(encoder.default(date(2025, 8, 11)))
    logger.info(encoder.default(timedelta(days=1)))
    logger.info(encoder.default(Decimal('123.45')))