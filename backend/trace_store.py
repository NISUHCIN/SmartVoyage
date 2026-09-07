"""最近执行轨迹的内存环形存储，供 /api/trace 与前端执行轨迹面板读取。"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any

_lock = threading.Lock()
_traces: deque[dict[str, Any]] = deque(maxlen=300)


def record_trace(
    *,
    kind: str,
    message: str = "",
    session_id: str = "",
    intents: list[str] | None = None,
    agents: list[str] | None = None,
    steps: list[dict[str, Any]] | None = None,
    status: str = "ok",
    duration_ms: int = 0,
) -> dict[str, Any]:
    """记录一条可观测轨迹。status 取 ok/warn/error。"""
    entry = {
        "trace_id": uuid.uuid4().hex[:12],
        "kind": kind,
        "message": (message or "")[:120],
        "session_id": session_id,
        "intents": intents or [],
        "agents": agents or [],
        "steps": steps or [],
        "status": status,
        "duration_ms": int(duration_ms),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
    }
    with _lock:
        _traces.appendleft(entry)
    return entry


def list_traces(limit: int = 50) -> list[dict[str, Any]]:
    with _lock:
        return list(_traces)[: max(1, min(int(limit or 50), 200))]


def clear_traces() -> None:
    with _lock:
        _traces.clear()
