"""
sql_safety.py：SQL 安全校验工具，防止 LLM 生成的 SQL 执行危险操作。

核心功能：
    校验 SQL 是否为纯 SELECT 语句。
    拦截 DDL/DML/系统命令等危险操作。
    限制可查询的表白名单。
"""
import re
from typing import Tuple


# 允许查询的表白名单
ALLOWED_TABLES = {
    'weather_data',
    'train_tickets',
    'flight_tickets',
    'concert_tickets',
    'hotel_rooms',
}

# 危险关键词（SQL 注入/未授权操作）
DANGEROUS_PATTERNS = [
    r'\b(insert|update|delete|drop|alter|create|truncate|grant|revoke)\b',
    r'\b(into\s+outfile|load_file|information_schema)\b',
    r';\s*\S',  # 分号后跟内容（多语句注入）
    r'--',      # SQL 注释
    r'/\*.*\*/',
    r'\bunion\s+select\b',  # UNION 注入
]


def validate_select_sql(sql: str, allowed_tables: set = None) -> Tuple[bool, str]:
    """
    校验 SQL 语句安全性。

    Args:
        sql: 待校验的 SQL 字符串
        allowed_tables: 允许查询的表白名单，默认使用全局 ALLOWED_TABLES

    Returns:
        (is_safe, message): 是否安全，以及原因描述
    """
    if not sql or not sql.strip():
        return False, "SQL 为空"

    allowed = allowed_tables or ALLOWED_TABLES
    normalized = sql.strip().lower()

    # 必须以 SELECT 开头
    if not normalized.startswith('select'):
        return False, "仅允许 SELECT 查询"

    # 检查危险关键词
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, normalized):
            return False, f"SQL 包含不允许的操作模式: {pattern}"

    # 检查查询的表是否在白名单内
    table_pattern = r'\bfrom\s+(\w+)|\bjoin\s+(\w+)'
    found_tables = set()
    for match in re.finditer(table_pattern, normalized):
        table = match.group(1) or match.group(2)
        if table:
            found_tables.add(table.lower())

    unallowed = found_tables - allowed
    if unallowed:
        return False, f"查询了不允许的表: {unallowed}"

    return True, "OK"


if __name__ == '__main__':
    # 测试用例
    test_cases = [
        ("SELECT * FROM weather_data WHERE city = '北京'", True),
        ("SELECT * FROM train_tickets WHERE departure_city = '北京'", True),
        ("DROP TABLE weather_data", False),
        ("SELECT * FROM information_schema.tables", False),
        ("SELECT * FROM weather_data; DROP TABLE users", False),
        ("INSERT INTO weather_data VALUES (1)", False),
        ("SELECT * FROM users", False),  # 不在白名单的表
    ]

    for sql, expected in test_cases:
        safe, msg = validate_select_sql(sql)
        status = "PASS" if safe == expected else "FAIL"
        print(f"[{status}] {sql[:60]:60s} -> safe={safe} ({msg})")
