FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependencies first for layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000

# One image, three roles (override the command):
#   API (default)   uvicorn, below
#   worker          celery -A app.workers.celery_app worker --loglevel=info
#   beat            celery -A app.workers.celery_app beat --loglevel=info
# Migrations run once per deploy as their own task (`alembic upgrade head`),
# never on every container start, so replicas can't race each other.
# Client IPs for rate limiting come from X-Forwarded-For (TRUSTED_PROXY_COUNT).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health/live' % os.environ.get('PORT', '8000'), timeout=3)" || exit 1
# PORT is set by hosts such as Render; 8000 everywhere else (AWS, compose).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
