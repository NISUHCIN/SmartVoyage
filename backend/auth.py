"""
auth.py：用户认证与数据库持久化模块。

核心功能：
    用户注册（密码哈希存储）。
    用户登录（验证密码，签发JWT）。
    JWT 令牌校验。
    会话和消息的数据库持久化（保存/加载对话历史）。
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Optional, Tuple

import jwt

from backend.virtual_bookings import release_by_order_no
from core.config import Config
from core.create_logger import logger
from utils.db import get_connection

conf = Config()


def get_db_connection():
    """从共享连接池获取数据库连接"""
    return get_connection()


# ---------- 密码哈希 ----------

def hash_password(password: str) -> str:
    """使用 PBKDF2-HMAC-SHA256 哈希密码"""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ':' + dk.hex()


def verify_password(password: str, stored_hash: str) -> bool:
    """验证密码"""
    try:
        salt_hex, hash_hex = stored_hash.split(':')
        salt = bytes.fromhex(salt_hex)
        stored_dk = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return hmac.compare_digest(dk, stored_dk)
    except Exception:
        return False


# ---------- JWT 令牌 ----------

def create_token(user_id: int, username: str) -> str:
    """签发 JWT 令牌"""
    now = int(time.time())
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": now + conf.jwt_expire_hours * 3600,
        "iat": now,
    }
    return jwt.encode(payload, conf.jwt_secret, algorithm="HS256")


def verify_token(token: str) -> Optional[dict]:
    """验证 JWT 令牌，返回 payload 或 None"""
    try:
        return jwt.decode(token, conf.jwt_secret, algorithms=["HS256"])
    except Exception:
        return None


# ---------- 用户管理 ----------

def register_user(username: str, password: str, email: str = None, phone: str = None) -> Tuple[bool, str, Optional[dict]]:
    """注册新用户"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            return False, "用户名已存在", None

        password_hash = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, email, phone) VALUES (%s, %s, %s, %s)",
            (username, password_hash, email, phone)
        )
        conn.commit()
        user_id = cursor.lastrowid

        token = create_token(user_id, username)
        return True, "注册成功", {"user_id": user_id, "username": username, "token": token}
    except Exception as e:
        logger.error(f"注册失败: {e}")
        return False, f"注册失败: {str(e)}", None
    finally:
        if conn and conn.is_connected():
            conn.close()


def login_user(username: str, password: str) -> Tuple[bool, str, Optional[dict]]:
    """用户登录"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if not user:
            return False, "用户名或密码错误", None

        if not verify_password(password, user['password_hash']):
            return False, "用户名或密码错误", None

        cursor.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user['id'],))
        conn.commit()

        token = create_token(user['id'], user['username'])
        return True, "登录成功", {
            "user_id": user['id'],
            "username": user['username'],
            "nickname": user.get('nickname'),
            "token": token
        }
    except Exception as e:
        logger.error(f"登录失败: {e}")
        return False, f"登录失败: {str(e)}", None
    finally:
        if conn and conn.is_connected():
            conn.close()


# ---------- 会话持久化 ----------

def create_session(user_id: int = None, title: str = "新对话", session_id: str = None) -> str:
    """创建新的对话会话，返回 session_id"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        session_id = session_id or str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO chat_sessions (session_id, user_id, title) VALUES (%s, %s, %s)",
            (session_id, user_id, title)
        )
        conn.commit()
        return session_id
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            conn.close()


