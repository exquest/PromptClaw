#!/bin/bash
set -euo pipefail

mkdir -p /opt/pal/logs

/opt/pal/scripts/start_ollama.sh
/opt/pal/scripts/start_router.sh
