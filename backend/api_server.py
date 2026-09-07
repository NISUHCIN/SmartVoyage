"""
api_server.py：SmartVoyage REST API 服务（FastAPI v2.0），完整接口清单见根目录 CLAUDE.md 第 7 节。

接口模块：
- 认证与会话、对话流式接口
- 天气/票务/酒店/行程直连查询与结构化搜索
- 火车/酒店沙箱下单
- 执行轨迹、会话记忆与演示环境

早期核心接口（仍保留）：
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
import json
import os
import threading
import time
import uuid
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from python_a2a import A2AClient, Message, MessageRole, Task, TextContent

from backend.auth import (
    cancel_order,
    create_session,
    list_user_orders,
    list_user_sessions,
    load_session_messages,
    login_user,
    register_user,
    session_belongs_to_user,
    session_exists,
    verify_token,
)
from backend.chat_service import AGENT_URLS, SmartVoyageChatService
from backend.demo_reset import (
    demo_environment_stats,
    reset_demo_environment,
)
from backend.session_memory import (
    delete_session_memory,
    load_session_memory,
    memory_chips,
)
from backend.trace_store import record_trace
from backend.virtual_bookings import (
    apply_virtual_occupancy,
    create_virtual_hotel_order,
    create_virtual_train_order,
)
from core.config import Config
from core.create_logger import logger
from utils.china_cities import PROVINCE_CITIES
from utils.db import get_connection
from utils.hotel_provider import (
    get_hotel_rooms_structured,
    search_hotels_structured,
)
from utils.mock_travel_provider import query_trains
from utils.query_builders import build_weather_query
from utils.request_id import strip_request_prefix
from utils.train_api_aliyun import AliyunTrainAPIError, query_train_tickets
from utils.weather_api import fetch_and_cache_weather

app = FastAPI(title="SmartVoyage API", version="2.0.0")


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": str(exc.detail), "detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"code": 422, "message": "参数校验失败", "detail": jsonable_encoder(exc.errors())},
    )


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = request_id
    start = time.time()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        f"{request.method} {request.url.path} -> {response.status_code} "
        f"({time.time() - start:.2f}s) rid={request_id}"
    )
    return response


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


class TrainSearchRequest(BaseModel):
    departure_city: str
    arrival_city: str
    travel_date: str
    seat_type: Optional[str] = None


class TrainOrderRequest(BaseModel):
    train: dict
    passenger_name: str
    contact_phone: str
    quantity: int = 1


class HotelSearchRequest(BaseModel):
    city: str
    district: Optional[str] = None
    keyword: Optional[str] = None
    check_in: Optional[str] = None
    nights: int = 1
    adults: int = 2
    budget: Optional[float] = None


class HotelRoomsRequest(BaseModel):
    hotel: dict
    check_in: Optional[str] = None
    nights: int = 1
    adults: int = 2
    rooms: int = 1


class HotelOrderRequest(BaseModel):
    hotel: dict
    room: dict
    check_in: str
    nights: int = 1
    rooms: int = 1
    guest_name: str
    contact_phone: str


class DemoResetRequest(BaseModel):
    session_id: Optional[str] = None


class WeatherSearchRequest(BaseModel):
    city: str
    date: Optional[str] = None
    days: int = 5


_conf = Config()

if _conf.jwt_secret == "smartvoyage-dev-secret-change-in-production" or len(_conf.jwt_secret) < 32:
    logger.warning("JWT_SECRET 强度不足或仍为默认值，生产环境请使用至少 32 位随机密钥。")

_rate_lock = threading.Lock()
_rate_attempts: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 20
REDIS_URL = os.getenv("REDIS_URL", "")


def _in_memory_rate_limit(client_ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        stamps = [s for s in _rate_attempts.get(client_ip, []) if now - s < RATE_LIMIT_WINDOW]
        if len(stamps) >= RATE_LIMIT_MAX:
            return False
        stamps.append(now)
        _rate_attempts[client_ip] = stamps
        if len(_rate_attempts) > 10000:
            for ip in [ip for ip, items in _rate_attempts.items() if not items]:
                del _rate_attempts[ip]
        return True


def _check_rate_limit(client_ip: str) -> bool:
    """限流：配置 REDIS_URL 时使用 Redis 共享计数，否则退回进程内计数。"""
    if not REDIS_URL:
        return _in_memory_rate_limit(client_ip)
    try:
        import redis
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        key = f"smartvoyage:rate:{client_ip}"
        now = int(time.time())
        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, now - RATE_LIMIT_WINDOW)
        pipe.zcard(key)
        count = pipe.execute()[1]
        if count >= RATE_LIMIT_MAX:
            return False
        pipe.zadd(key, {f"{now}-{uuid.uuid4().hex}": now})
        pipe.expire(key, RATE_LIMIT_WINDOW)
        pipe.execute()
        return True
    except Exception:
        return _in_memory_rate_limit(client_ip)

AGENT_DIRECT_URLS = {
    "weather": _conf.a2a_weather_url,
    "ticket": _conf.a2a_ticket_url,
    "ticket-order": _conf.a2a_order_url,
    "hotel": _conf.a2a_hotel_url,
    "itinerary": _conf.a2a_itinerary_url,
}

_agent_clients: dict[str, A2AClient] = {}
_agent_clients_lock = threading.Lock()
_direct_cache: dict[tuple[str, str], tuple[float, str, object]] = {}
_direct_cache_lock = threading.Lock()
DIRECT_CACHE_TTL = int(os.getenv("DIRECT_CACHE_TTL_SECONDS", "10800"))


def _get_agent_client(endpoint: str) -> A2AClient:
    with _agent_clients_lock:
        client = _agent_clients.get(endpoint)
        if client is None:
            client = A2AClient(endpoint, timeout=90)
            _agent_clients[endpoint] = client
        return client


async def call_agent_direct(endpoint: str, message: str, request_id: str = "",
                            cacheable: bool = True) -> tuple[str, object]:
    cache_message = strip_request_prefix(message)
    key = (endpoint, cache_message)
    if cacheable:
        with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached and time.time() - cached[0] < DIRECT_CACHE_TTL:
                return cached[1], cached[2]

    client = _get_agent_client(endpoint)
    if request_id:
        message = f"[请求ID: {request_id}]\n{message}"
    task = Task(
        id="api-" + uuid.uuid4().hex,
        message=Message(content=TextContent(text=message), role=MessageRole.USER).to_dict(),
    )
    result = await client.send_task_async(task)
    structured = None
    state = result.status.state
    if state == "completed" and result.artifacts:
        artifact = result.artifacts[0]
        parts = artifact["parts"] if isinstance(artifact, dict) else artifact.parts
        part = parts[0]
        reply = part["text"] if isinstance(part, dict) else part.text
        if len(parts) > 1:
            try:
                second = parts[1]
                structured = json.loads(second["text"] if isinstance(second, dict) else second.text)
            except Exception:
                structured = None
    else:
        msg = result.status.message
        if isinstance(msg, dict) and "content" in msg:
            content = msg["content"]
            reply = content.get("text", "") if isinstance(content, dict) else str(content)
        else:
            reply = "未返回可展示的结果"

    if cacheable and state == "completed" and reply and reply.strip():
        with _direct_cache_lock:
            _direct_cache[key] = (time.time(), reply, structured)
            if len(_direct_cache) > 500:
                expired = [k for k, v in _direct_cache.items() if time.time() - v[0] >= DIRECT_CACHE_TTL]
                for k in expired:
                    del _direct_cache[k]
    return reply, structured


def auth_required(request: Request, authorization: Optional[str] = Header(None)) -> int:
    """从请求头提取并验证 JWT，返回 user_id"""
    token = request.cookies.get("sv_token")
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(401, "未提供认证令牌")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(401, "认证令牌无效或已过期")
    return payload["user_id"]


def _set_auth_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(
        "sv_token", token,
        httponly=True, samesite="lax", path="/",
        max_age=_conf.jwt_expire_hours * 3600
    )


@app.post("/api/register")
async def register(req: RegisterRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(429, "请求过于频繁，请稍后再试")
    if len(req.username) < 3:
        raise HTTPException(400, "用户名至少3个字符")
    if len(req.password) < 6:
        raise HTTPException(400, "密码至少6个字符")
    success, msg, data = register_user(req.username, req.password, req.email, req.phone)
    if not success:
        raise HTTPException(400, msg)
    token = (data or {}).get("token")
    if token:
        data = {k: v for k, v in data.items() if k != "token"}
    response = JSONResponse({"code": 0, "message": msg, "data": data})
    if token:
        _set_auth_cookie(response, token)
    return response


@app.post("/api/login")
async def login(req: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(429, "请求过于频繁，请稍后再试")
    success, msg, data = login_user(req.username, req.password)
    if not success:
        raise HTTPException(401, msg)
    token = (data or {}).get("token")
    if token:
        data = {k: v for k, v in data.items() if k != "token"}
    response = JSONResponse({"code": 0, "message": msg, "data": data})
    if token:
        _set_auth_cookie(response, token)
    return response


@app.get("/api/me")
async def me(request: Request):
    payload = _current_user(request)
    if not payload:
        raise HTTPException(401, "未登录")
    return {"code": 0, "data": {
        "user_id": payload["user_id"],
        "username": payload.get("username", ""),
    }}


@app.post("/api/logout")
async def logout():
    response = JSONResponse({"code": 0, "message": "已退出登录"})
    response.delete_cookie("sv_token", path="/")
    return response


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


async def _db_ok() -> bool:
    """MySQL 连通性检查"""
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
            return True
        finally:
            conn.close()
    except Exception:
        return False


async def _probe_agents() -> dict:
    results = await asyncio.gather(*(_agent_is_online(url) for url in AGENT_URLS.values()))
    return {"online": sum(1 for ok in results if ok), "total": len(results)}


@app.get("/api/health")
async def health():
    db_status = "ok" if await _db_ok() else "error"
    try:
        agents = await asyncio.wait_for(_probe_agents(), timeout=2.0)
    except asyncio.TimeoutError:
        agents = {"online": 0, "total": len(AGENT_URLS)}
    return {
        "code": 0,
        "status": "ok",
        "service": "SmartVoyage API v2.0",
        "db": db_status,
        "agents": agents,
    }


@app.get("/api/cities")
async def cities():
    data = [{"province": name, "cities": cities} for name, cities in PROVINCE_CITIES.items()]
    return {"code": 0, "data": data}


def _resolve_chat_session(session_id: Optional[str], user_id: Optional[int]) -> str:
    session_id = session_id or "default"
    if user_id:
        if session_id == "default" or not session_belongs_to_user(session_id, user_id):
            created = create_session(user_id, "新对话")
            if created:
                session_id = created
    elif session_id == "default" or not session_exists(session_id):
        created = create_session(
            None, "新对话", session_id=None if session_id == "default" else session_id
        )
        if created:
            session_id = created
    return session_id


def _current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("sv_token")
    if not token:
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            token = authorization.split(" ", 1)[1]
    if token:
        return verify_token(token)
    return None


def _chat_user_id(request: Request) -> Optional[int]:
    payload = _current_user(request)
    return payload["user_id"] if payload else None


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request, authorization: Optional[str] = Header(None)):
    if not req.message.strip():
        raise HTTPException(400, "消息不能为空")
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(429, "请求过于频繁，请稍后再试")
    user_id = _chat_user_id(request)
    session_id = _resolve_chat_session(req.session_id, user_id)

    service = get_chat_service()
    reply = await asyncio.to_thread(
        service.process, req.message.strip(), session_id, user_id,
        request_id=request.state.request_id
    )
    return {"code": 0, "data": {"reply": reply, "session_id": session_id}}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request,
                      authorization: Optional[str] = Header(None)):
    if not req.message.strip():
        raise HTTPException(400, "消息不能为空")
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(429, "请求过于频繁，请稍后再试")
    user_id = _chat_user_id(request)
    session_id = _resolve_chat_session(req.session_id, user_id)
    service = get_chat_service()

    async def event_source():
        async for event in service.stream_process(
            req.message.strip(), session_id, user_id,
            request_id=request.state.request_id
        ):
            payload = {"session_id": session_id, **event}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request.state.request_id,
        },
    )


@app.get("/api/agents")
async def agents():
    async def probe(name: str, url: str) -> dict:
        online = await _agent_is_online(url)
        return {"name": name, "url": url, "status": "online" if online else "offline"}

    data = await asyncio.gather(
        *(probe(name, url) for name, url in AGENT_URLS.items())
    )
    return {"code": 0, "data": data}


async def _agent_is_online(url: str) -> bool:
    """通过 A2A 的 /agent.json 端点探测 Agent 是否存活。"""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{url}/agent.json")
            return resp.status_code == 200
    except Exception:
        return False


def _weather_rows_from_db(city: str, start_date: str, end_date: str) -> list:
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        sql, params = build_weather_query(city, start_date, end_date)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cursor.close()
        return rows
    except Exception as exc:
        logger.warning(f"读取本地天气兜底失败: {exc}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


@app.post("/api/weather")
async def weather(req: AgentRequest, request: Request):
    reply, data = await call_agent_direct(
        AGENT_DIRECT_URLS["weather"], req.message, request_id=request.state.request_id
    )
    return {"code": 0, "data": {"reply": reply, "data": data}}


@app.post("/api/ticket")
async def ticket(req: AgentRequest, request: Request):
    reply, data = await call_agent_direct(
        AGENT_DIRECT_URLS["ticket"], req.message, request_id=request.state.request_id
    )
    return {"code": 0, "data": {"reply": reply, "data": data}}


@app.post("/api/ticket-order")
async def ticket_order(req: AgentRequest, request: Request, authorization: Optional[str] = Header(None)):
    message = req.message
    payload = _current_user(request)
    if payload:
        message = f"{message}\n用户ID: {payload['user_id']}"
    # 下单是写操作，不能复用查询缓存，否则重复下单/取消后重订会拿到旧结果。
    reply, data = await call_agent_direct(
        AGENT_DIRECT_URLS["ticket-order"], message,
        request_id=request.state.request_id, cacheable=False
    )
    return {"code": 0, "data": {"reply": reply, "data": data}}


@app.post("/api/hotel")
async def hotel(req: AgentRequest, request: Request):
    reply, data = await call_agent_direct(
        AGENT_DIRECT_URLS["hotel"], req.message, request_id=request.state.request_id
    )
    return {"code": 0, "data": {"reply": reply, "data": data}}


@app.post("/api/itinerary")
async def itinerary(req: AgentRequest, request: Request):
    reply, data = await call_agent_direct(
        AGENT_DIRECT_URLS["itinerary"], req.message, request_id=request.state.request_id
    )
    return {"code": 0, "data": {"reply": reply, "data": data}}


@app.post("/api/demo/login")
async def demo_login():
    """面试演示账号：首次运行自动注册，之后直接登录。"""
    username = "demo_user"
    password = "SmartVoyageDemo@2026"
    ok, message, payload = login_user(username, password)
    if not ok:
        ok, message, payload = register_user(username, password)
    if not ok:
        raise HTTPException(400, message)
    response = JSONResponse(
        {"code": 0, "data": {"username": username, "mode": "interview_demo"}}
    )
    _set_auth_cookie(response, payload["token"])
    return response


@app.post("/api/trains/search")
async def trains_search(req: TrainSearchRequest, request: Request):
    """真实余票查询；真实票源无数据时降级本地演示班次，避免查询页空白。"""
    started = time.perf_counter()
    status = "ok"
    degraded = False
    fallback_message = ""
    try:
        rows = query_train_tickets(
            req.departure_city,
            req.arrival_city,
            req.travel_date,
            seat_type=req.seat_type,
            request_id=request.state.request_id,
        )
    except AliyunTrainAPIError as exc:
        logger.error(f"真实票源查询失败: {exc}")
        fallback_message = str(exc)
        rows = []
    if not rows:
        rows = query_trains(req.departure_city, req.arrival_city, req.travel_date)
        if req.seat_type:
            rows = [row for row in rows if row["seat_type"] == req.seat_type]
        if rows:
            for row in rows:
                row["source"] = "本地演示数据"
                row["_provider"] = "demo"
            degraded = True
            status = "warn"
            fallback_message = fallback_message or "真实票源暂无可订余票，已展示本地演示班次。"
    apply_virtual_occupancy(rows)
    source = (
        str(rows[0].get("source") or "聚美智数/阿里云")
        if rows
        else (
            "真实票源暂无结果"
        )
    )
    record_trace(
        kind="train_direct",
        message=f"{req.departure_city} → {req.arrival_city} {req.travel_date} {req.seat_type or ''}",
        steps=[{
            "step": "真实余票查询",
            "agent": "TicketQueryAssistant/MCP票务",
            "status": status,
            "source": source,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "degraded": degraded,
        }],
        status=status,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    return {
        "code": 0,
        "data": {
            "rows": rows,
            "source": source,
            "message": fallback_message or None,
            "booking_mode": "virtual_demo",
            "meta": {
                "cache_ttl_seconds": 120,
                "rate_max_per_minute": 12,
                "degraded": degraded,
            },
        },
    }


@app.post("/api/orders/train")
async def train_order(req: TrainOrderRequest, request: Request):
    """按真实班次生成沙箱虚拟订单，不产生真实出票。"""
    payload = _current_user(request)
    user_id = payload["user_id"] if payload else None
    ok, message, data = create_virtual_train_order(
        req.train,
        req.quantity,
        user_id,
        req.passenger_name,
        req.contact_phone,
    )
    if not ok:
        raise HTTPException(400, message)
    return {"code": 0, "data": data}


@app.get("/api/demo/status")
async def demo_status():
    db_ok = await _db_ok()
    stats = await asyncio.to_thread(demo_environment_stats)
    rollinggo = bool(
        Path(__file__).resolve().parent.parent.joinpath(".mcp.json").exists()
    )
    return {
        "code": 0,
        "data": {
            "db": db_ok,
            "agents_configured": len(AGENT_URLS),
            "rollinggo_configured": rollinggo,
            "train_source_configured": bool(
                os.getenv("ALIYUN_APPCODE") and os.getenv("ALIYUN_TRAIN_API_URL")
            ),
            "weather_source_configured": bool(
                os.getenv("WEATHER_API_KEY") and os.getenv("QWEATHER_API_HOST")
            ),
            **stats,
        },
    }


@app.post("/api/demo/reset")
async def demo_reset(req: DemoResetRequest):
    result = await asyncio.to_thread(reset_demo_environment)
    if result.get("status") != "ok":
        raise HTTPException(400, result.get("message", "演示数据复位失败"))
    if req.session_id:
        await asyncio.to_thread(delete_session_memory, req.session_id)
        result["memory_cleared"] = True
    return {"code": 0, "message": "沙箱订单已清空，虚拟占用已释放", "data": result}


@app.post("/api/hotels/search")
async def hotels_search(req: HotelSearchRequest, request: Request):
    """真实酒店搜索（RollingGo），失败降级本地演示房型。"""
    if not req.city.strip():
        raise HTTPException(400, "请提供城市")
    started = time.perf_counter()
    result = await search_hotels_structured(
        req.city.strip(),
        check_in=req.check_in,
        nights=req.nights,
        adults=req.adults,
        district=req.district,
        room_type=req.keyword,
        max_price=req.budget,
        request_id=request.state.request_id,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    record_trace(
        kind="hotel_direct",
        message=f"{req.city} 酒店 {req.check_in or '未指定日期'} {req.nights}晚",
        steps=[{
            "step": "酒店真实搜索",
            "agent": "HotelQueryAssistant/RollingGo MCP",
            "status": "ok" if not result.get("degraded") else "warn",
            "source": result.get("source", ""),
            "duration_ms": duration_ms,
            "degraded": bool(result.get("degraded")),
        }],
        status="ok" if not result.get("degraded") else "warn",
        duration_ms=duration_ms,
    )
    return {"code": 0, "data": result}


@app.post("/api/hotels/rooms")
async def hotels_rooms(req: HotelRoomsRequest, request: Request):
    """选中酒店后查询实时房型与价格。"""
    if not req.hotel:
        raise HTTPException(400, "请先选择酒店")
    started = time.perf_counter()
    result = await get_hotel_rooms_structured(
        req.hotel,
        req.check_in or (req.hotel.get("check_in") or ""),
        req.nights,
        req.adults,
        req.rooms,
        request_id=request.state.request_id,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    record_trace(
        kind="hotel_room_direct",
        message=f"{req.hotel.get('hotel_name')} 房型查询",
        steps=[{
            "step": "酒店房型实时查询",
            "agent": "HotelQueryAssistant/RollingGo MCP",
            "status": "ok" if not result.get("degraded") else "warn",
            "source": result.get("source", ""),
            "duration_ms": duration_ms,
            "degraded": bool(result.get("degraded")),
        }],
        status="ok" if not result.get("degraded") else "warn",
        duration_ms=duration_ms,
    )
    return {"code": 0, "data": result}


@app.post("/api/orders/hotel")
async def hotel_order(req: HotelOrderRequest, request: Request):
    """按真实酒店房型生成沙箱虚拟酒店订单。"""
    if not req.guest_name.strip() or not req.contact_phone.strip():
        raise HTTPException(400, "请填写入住人姓名和联系电话")
    if req.nights < 1 or req.rooms < 1:
        raise HTTPException(400, "入住晚数和房间数至少为 1")
    payload = _current_user(request)
    user_id = payload["user_id"] if payload else None
    ok, message, data = create_virtual_hotel_order(
        req.hotel,
        req.room,
        req.check_in,
        req.nights,
        req.rooms,
        user_id,
        req.guest_name.strip(),
        req.contact_phone.strip(),
    )
    if not ok:
        raise HTTPException(400, message)
    record_trace(
        kind="hotel_order",
        message=f"{req.hotel.get('hotel_name')} {req.room.get('room_type')} 沙箱预订",
        steps=[{
            "step": "虚拟酒店订单",
            "agent": "本地沙箱订单服务",
            "status": "ok",
            "source": "virtual_demo",
            "degraded": False,
            "duration_ms": 0,
        }],
    )
    return {"code": 0, "message": message, "data": data}


@app.post("/api/weather/search")
async def weather_search(req: WeatherSearchRequest, request: Request):
    """和风天气真实 7 天预报结构化查询，供行程时间线直接渲染。"""
    city = req.city.strip()
    if not city:
        raise HTTPException(400, "请提供城市")
    started = time.perf_counter()
    from datetime import date as date_type
    from datetime import datetime, timedelta

    start = req.date or date_type.today().isoformat()
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD")
    end_dt = start_dt + timedelta(days=max(1, min(int(req.days or 5), 7)) - 1)
    result = await asyncio.to_thread(fetch_and_cache_weather, city)
    degraded = result.get("status") != "success"
    if not degraded:
        rows = [
            day for day in (result.get("data") or [])
            if start_dt <= datetime.strptime(day["fxDate"], "%Y-%m-%d").date() <= end_dt
        ]
        source = "和风天气真实接口"
    else:
        rows = await asyncio.to_thread(
            _weather_rows_from_db, city, start_dt.isoformat(), end_dt.isoformat()
        )
        source = "本地天气数据"
    duration_ms = int((time.perf_counter() - started) * 1000)
    record_trace(
        kind="weather_direct",
        message=f"{city} {start_dt} 起 {req.days} 天",
        steps=[{
            "step": "结构化天气查询",
            "agent": "WeatherQueryAssistant/和风天气",
            "status": "ok" if not degraded else "warn",
            "source": source,
            "duration_ms": duration_ms,
            "degraded": degraded,
        }],
        status="ok" if not degraded else "warn",
        duration_ms=duration_ms,
    )
    return {"code": 0, "data": {"rows": rows, "source": source, "degraded": degraded}}


@app.get("/api/trace")
async def trace(limit: int = 50):
    from backend.trace_store import list_traces
    return {"code": 0, "data": list_traces(limit)}


@app.get("/api/session-memory/{session_id}")
async def session_memory(session_id: str):
    memory = await asyncio.to_thread(load_session_memory, session_id)
    return {
        "code": 0,
        "data": {
            "memory": memory,
            "chips": memory_chips(memory),
        },
    }


_WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
if _WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
