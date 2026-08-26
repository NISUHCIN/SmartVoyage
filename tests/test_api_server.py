import asyncio
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.api_server import app
import backend.api_server as api_server
from backend.auth import create_token
from backend import chat_service


class _FakeA2AResult:
    def __init__(self, text: str):
        self.status = type("Status", (), {"state": "completed"})()
        self.artifacts = [{"parts": [{"type": "text", "text": text}]}]


class _FakeA2AClient:
    def __init__(self):
        self.calls = 0

    async def send_task_async(self, task):
        self.calls += 1
        return _FakeA2AResult("fake reply")


class ApiServerTest(unittest.TestCase):
    def setUp(self):
        self._real_service = api_server._chat_service
        api_server._chat_service = _FakeChatService()
        self.client = TestClient(app)

    def tearDown(self):
        api_server._chat_service = self._real_service

    def test_health(self):
        with mock.patch.object(api_server, "_db_ok", new=mock.AsyncMock(return_value=True)), \
                mock.patch.object(api_server, "_agent_is_online", return_value=False):
            res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["code"], 0)
        self.assertEqual(body["db"], "ok")
        self.assertEqual(body["agents"], {"online": 0, "total": 5})

    def test_cities(self):
        res = self.client.get("/api/cities")
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(len(data), 34)
        self.assertTrue(any("北京" in item["cities"] for item in data))

    def test_agents(self):
        res = self.client.get("/api/agents")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["data"]), 5)

    def test_agents_reports_offline_when_unreachable(self):
        with mock.patch.object(api_server, "_agent_is_online", return_value=False):
            res = self.client.get("/api/agents")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(all(item["status"] == "offline" for item in res.json()["data"]))

    def test_agents_reports_online_when_reachable(self):
        with mock.patch.object(api_server, "_agent_is_online", return_value=True):
            res = self.client.get("/api/agents")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(all(item["status"] == "online" for item in res.json()["data"]))

    def test_static_dist_path_points_to_web_dist(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(api_server._WEB_DIST, root / "web" / "dist")
        self.assertTrue((root / "web" / "dist" / "index.html").exists())

    def test_request_id_header_added(self):
        res = self.client.get("/api/health")
        self.assertIn("x-request-id", res.headers)
        self.assertTrue(res.headers["x-request-id"])

    def test_rate_limit_blocks_after_max(self):
        api_server._rate_attempts.clear()
        for _ in range(20):
            self.assertTrue(api_server._check_rate_limit("1.2.3.4"))
        self.assertFalse(api_server._check_rate_limit("1.2.3.4"))

    def test_me_requires_auth(self):
        res = self.client.get("/api/me")
        self.assertEqual(res.status_code, 401)

    def test_logout_clears_cookie(self):
        res = self.client.post("/api/logout")
        self.assertEqual(res.status_code, 200)
        set_cookie = res.headers.get("set-cookie", "")
        self.assertIn("sv_token=", set_cookie)

    def test_chat(self):
        res = self.client.post("/api/chat", json={"message": "北京今天天气", "session_id": "verify"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["code"], 0)
        self.assertEqual(body["data"]["reply"], "mock reply")
        self.assertEqual(body["data"]["session_id"], "verify")
        self.assertIsNone(api_server._chat_service.last_user_id)

    def test_chat_authenticated_creates_owned_session(self):
        token = create_token(42, "tester")
        with mock.patch.object(api_server, "session_belongs_to_user", return_value=False), \
                mock.patch.object(api_server, "create_session", return_value="new-session-1"):
            res = self.client.post(
                "/api/chat",
                json={"message": "帮我订票"},
                headers={"Authorization": f"Bearer {token}"},
            )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["data"]["reply"], "mock reply")
        self.assertEqual(body["data"]["session_id"], "new-session-1")
        self.assertEqual(api_server._chat_service.last_user_id, 42)
        self.assertEqual(api_server._chat_service.last_session_id, "new-session-1")

    def test_chat_guest_creates_session_when_missing(self):
        with mock.patch.object(api_server, "session_exists", return_value=False), \
                mock.patch.object(api_server, "create_session", return_value="guest-session-1") as create:
            res = self.client.post("/api/chat", json={"message": "你好", "session_id": "web-abc"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["data"]["session_id"], "guest-session-1")
        create.assert_called_once_with(None, "新对话", session_id="web-abc")

    def test_chat_stream_returns_sse_events(self):
        with self.client.stream(
            "POST", "/api/chat/stream",
            json={"message": "北京今天天气", "session_id": "verify"}
        ) as res:
            self.assertEqual(res.status_code, 200)
            self.assertIn("text/event-stream", res.headers["content-type"])
            body = res.read().decode("utf-8")
        self.assertIn('"delta": "你好"', body)
        self.assertIn('"done": true', body)
        self.assertEqual(api_server._chat_service.last_session_id, "verify")

    def test_ticket_order_disables_direct_cache(self):
        with mock.patch.object(
            api_server, "call_agent_direct", new=mock.AsyncMock(return_value=("ok", None))
        ) as call:
            res = self.client.post("/api/ticket-order", json={"message": "订一张北京到上海的票"})
        self.assertEqual(res.status_code, 200)
        call.assert_awaited_once()
        self.assertFalse(call.await_args.kwargs["cacheable"])

    def test_weather_keeps_direct_cache_enabled(self):
        with mock.patch.object(
            api_server, "call_agent_direct", new=mock.AsyncMock(return_value=("ok", None))
        ) as call:
            res = self.client.post("/api/weather", json={"message": "北京天气"})
        self.assertEqual(res.status_code, 200)
        call.assert_awaited_once()
        self.assertTrue(call.await_args.kwargs.get("cacheable", True))

    def test_chat_rate_limited(self):
        with mock.patch.object(api_server, "_check_rate_limit", return_value=False):
            res = self.client.post("/api/chat", json={"message": "北京天气", "session_id": "verify"})
        self.assertEqual(res.status_code, 429)

    def test_chat_stream_rate_limited(self):
        with mock.patch.object(api_server, "_check_rate_limit", return_value=False):
            res = self.client.post("/api/chat/stream", json={"message": "北京天气", "session_id": "verify"})
        self.assertEqual(res.status_code, 429)


def test_call_agent_direct_only_caches_cacheable_requests():
    api_server._direct_cache.clear()
    client = _FakeA2AClient()
    with mock.patch.object(api_server, "_get_agent_client", return_value=client):
        asyncio.run(api_server.call_agent_direct("ep-cache", "同一条查询"))
        asyncio.run(api_server.call_agent_direct("ep-cache", "同一条查询"))
        asyncio.run(api_server.call_agent_direct("ep-cache", "同一条查询", cacheable=False))
    assert client.calls == 2
    api_server._direct_cache.clear()


def test_call_agent_direct_reuses_client_and_strips_request_id_from_cache_key():
    api_server._direct_cache.clear()
    client = _FakeA2AClient()
    with mock.patch.object(api_server, "_get_agent_client", return_value=client):
        asyncio.run(api_server.call_agent_direct("ep-reuse", "北京天气", request_id="rid-1"))
        asyncio.run(api_server.call_agent_direct("ep-reuse", "北京天气", request_id="rid-2"))
    assert client.calls == 1
    api_server._direct_cache.clear()


class _FakeChatService:
    def __init__(self):
        self.last_user_id = None
        self.last_session_id = None

    def process(self, user_input, session_id="default", user_id=None, request_id=""):
        self.last_user_id = user_id
        self.last_session_id = session_id
        return "mock reply"

    async def stream_process(self, user_input, session_id="default", user_id=None, request_id=""):
        self.last_user_id = user_id
        self.last_session_id = session_id
        yield {"delta": "你好"}
        yield {"done": True, "session_id": session_id}


if __name__ == "__main__":
    unittest.main()