def session_exists(session_id: str) -> bool:
    """判断会话是否存在"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM chat_sessions WHERE session_id = %s", (session_id,))
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"检查会话失败: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def session_belongs_to_user(session_id: str, user_id: int) -> bool:
    """判断会话是否属于指定用户"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM chat_sessions WHERE session_id = %s AND user_id = %s",
            (session_id, user_id)
        )
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"校验会话归属失败: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def save_message(session_id: str, role: str, content: str, intent: str = None, agent_name: str = None):
    """保存一条对话消息到数据库"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_messages (session_id, role, content, intent, agent_name) VALUES (%s, %s, %s, %s, %s)",
            (session_id, role, content, intent, agent_name)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"保存消息失败: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()


def load_session_messages(session_id: str) -> list:
    """加载会话的所有消息"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT role, content, intent, agent_name FROM chat_messages WHERE session_id = %s ORDER BY created_at",
            (session_id,)
        )
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"加载消息失败: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def list_user_sessions(user_id: int) -> list:
    """列出用户的所有会话"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT session_id, title, created_at, updated_at FROM chat_sessions WHERE user_id = %s ORDER BY updated_at DESC",
            (user_id,)
        )
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"列出会话失败: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


# ---------- 订单管理 ----------

def create_order(order_type: str, item_desc: str, quantity: int,
                 unit_price: float, item_id: int = None, user_id: int = None,
                 contact_name: str = None, contact_phone: str = None) -> Tuple[bool, str, Optional[dict]]:
    """在同一事务内创建订单并扣减库存，任一步失败都整体回滚。"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        order_no = str(uuid.uuid4())
        total_price = round(unit_price * quantity, 2)

        table_map = {
            'train': 'train_tickets',
            'flight': 'flight_tickets',
            'concert': 'concert_tickets',
            'hotel': 'hotel_rooms'
        }
        table = table_map.get(order_type)

        if item_id and table:
            col = 'remaining_seats' if table != 'hotel_rooms' else 'remaining_rooms'
            cursor.execute(
                f"SELECT {col} AS remaining FROM {table} WHERE id = %s FOR UPDATE",
                (item_id,)
            )
            item = cursor.fetchone()
            if not item:
                conn.rollback()
                return False, "未找到要预订的记录", None
            if item["remaining"] < quantity:
                conn.rollback()
                return False, f"库存不足，仅剩 {item['remaining']}，需要 {quantity}", None

        cursor.execute(
            """INSERT INTO orders (order_no, user_id, order_type, item_id, item_desc, quantity,
               unit_price, total_price, contact_name, contact_phone, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'confirmed')""",
            (order_no, user_id, order_type, item_id, item_desc, quantity,
             unit_price, total_price, contact_name, contact_phone)
        )

        if item_id and table:
            col = 'remaining_seats' if table != 'hotel_rooms' else 'remaining_rooms'
            cursor.execute(
                f"UPDATE {table} SET {col} = {col} - %s WHERE id = %s AND {col} >= %s",
                (quantity, item_id, quantity)
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return False, "库存不足，下单失败", None

        conn.commit()
        return True, "下单成功", {
            "order_no": order_no,
            "total_price": total_price,
            "status": "confirmed"
        }
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"创建订单失败: {e}")
        return False, f"下单失败: {str(e)}", None
    finally:
        if conn and conn.is_connected():
            conn.close()


def list_user_orders(user_id: int) -> list:
    """列出用户的所有订单"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        )
        rows = cursor.fetchall()
        for row in rows:
            raw = row.get("item_desc")
            item = None
            if isinstance(raw, str) and raw:
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    item = {"raw": raw}
            elif isinstance(raw, dict):
                item = raw
            row["item"] = item
        return rows
    except Exception as e:
        logger.error(f"列出订单失败: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def cancel_order(order_no: str, user_id: int) -> Tuple[bool, str]:
    """取消订单并在同一事务内恢复库存。"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM orders WHERE order_no = %s AND user_id = %s FOR UPDATE",
            (order_no, user_id)
        )
        order = cursor.fetchone()
        if not order:
            return False, "订单不存在"
        if order['status'] != 'confirmed':
            return False, f"订单状态为 {order['status']}，无法取消"

        cursor.execute(
            "UPDATE orders SET status = 'cancelled' WHERE order_no = %s AND status = 'confirmed'",
            (order_no,)
        )
        if cursor.rowcount == 0:
            conn.rollback()
            return False, "订单状态已变更，无法取消"

        table_map = {
            'train': 'train_tickets',
            'flight': 'flight_tickets',
            'concert': 'concert_tickets',
            'hotel': 'hotel_rooms'
        }
        table = table_map.get(order['order_type'])
        if order.get('item_id') and table:
            col = 'remaining_seats' if table != 'hotel_rooms' else 'remaining_rooms'
            cursor.execute(
                f"UPDATE {table} SET {col} = {col} + %s WHERE id = %s",
                (order['quantity'], order['item_id'])
            )
        conn.commit()
        release_by_order_no(order_no)
        return True, "订单已取消"
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"取消订单失败: {e}")
        return False, f"取消失败: {str(e)}"
    finally:
        if conn and conn.is_connected():
            conn.close()
