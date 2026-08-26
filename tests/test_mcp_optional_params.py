import asyncio

from mcp_servers.mcp_hotel_server import create_hotel_mcp_server
from mcp_servers.mcp_order_server import order_mcp
from mcp_servers.mcp_ticket_server import create_ticket_mcp_server
from mcp_servers.mcp_weather_server import create_weather_mcp_server


def _tool_schema(mcp, tool_name):
    tools = asyncio.run(mcp.list_tools())
    for tool in tools:
        if tool.name == tool_name:
            return tool.inputSchema
    raise AssertionError(f"tool not found: {tool_name}")


def _assert_optional(schema, field_names):
    required = schema.get("required", [])
    for name in field_names:
        assert name not in required, f"{name} should be optional"
        prop = schema["properties"][name]
        assert prop.get("default") is None
        assert prop.get("type") == "null" or {"type": "null"} in prop.get("anyOf", [])


def test_ticket_optional_params_accept_none():
    schema = _tool_schema(create_ticket_mcp_server(run=False), "query_train")
    _assert_optional(schema, ["seat_type", "request_id"])


def test_weather_optional_params_accept_none():
    schema = _tool_schema(create_weather_mcp_server(run=False), "query_weather")
    _assert_optional(schema, ["start_date", "end_date", "request_id"])


def test_hotel_optional_params_accept_none():
    schema = _tool_schema(create_hotel_mcp_server(run=False), "query_hotels")
    _assert_optional(
        schema,
        ["district", "room_type", "price_min", "price_max", "rating_min", "request_id"],
    )


def test_order_optional_params_accept_none():
    schema = _tool_schema(order_mcp, "order_train")
    _assert_optional(schema, ["user_id", "request_id"])
