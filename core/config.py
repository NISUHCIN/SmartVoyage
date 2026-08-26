import logging

import os
logger = logging.getLogger(__name__)

# 项目根目录（当前文件在 core/ 下，向上取一级）
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 自动加载 .env 文件（如果 python-dotenv 可用）
_env_path = os.path.join(project_root, '.env')
if os.path.exists(_env_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
    except ImportError:
        pass  # python-dotenv 未安装时，依赖系统环境变量


#定义配置文件
class Config:
    def __init__(self) -> None:
        # 大模型配置（从环境变量读取，提供默认值方便开发）
        self.base_url = os.getenv('LLM_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
        self.api_key = os.getenv('LLM_API_KEY', '')
        self.model_name = os.getenv('LLM_MODEL_NAME', 'qwen-plus')
        self.fast_model_name = os.getenv('LLM_FAST_MODEL', 'qwen-plus')

        # 数据库配置（从环境变量读取）
        self.host = os.getenv('DB_HOST', 'localhost')
        self.user = os.getenv('DB_USER', 'root')
        self.password = os.getenv('DB_PASSWORD', '')
        self.database = os.getenv('DB_NAME', 'travel_rag')
        self.db_port = int(os.getenv('DB_PORT', '3306'))
        self.db_pool_size = int(os.getenv('DB_POOL_SIZE', '8'))

        # 和风天气 API（从环境变量读取）
        self.weather_api_key = os.getenv('WEATHER_API_KEY', '')
        self.qweather_api_host = os.getenv('QWEATHER_API_HOST', '')

        # 服务端口配置
        self.mcp_ticket_port = int(os.getenv('MCP_TICKET_PORT', '8001'))
        self.mcp_weather_port = int(os.getenv('MCP_WEATHER_PORT', '8002'))
        self.mcp_order_port = int(os.getenv('MCP_ORDER_PORT', '8003'))
        self.a2a_weather_port = int(os.getenv('A2A_WEATHER_PORT', '5005'))
        self.a2a_ticket_port = int(os.getenv('A2A_TICKET_PORT', '5006'))
        self.a2a_order_port = int(os.getenv('A2A_ORDER_PORT', '5007'))

        self.mcp_hotel_port = int(os.getenv('MCP_HOTEL_PORT', '8004'))
        self.a2a_hotel_port = int(os.getenv('A2A_HOTEL_PORT', '5008'))
        self.a2a_itinerary_port = int(os.getenv('A2A_ITINERARY_PORT', '5009'))

        # 服务地址（本地默认 localhost，容器部署时通过环境变量指向服务名）
        self.mcp_ticket_url = os.getenv('MCP_TICKET_URL', f'http://localhost:{self.mcp_ticket_port}/mcp')
        self.mcp_weather_url = os.getenv('MCP_WEATHER_URL', f'http://localhost:{self.mcp_weather_port}/mcp')
        self.mcp_order_url = os.getenv('MCP_ORDER_URL', f'http://localhost:{self.mcp_order_port}/mcp')
        self.mcp_hotel_url = os.getenv('MCP_HOTEL_URL', f'http://localhost:{self.mcp_hotel_port}/mcp')
        self.a2a_weather_url = os.getenv('A2A_WEATHER_URL', f'http://localhost:{self.a2a_weather_port}')
        self.a2a_ticket_url = os.getenv('A2A_TICKET_URL', f'http://localhost:{self.a2a_ticket_port}')
        self.a2a_order_url = os.getenv('A2A_ORDER_URL', f'http://localhost:{self.a2a_order_port}')
        self.a2a_hotel_url = os.getenv('A2A_HOTEL_URL', f'http://localhost:{self.a2a_hotel_port}')
        self.a2a_itinerary_url = os.getenv('A2A_ITINERARY_URL', f'http://localhost:{self.a2a_itinerary_port}')

        # 日志配置
        self.log_file = os.path.join(project_root, 'logs', 'app.log')

        # JWT 密钥（用户认证用）
        self.jwt_secret = os.getenv('JWT_SECRET', 'smartvoyage-dev-secret-change-in-production')
        self.jwt_expire_hours = int(os.getenv('JWT_EXPIRE_HOURS', '24'))

if __name__ == '__main__':
   cfg = Config()
   logger.info(cfg.log_file)
   print("日志文件路径：", cfg.log_file)
   print("数据库：", cfg.database)
   print("模型：", cfg.model_name)
   print(f"LLM_API_KEY是否为空: {bool(cfg.api_key)}")
   print(f"_env_path: {_env_path}")
   print(f".env文件是否存在: {os.path.exists(_env_path)}")
