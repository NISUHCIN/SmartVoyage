"""共享 MySQL 连接池，避免每个查询都新建数据库连接。"""
import threading

import mysql.connector

from core.config import Config


_conf = Config()
_pool = None
_pool_lock = threading.Lock()


def get_connection():
    """从连接池取连接；池不可用时回退为一次性连接。"""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                try:
                    _pool = mysql.connector.pooling.MySQLConnectionPool(
                        pool_name="smartvoyage_pool",
                        pool_size=_conf.db_pool_size,
                        host=_conf.host,
                        user=_conf.user,
                        password=_conf.password,
                        database=_conf.database,
                        port=_conf.db_port,
                        charset="utf8mb4",
                    )
                except Exception:
                    _pool = None
    if _pool is not None:
        try:
            return _pool.get_connection()
        except Exception:
            pass
    return mysql.connector.connect(
        host=_conf.host,
        user=_conf.user,
        password=_conf.password,
        database=_conf.database,
        port=_conf.db_port,
        charset="utf8mb4",
    )
