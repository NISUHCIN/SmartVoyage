"""
api_server.py：SmartVoyage REST API 服务，提供用户认证和会话管理接口。

核心接口：
    POST /api/register       - 用户注册
    POST /api/login          - 用户登录
    GET  /api/sessions       - 获取用户会话列表
    POST /api/sessions       - 创建新会话
    GET  /api/messages/{sid} - 获取会话消息历史
    GET  /api/orders         - 获取用户订单列表
    POST /api/orders/cancel  - 取消订单
    GET  /api/health         - 健康检查
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import os
import threading
import time
import uuid

from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from core.create_logger import logger
from backend.auth import (
    register_user, login_user, verify_token,
    create_session, load_session_messages,
    list_user_sessions, list_user_orders, cancel_order
)
from backend.chat_service import AGENT_URLS, SmartVoyageChatService
from python_a2a import A2AClient, Message, TextContent, MessageRole, Task
from utils.china_cities import PROVINCE_CITIES

app = FastAPI(title="SmartVoyage API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


_chat_service = None
_chat_service_lock = threading.Lock()


def get_chat_service() -> SmartVoyageChatService:
    global _chat_service
    with _chat_service_lock:
        if _chat_service is None:
            _chat_service = SmartVoyageChatService()
    return _chat_service


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    phone: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class SessionRequest(BaseModel):
    title: str = "新对话"


class CancelOrderRequest(BaseModel):
    order_no: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class AgentRequest(BaseModel):
    message: str


AGENT_DIRECT_URLS = {
    "weather": "http://localhost:5005",
    "ticket": "http://localhost:5006",
    "ticket-order": "http://localhost:5007",
    "hotel": "http://localhost:5008",
    "itinerary": "http://localhost:5009",
}

_agent_clients: dict[str, A2AClient] = {}
_agent_clients_lock = threading.Lock()
_direct_cache: dict[tuple[str, str], tuple[float, str]] = {}
_direct_cache_lock = threading.Lock()
DIRECT_CACHE_TTL = int(os.getenv("DIRECT_CACHE_TTL_SECONDS", "10800"))


def _get_agent_client(endpoint: str) -> A2AClient:
    with _agent_clients_lock:
        client = _agent_clients.get(endpoint)
        if client is None:
            client = A2AClient(endpoint, timeout=90)
            _agent_clients[endpoint] = client
        return client


async def call_agent_direct(endpoint: str, message: str) -> str:
    key = (endpoint, message)
    with _direct_cache_lock:
        cached = _direct_cache.get(key)
        if cached and time.time() - cached[0] < DIRECT_CACHE_TTL:
            return cached[1]

    client = _get_agent_client(endpoint)
    task = Task(
        id="api-" + uuid.uuid4().hex,
        message=Message(content=TextContent(text=message), role=MessageRole.USER).to_dict(),
    )
    result = await client.send_task_async(task)
    if result.status.state == "completed" and result.artifacts:
        artifact = result.artifacts[0]
        parts = artifact["parts"] if isinstance(artifact, dict) else artifact.parts
        part = parts[0]
        reply = part["text"] if isinstance(part, dict) else part.text
    else:
        msg = result.status.message
        if isinstance(msg, dict) and "content" in msg:
            content = msg["content"]
            reply = content.get("text", "") if isinstance(content, dict) else str(content)
        else:
            reply = "未返回可展示的结果"

    with _direct_cache_lock:
        _direct_cache[key] = (time.time(), reply)
    return reply


def auth_required(authorization: Optional[str] = Header(None)) -> int:
    """从请求头提取并验证 JWT，返回 user_id"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "未提供认证令牌")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(401, "认证令牌无效或已过期")
    return payload["user_id"]


@app.post("/api/register")
async def register(req: RegisterRequest):
    if len(req.username) < 3:
        raise HTTPException(400, "用户名至少3个字符")
    if len(req.password) < 6:
        raise HTTPException(400, "密码至少6个字符")
    success, msg, data = register_user(req.username, req.password, req.email, req.phone)
    if not success:
        raise HTTPException(400, msg)
    return {"code": 0, "message": msg, "data": data}


@app.post("/api/login")
async def login(req: LoginRequest):
    success, msg, data = login_user(req.username, req.password)
    if not success:
        raise HTTPException(401, msg)
    return {"code": 0, "message": msg, "data": data}


@app.get("/api/sessions")
async def get_sessions(user_id: int = Depends(auth_required)):
    return {"code": 0, "data": list_user_sessions(user_id)}


@app.post("/api/sessions")
async def create_new_session(req: SessionRequest, user_id: int = Depends(auth_required)):
    session_id = create_session(user_id, req.title)
    if not session_id:
        raise HTTPException(500, "创建会话失败")
    return {"code": 0, "data": {"session_id": session_id}}


@app.get("/api/messages/{session_id}")
async def get_messages(session_id: str, user_id: int = Depends(auth_required)):
    return {"code": 0, "data": load_session_messages(session_id)}


@app.get("/api/orders")
async def get_orders(user_id: int = Depends(auth_required)):
    return {"code": 0, "data": list_user_orders(user_id)}


@app.post("/api/orders/cancel")
async def cancel_user_order(req: CancelOrderRequest, user_id: int = Depends(auth_required)):
    success, msg = cancel_order(req.order_no, user_id)
    if not success:
        raise HTTPException(400, msg)
    return {"code": 0, "message": msg}


@app.get("/api/health")
async def health():
    return {"code": 0, "status": "ok", "service": "SmartVoyage API v2.0"}


@app.get("/api/cities")
async def cities():
    data = [{"province": name, "cities": cities} for name, cities in PROVINCE_CITIES.items()]
    return {"code": 0, "data": data}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "消息不能为空")
    session_id = req.session_id or "default"
    service = get_chat_service()
    reply = await asyncio.to_thread(service.process, req.message.strip(), session_id)
    return {"code": 0, "data": {"reply": reply, "session_id": session_id}}


@app.get("/api/agents")
async def agents():
    data = [
        {"name": name, "url": url, "status": "online"}
        for name, url in AGENT_URLS.items()
    ]
    return {"code": 0, "data": data}


@app.post("/api/weather")
async def weather(req: AgentRequest):
    reply = await call_agent_direct(AGENT_DIRECT_URLS["weather"], req.message)
    return {"code": 0, "data": {"reply": reply}}


@app.post("/api/ticket")
async def ticket(req: AgentRequest):
    reply = await call_agent_direct(AGENT_DIRECT_URLS["ticket"], req.message)
    return {"code": 0, "data": {"reply": reply}}


@app.post("/api/ticket-order")
async def ticket_order(req: AgentRequest):
    reply = await call_agent_direct(AGENT_DIRECT_URLS["ticket-order"], req.message)
    return {"code": 0, "data": {"reply": reply}}


@app.post("/api/hotel")
async def hotel(req: AgentRequest):
    reply = await call_agent_direct(AGENT_DIRECT_URLS["hotel"], req.message)
    return {"code": 0, "data": {"reply": reply}}


@app.post("/api/itinerary")
async def itinerary(req: AgentRequest):
    reply = await call_agent_direct(AGENT_DIRECT_URLS["itinerary"], req.message)
    return {"code": 0, "data": {"reply": reply}}


_WEB_DIST = Path(__file__).parent / "web" / "dist"
if _WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
