# SmartVoyage Docker 部署指南

## 前置条件

- Docker 20.10+
- Docker Compose 2.0+

## 部署步骤

### 1. 准备环境配置

```bash
cp .env.example .env
# 编辑 .env，填入你的 API 密钥和数据库密码
```

### 2. 一键启动

```bash
docker compose up -d --build
```

这会自动：
- 启动 MySQL 数据库（自动建表+插入数据）
- 启动 4 个 MCP 服务
- 启动 5 个 A2A Agent 服务
- 启动 REST API 服务
- 启动 Vue 前端

### 3. 访问服务

| 服务 | 地址 |
|------|------|
| 前端界面 | http://localhost:5173 |
| API 接口 | http://localhost:8080/docs |
| MySQL | localhost:3306 |

### 4. 查看日志

```bash
# 查看所有服务
docker compose logs -f

# 查看特定服务
docker compose logs -f frontend
docker compose logs -f a2a-weather
```

### 5. 停止服务

```bash
docker compose down

# 同时删除数据卷（清空数据库）
docker compose down -v
```

## 架构说明

```
用户浏览器
    │
    ├── Vue 前端 (:5173)
    └── REST API (:8080)
         │
    ┌────┴──── A2A Agent 层 ────┐
    │ WeatherAgent  (:5005)     │
    │ TicketAgent   (:5006)     │
    │ OrderAgent    (:5007)     │
    │ HotelAgent    (:5008)     │
    │ ItineraryAgent (:5009)    │
    └────┬──── MCP 工具层 ──────┘
         │
    ┌────┴──────────────────────┐
    │ TicketMCP  (:8001)        │
    │ WeatherMCP (:8002)        │
    │ OrderMCP   (:8003)        │
    │ HotelMCP   (:8004)        │
    └────┬──────────────────────┘
         │
     MySQL (:3306)
```
