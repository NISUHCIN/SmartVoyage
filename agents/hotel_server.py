"""
hotel_server.py：酒店代理服务器，使用 LLM 生成 SQL 查询 MCP 酒店工具，返回用户友好文本结果。

核心功能：
    初始化 LLM 和 MCP 客户端。
    生成 SQL，调用 MCP。
    解析 JSON 结果，返回格式化文本。
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from typing import Any
import json
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, TaskState
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from datetime import datetime
import pytz
from core.config import Config
from core.create_logger import logger
from utils.china_cities import detect_city

conf = Config()

llm = ChatOpenAI(
    model=conf.fast_model_name,
    base_url=conf.base_url,
    api_key=conf.api_key,
    temperature=0.1,
    extra_body={"enable_thinking": False}
)

table_schema_string = """CREATE TABLE hotel_rooms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hotel_name VARCHAR(100) NOT NULL COMMENT '酒店名称',
    city VARCHAR(50) NOT NULL COMMENT '所在城市',
    district VARCHAR(50) COMMENT '所在区域',
    address VARCHAR(200) COMMENT '酒店地址',
    room_type VARCHAR(50) NOT NULL COMMENT '房型',
    bed_type VARCHAR(30) COMMENT '床型',
    price DECIMAL(10, 2) NOT NULL COMMENT '每晚价格',
    total_rooms INT NOT NULL COMMENT '总房间数',
    remaining_rooms INT NOT NULL COMMENT '剩余房间数',
    check_in_time TIME COMMENT '入住时间',
    check_out_time TIME COMMENT '退房时间',
    rating DECIMAL(2, 1) COMMENT '评分1.0-5.0',
    has_wifi TINYINT(1) COMMENT 'WiFi',
    has_breakfast TINYINT(1) COMMENT '早餐',
    has_parking TINYINT(1) COMMENT '停车场'
);
"""

sql_prompt = ChatPromptTemplate.from_template(
    """
系统提示：你是一个专业的酒店SQL生成器，需要从对话历史（含用户的问题）中提取关键信息，然后基于hotel_rooms表生成SELECT语句。
- 如果用户需要查酒店，则至少需要城市信息。如果对话历史中缺乏必要的信息，可以向其追问，输出格式为json格式；如果对话历史中信息齐全，则输出纯SQL即可。
- 可以根据用户的偏好（价格范围、区域、房型、评分等）来生成更精确的查询。
- 如果查询中有价格范围要求，使用 price 字段做范围查询。
- 如果查询中有评分要求，使用 rating 字段做筛选，注意 rating >= 某个值。
- 默认按价格升序排列。

示例：
- 对话: user: 北京的酒店
输出: SELECT hotel_name, city, district, room_type, bed_type, price, remaining_rooms, rating, has_breakfast FROM hotel_rooms WHERE city = '北京' ORDER BY price ASC
- 对话: user: 上海 500到1000元的酒店
输出: SELECT hotel_name, city, district, room_type, bed_type, price, remaining_rooms, rating, has_breakfast FROM hotel_rooms WHERE city = '上海' AND price BETWEEN 500 AND 1000 ORDER BY price ASC
- 对话: user: 广州天河区的大床房
输出: SELECT hotel_name, city, district, room_type, bed_type, price, remaining_rooms, rating, has_breakfast FROM hotel_rooms WHERE city = '广州' AND district = '天河区' AND room_type LIKE '%大床房%' ORDER BY price ASC
- 对话: user: 深圳评分4.5以上的酒店
输出: SELECT hotel_name, city, district, room_type, bed_type, price, remaining_rooms, rating, has_breakfast FROM hotel_rooms WHERE city = '深圳' AND rating >= 4.5 ORDER BY price ASC
- 对话: user: 你好
输出: {{"status": "input_required", "message": "请提供城市信息，例如 '北京的酒店'。"}}

