import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import Config


def test_service_url_defaults():
    cfg = Config()
    assert cfg.a2a_weather_url == "http://localhost:5005"
    assert cfg.a2a_ticket_url == "http://localhost:5006"
    assert cfg.a2a_order_url == "http://localhost:5007"
    assert cfg.a2a_hotel_url == "http://localhost:5008"
    assert cfg.a2a_itinerary_url == "http://localhost:5009"
    assert cfg.mcp_ticket_url == "http://localhost:8001/mcp"
    assert cfg.mcp_weather_url == "http://localhost:8002/mcp"
    assert cfg.mcp_order_url == "http://localhost:8003/mcp"
    assert cfg.mcp_hotel_url == "http://localhost:8004/mcp"


def test_service_url_env_override(monkeypatch):
    monkeypatch.setenv("A2A_TICKET_URL", "http://a2a-ticket:5006")
    monkeypatch.setenv("A2A_ITINERARY_URL", "http://a2a-itinerary:5009")
    monkeypatch.setenv("MCP_TICKET_URL", "http://mcp-ticket:8001/mcp")
    monkeypatch.setenv("MCP_HOTEL_URL", "http://mcp-hotel:8004/mcp")

    cfg = Config()
    assert cfg.a2a_ticket_url == "http://a2a-ticket:5006"
    assert cfg.a2a_itinerary_url == "http://a2a-itinerary:5009"
    assert cfg.mcp_ticket_url == "http://mcp-ticket:8001/mcp"
    assert cfg.mcp_hotel_url == "http://mcp-hotel:8004/mcp"
