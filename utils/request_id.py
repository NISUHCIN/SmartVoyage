"""请求 ID 提取：优先从 A2A HTTP 头读取，其次从消息文本前缀读取。"""
import re

PREFIX_RE = re.compile(r"^\s*\[请求ID[:：]\s*([A-Za-z0-9_-]+)\]\s*\n?")
INLINE_RE = re.compile(r"\[请求ID[:：]\s*([A-Za-z0-9_-]+)\]")


def extract_request_id(conversation: str = "") -> str:
    rid = ""
    try:
        from flask import request as flask_request
        rid = (flask_request.headers.get("X-Request-ID") or "").strip()
    except Exception:
        rid = ""
    if not rid and conversation:
        match = INLINE_RE.search(conversation)
        rid = match.group(1) if match else ""
    return rid


def strip_request_prefix(conversation: str) -> str:
    if not conversation:
        return conversation
    return PREFIX_RE.sub("", conversation).lstrip()
