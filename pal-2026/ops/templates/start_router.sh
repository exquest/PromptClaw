#!/bin/bash
set -euo pipefail

ROUTER_DIR=/opt/pal/router
LOG=/opt/pal/logs/router.log
PID_FILE=/opt/pal/logs/router.pid

mkdir -p /opt/pal/logs "$ROUTER_DIR"
cd "$ROUTER_DIR"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
    kill "$(cat "$PID_FILE")"
    sleep 2
fi

pkill -f "uvicorn app:app.*--port 8000" >/dev/null 2>&1 || true

export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
export DEFAULT_MODEL="${DEFAULT_MODEL:-llama3.3:70b-instruct-q4_K_M}"

if [ -x "$ROUTER_DIR/.venv/bin/python" ]; then
    PYTHON="$ROUTER_DIR/.venv/bin/python"
else
    PYTHON=python3
fi

nohup "$PYTHON" -m uvicorn app:app --host 0.0.0.0 --port 8000 > "$LOG" 2>&1 &
echo "$!" > "$PID_FILE"
sleep 3
curl --max-time 10 -fsS http://localhost:8000/health
