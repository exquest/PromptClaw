#!/bin/bash
set -euo pipefail

LOG=/opt/pal/logs/ollama.log
PID_FILE=/opt/pal/logs/ollama.pid

mkdir -p /opt/pal/logs /opt/pal/ollama

if pgrep -f "ollama serve" >/dev/null 2>&1; then
    echo "Ollama is already running."
    exit 0
fi

export OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0:11434}"
export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:-30m}"
export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}"
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-2}"
export OLLAMA_MODELS="${OLLAMA_MODELS:-/opt/pal/ollama}"

nohup ollama serve > "$LOG" 2>&1 &
echo "$!" > "$PID_FILE"
sleep 2
curl --max-time 10 -fsS http://localhost:11434/api/version
