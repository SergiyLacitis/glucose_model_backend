#!/bin/sh

set -e

echo "[entrypoint] Running database migrations..."
uv run --no-dev alembic upgrade head

echo "[entrypoint] Starting application..."
exec uv run --no-dev python src/main.py
