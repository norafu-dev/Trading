# 构建 Python 采集与 API 镜像；development 阶段包含 Ruff 和测试依赖。
FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
RUN pip install --no-cache-dir uv==0.11.28
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
COPY backend/alembic.ini ./alembic.ini
COPY backend/migrations ./migrations
RUN uv sync --frozen --no-dev && useradd --uid 10001 --create-home collector

FROM base AS development
RUN uv sync --frozen
COPY backend/tests ./tests
USER collector
CMD ["trading", "check"]

FROM base AS runtime
USER collector
CMD ["trading", "collect"]
