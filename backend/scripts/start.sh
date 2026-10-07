#!/bin/sh
# Container entrypoint for the API.
# MIGRATE_ON_START=true applies database migrations first (hosts without a
# separate release step, e.g. Render's free plan). Elsewhere migrations run as
# their own one-off task, so replicas never race each other.
set -e

if [ "${MIGRATE_ON_START:-false}" = "true" ]; then
  echo "Applying database migrations..."
  alembic upgrade head
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
