import asyncio
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import chat_service
from backend.chat_service import (
    SmartVoyageChatService,
    _looks_like_itinerary,
    _trim_history,
    collapse_redundant_intents,
)
from core.config import Config


def test_trim_history_keeps_recent_lines():
    text = "\n".join(f"User: 消息{i}" for i in range(10))
    assert _trim_history(text, max_lines=3) == "\n".join(f"User: 消息{i}" for i in range(7, 10))


def test_trim_history_short_text_unchanged():
    assert _trim_history("User: 北京", max_lines=10) == "User: 北京"


def test_looks_like_itinerary_detects_travel_planning():
    assert _looks_like_itinerary("重庆到西安周末两日游")
    assert _looks_like_itinerary("帮我规划北京3天游")
    assert _looks_like_itinerary("上海5天行程安排")


def test_looks_like_itinerary_rejects_greeting():
    assert not _looks_like_itinerary("你好")
    assert not _looks_like_itinerary("今天天气怎么样")


def test_collapse_redundant_intents_keeps_only_itinerary():
    assert collapse_redundant_intents(
        ["itinerary", "train", "hotel", "attraction"]
    ) == ["itinerary"]


def test_collapse_redundant_intents_keeps_order_with_itinerary():
    assert collapse_redundant_intents(["itinerary", "order"]) == ["itinerary", "order"]


def test_collapse_redundant_intents_preserves_unrelated_intents():
    assert collapse_redundant_intents(["weather", "flight"]) == ["weather", "flight"]


class _FakeAgentResult:
    def __init__(self, text: str):
        self.status = type("Status", (), {"state": "completed"})()
        self.artifacts = [{"parts": [{"type": "text", "text": text}]}]


class _FakeAgent:
    def __init__(self):
        self.last_message = ""

    async def send_task_async(self, task):
        self.last_message = task.message["content"]["text"]
        return _FakeAgentResult("代理返回")


class _FakeNetwork:
    def __init__(self, agent):
        self._agent = agent

    def get_agent(self, agent_name):
        return self._agent


class _FakePrompt:
    def __or__(self, other):
        return other


class _StreamingAgent:
    async def stream_response(self, message):
        yield "代理返回"


def test_process_uses_db_history_for_persisted_session(monkeypatch):
    rows = [
        {"role": "user", "content": "北京今天天气"},
        {"role": "assistant", "content": "北京晴"},
        {"role": "user", "content": "那上海呢"},
    ]
    monkeypatch.setattr(chat_service, "load_session_messages", lambda session_id: rows)
    monkeypatch.setattr(chat_service, "session_exists", lambda session_id: True)
    monkeypatch.setattr(chat_service, "save_message", lambda *args, **kwargs: None)

    service = SmartVoyageChatService.__new__(SmartVoyageChatService)
    service.conf = Config()
    service.llm = None
    service._session_history = {}
    service._lock = threading.Lock()
    fake_agent = _FakeAgent()
    service.agent_network = _FakeNetwork(fake_agent)

    captured = {}

    def fake_intent(user_input, session_id, history=None):
        captured["history"] = history
        return ["weather"], {"weather": "北京今天天气"}, ""

    service._intent_agent = fake_intent
    fake_summary = type("FakeSummary", (), {"content": "天气总结"})()
    monkeypatch.setattr(
        chat_service.SmartVoyagePrompts, "summarize_weather_prompt", lambda: _FakePrompt()
    )
    monkeypatch.setattr(chat_service, "_invoke_with_retry", lambda chain, inputs: fake_summary)

    reply = service.process("北京今天天气", session_id="db-session-1", user_id=7)

    assert "User: 北京今天天气" in captured["history"]
    assert "Assistant: 北京晴" in captured["history"]
    assert "Assistant: 北京晴" in fake_agent.last_message
    assert reply == "天气总结"


def test_stream_process_does_not_duplicate_itinerary_reply(monkeypatch):
    monkeypatch.setattr(chat_service, "load_session_messages", lambda session_id: [])
    monkeypatch.setattr(chat_service, "session_exists", lambda session_id: True)
    monkeypatch.setattr(chat_service, "save_message", lambda *args, **kwargs: None)

    service = SmartVoyageChatService.__new__(SmartVoyageChatService)
    service.conf = Config()
    service.llm = None
    service._session_history = {}
    service._lock = threading.Lock()
    agent = _StreamingAgent()
    monkeypatch.setattr(chat_service, "A2AClient", lambda *args, **kwargs: agent)

    def fake_intent(user_input, session_id, history=None):
        return ["itinerary"], {"itinerary": "规划北京3天游"}, ""

    service._intent_agent = fake_intent

    deltas = []

    async def run():
        async for event in service.stream_process("规划北京3天游", session_id="s1", user_id=1):
            if event.get("delta"):
                deltas.append(event["delta"])

    asyncio.run(run())
    assert deltas == ["代理返回"]