hotel_rooms表结构：{table_schema_string}
对话历史: {conversation}
当前日期: {current_date} (Asia/Shanghai)
    """
)


async def get_hotel(sql: Any) -> Any:
    try:
        async with streamablehttp_client("http://127.0.0.1:8004/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                try:
                    await session.initialize()
                    result = await session.call_tool("query_hotels", {"sql": sql})
                    result_data = json.loads(result) if isinstance(result, str) else result
                    logger.info(f"酒店查询结果：{result_data}")
                    return result_data.content[0].text
                except Exception as e:
                    logger.error(f"酒店 MCP 查询出错：{str(e)}")
                    return json.dumps({"status": "error", "message": f"酒店 MCP 查询出错：{str(e)}"})
    except Exception as e:
        logger.error(f"连接或会话初始化时发生错误: {e}")
        return json.dumps({"status": "error", "message": "连接或会话初始化时发生错误"})


def _rollinggo_hotel_conf():
    cfg_path = Path(__file__).resolve().parent.parent / ".mcp.json"
    if not cfg_path.exists():
        return None
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        for conf in data.get("mcpServers", {}).values():
            if conf.get("url", "").rstrip("/") == "https://mcp.rollinggo.cn/mcp":
                return conf
    except Exception as e:
        logger.warning(f"读取 .mcp.json 失败: {e}")
    return None


async def search_rollinggo_hotels(conversation: str) -> str | None:
    """调用 RollingGo 酒店 MCP 搜索真实酒店，失败返回 None。"""
    conf = _rollinggo_hotel_conf()
    if not conf:
        return None
    city = detect_city(conversation) or conversation.strip()
    if not city:
        return None
    try:
        async with streamablehttp_client(conf["url"], headers=conf.get("headers", {})) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("searchHotels", {
                    "place": city,
                    "originQuery": conversation,
                })
                text = result.content[0].text
                data = json.loads(text)
                if not data.get("success"):
                    return None
                hotels = data.get("hotelInformationList", [])[:10]
                lines = []
                for hotel in hotels:
                    price = (hotel.get("price") or {}).get("lowestPrice")
                    price_text = f"{price}元/晚" if price else "价格待查"
                    lines.append(
                        f"{hotel.get('name', '')}（{city}）：{hotel.get('starRating', '')}星，"
                        f"{price_text}，地址：{hotel.get('address', '')}"
                    )
                return "\n".join(lines) if lines else None
    except Exception as e:
        logger.warning(f"RollingGo 酒店接口异常: {e}")
        return None


agent_card = AgentCard(
    name="HotelQueryAssistant",
    description="基于LangChain提供酒店查询服务的助手",
    url="http://localhost:5008",
    version="1.0.0",
    capabilities={"streaming": True, "memory": True},
    skills=[
        AgentSkill(
            name="execute hotel query",
            description="执行酒店查询，返回酒店房间信息，支持自然语言输入",
            examples=["北京的酒店", "上海500到1000元的酒店", "广州天河区的大床房"]
        )
    ]
)


class HotelQueryServer(A2AServer):
    def __init__(self) -> None:
        super().__init__(agent_card=agent_card)
        self.llm = llm
        self.sql_prompt = sql_prompt
        self.schema = table_schema_string

    def generate_sql_query(self, conversation: str) -> dict:
        try:
            chain = self.sql_prompt | self.llm
            current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
            output = chain.invoke({"conversation": conversation, "current_date": current_date, "table_schema_string": self.schema}).content.strip()
            logger.info(f"原始 LLM 输出: {output}")

            if output.startswith('{'):
                return json.loads(output)
            return {"status": "sql", "sql": output}
        except Exception as e:
            logger.error(f"SQL生成失败: {str(e)}")
            return {"status": "input_required", "message": "查询无效，请提供城市信息。"}

    def handle_task(self, task: Any) -> Any:
        content = (task.message or {}).get("content", {})
        conversation = content.get("text", "") if isinstance(content, dict) else ""
        logger.info(f"对话历史及用户问题: {conversation}")

        try:
            rollinggo_text = asyncio.run(search_rollinggo_hotels(conversation))
            if rollinggo_text:
                logger.info("酒店查询使用 RollingGo 真实接口结果")
                task.artifacts = [{"parts": [{"type": "text", "text": rollinggo_text}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
                return task
        except Exception as e:
            logger.warning(f"RollingGo 酒店查询失败，回退本地库: {e}")

        try:
            gen_result = self.generate_sql_query(conversation)
            if gen_result["status"] == "input_required":
                task.status = TaskStatus(state=TaskState.INPUT_REQUIRED,
                                         message={"role": "agent", "content": {"text": gen_result["message"]}})
                return task

            sql_query = gen_result["sql"]
            logger.info(f"生成的SQL查询: {sql_query}")

            hotel_result = asyncio.run(get_hotel(sql_query))
            response = json.loads(hotel_result) if isinstance(hotel_result, str) else hotel_result
            logger.info(f"MCP 返回: {response}")

            if response.get("status") == "success":
                data = response.get("data", [])
                response_text = "\n".join([
                    f"{d['hotel_name']}（{d['city']}{d.get('district', '')}）：{d['room_type']}，{d.get('bed_type', '')}，每晚{d['price']}元，剩余{d['remaining_rooms']}间，评分{d['rating']}{'，含早' if d.get('has_breakfast') else ''}"
                    for d in data])

                task.artifacts = [{"parts": [{"type": "text", "text": response_text}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
            elif response.get("status") == "no_data":
                response_text = response.get("message", "请重新输入查询的城市。")
                task.status = TaskStatus(state=TaskState.INPUT_REQUIRED,
                                         message={"role": "agent", "content": {"text": response_text}})
            else:
                response_text = response.get("message", "查询失败，请重试或提供更多细节。")
                task.status = TaskStatus(state=TaskState.FAILED,
                                         message={"role": "agent", "content": {"text": response_text}})
            return task
        except Exception as e:
            logger.error(f"查询失败: {str(e)}")
            task.status = TaskStatus(state=TaskState.FAILED,
                                     message={"role": "agent", "content": {"text": f"查询失败: {str(e)} 请重试或提供更多细节。"}})
            return task


if __name__ == "__main__":
    hotel_server = HotelQueryServer()
    logger.info("\n=== 服务器信息 ===")
    logger.info(f"名称: {hotel_server.agent_card.name}")
    logger.info(f"描述: {hotel_server.agent_card.description}")
    logger.info("\n技能:")
    for skill in hotel_server.agent_card.skills:
        logger.info(f"- {skill.name}: {skill.description}")
    run_server(hotel_server, host="127.0.0.1", port=5008)
