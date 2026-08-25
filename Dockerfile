FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建日志目录
RUN mkdir -p logs

EXPOSE 8001 8002 8003 8004 5005 5006 5007 5008 5009 8080 8501

# 默认启动 API Server，docker-compose 中会覆盖
CMD ["python", "backend/api_server.py"]
