ARG BASE_IMAGE_NODE=node:20-alpine
ARG BASE_IMAGE_PYTHON=python:3.11-slim

# 前端构建阶段
FROM ${BASE_IMAGE_NODE} AS web-build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
ARG NPM_REGISTRY=https://registry.npmjs.org/
RUN npm ci --registry=$NPM_REGISTRY --no-audit --no-fund \
    || npm install --registry=$NPM_REGISTRY --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM ${BASE_IMAGE_PYTHON}

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url $PIP_INDEX_URL --timeout 60 --retries 5 -r requirements.txt

# 复制项目文件
COPY . .

# 复制前端构建产物，让 API 服务在 8080 同时提供前端页面
COPY --from=web-build /app/web/dist ./web/dist

# 创建日志目录
RUN mkdir -p logs

EXPOSE 8001 8002 8003 8004 5005 5006 5007 5008 5009 8080 8501

# 默认启动 API Server，docker-compose 中会覆盖
CMD ["python", "backend/api_server.py"]
