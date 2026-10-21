FROM python:3.11-slim

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 云服务器访问 deb.debian.org 可能超时，构建前切到阿里云 Debian 镜像
RUN set -eux; \
    for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources; do \
        if [ -f "$f" ]; then \
            sed -i -e 's|deb.debian.org|mirrors.aliyun.com|g' \
                   -e 's|security.debian.org|mirrors.aliyun.com|g' "$f"; \
        fi; \
    done; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata libgomp1; \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r /app/backend/requirements.txt

COPY backend/ /app/backend/
# 启动时 init_db 会读取仓库根目录的 sql/init_mysql.sql，需保持 backend/ 与 sql/ 同级
COPY sql/ /app/sql/

RUN mkdir -p /app/backend/logs /app/backend/data/chroma /app/backend/data/knowledge_base

WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)" || exit 1

# 出题与知识库任务队列在进程内维护，必须单 worker；需要横向扩容时应先改为外部任务队列
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
