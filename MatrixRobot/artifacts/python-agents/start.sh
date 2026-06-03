#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Install dependencies into local venv using uv
if [ ! -d ".venv" ]; then
  echo "[agents] Creating virtual environment..."
  uv venv .venv
fi

echo "[agents] Installing dependencies..."
uv pip install --quiet -r requirements.txt

PORT="${PORT:-8000}"

echo "[agents] Starting FastAPI on port $PORT..."
exec .venv/bin/uvicorn main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --log-level info \
  --no-access-log
