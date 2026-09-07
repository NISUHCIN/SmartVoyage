# SmartVoyage 旅行智能助手项目描述

SmartVoyage 是一个基于 A2A + MCP + LangChain + FastAPI + Vue3 的多 Agent 旅行智能助手。它把天气、火车票、酒店、行程编排拆成独立 A2A Agent，再通过 MCP 工具服务调用真实数据源，最终由 LLM 将结构化结果整合为完整旅行方案。

## 核心能力

- 真实天气查询：和风天气 API，城市名覆盖官方 LocationID 与全国城市经纬度兜底。
- 真实余票查询：聚美智数 / 阿里云为主票源，极速数据为备用票源；接口不可用或返回空时自动切换，仍无结果则降级本地演示班次，保证页面和行程不空白。
- 酒店查询：RollingGo MCP 真实酒店搜索与实时房型，失败时回退本地酒店数据。
- 沙箱下单：火车票与酒店订单写入本地 MySQL，不产生真实扣款或出票；火车订票会同步维护虚拟余票占用，支持取消释放。
- 行程规划：行程 Agent 并行调度天气、去程 / 返程票务、酒店 Agent，再由 LLM 生成结构化多日行程；返程时间冲突时会自动重试或补演示班次。
- 对话与记忆：支持 SSE 流式对话、意图识别路由、跨消息会话记忆 chips。
- 可观测性：API 与对话链路记录执行轨迹，前端可查看 Agent 状态、来源与降级信息。
- 用户体系：注册、登录、会话、订单历史、演示环境复位。

## 技术架构

```
Vue3 前端 (:5173)
  → FastAPI REST API (:8080)
      → 5 个 A2A Agent
          → 4 个 MCP 服务
              → 天气/火车/酒店真实接口、MySQL
```

核心服务包括：

- `weather_server` / `ticket_server` / `order_server` / `hotel_server` / `itinerary_server`：A2A Agent 层
- `mcp_weather_server` / `mcp_ticket_server` / `mcp_order_server` / `mcp_hotel_server`：MCP 工具层
- `api_server.py`：REST 入口，提供直连查询、结构化搜索、沙箱下单、认证与可观测接口
- `chat_service.py`：对话意图识别与 Agent 编排
- MySQL：会话、消息、订单、演示数据与虚拟票占用

## 数据源与降级

表格

| 能力 | 主数据源 | 降级策略 |
| --- | --- | --- |
| 天气 | 和风天气 | MySQL 天气兜底 |
| 火车余票 | 聚美智数 | 极速数据 → 本地演示 |
| 酒店 | RollingGo | MySQL 本地酒店 |
| 火车 / 酒店下单 | 本地沙箱订单 | 不真实扣款 / 出票 |
| 行程生成 | LLM 编排 | 真实数据缺失时自动补演示交通 |

## 技术亮点

- 多协议协同：A2A 负责 Agent 间协作，MCP 封装工具能力，LangChain 负责意图与文本生成。
- 可回退架构：天气、票源、酒店、行程均有降级路径，演示与真实环境均可运行。
- 沙箱安全边界：所有下单均标为 `virtual_demo`，不会触发外部扣款。
- 工程收口：已补充票源切换、会话记忆、执行轨迹、接口测试与文档同步，具备 CI 与 Docker Compose 部署能力。
