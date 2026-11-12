FROM python:3.12-slim

# uv resolves from uv.lock, so the image matches the local venv exactly.
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CHEEBOT_DB_PATH=/data/cheebot.db \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY cheebot ./cheebot
COPY scripts ./scripts

RUN uv sync --frozen --no-dev --no-editable \
    && useradd --create-home bot \
    && mkdir -p /data \
    && chown bot:bot /data

USER bot
VOLUME ["/data"]

CMD ["python", "-m", "cheebot"]
