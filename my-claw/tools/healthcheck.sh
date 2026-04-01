#!/bin/bash
# CypherClaw health check — only restart on real problems
LOG="${HEALTHCHECK_LOG:-/home/user/cypherclaw/tools/cypherclaw_daemon.log}"
DAEMON_PATTERN="${HEALTHCHECK_DAEMON_PATTERN:-python3.*cypherclaw_daemon.py}"
AGENT_PATTERN="${HEALTHCHECK_AGENT_PATTERN:-claude|codex|gemini}"
PROC_ROOT="${HEALTHCHECK_PROC_ROOT:-/proc}"

# Check: at least 1 daemon process (match python3 specifically)
PID_COUNT=$(pgrep -c -f "$DAEMON_PATTERN")
if [ "$PID_COUNT" -eq 0 ]; then
    echo "UNHEALTHY: daemon not running"
    exit 1
fi
if [ "$PID_COUNT" -gt 1 ]; then
    echo "UNHEALTHY: $PID_COUNT daemon processes"
    exit 1
fi

# Check: no D-state python processes (more than 2 = problem)
DSTATE=$(ps aux | grep python3 | grep " D " | grep -v grep | wc -l)
if [ "$DSTATE" -gt 2 ]; then
    echo "UNHEALTHY: $DSTATE processes in D-state"
    exit 1
fi

# Check: daemon process is not zombie
DAEMON_PID=$(pgrep -f "$DAEMON_PATTERN" | head -1)
if [ -d "$PROC_ROOT/$DAEMON_PID" ]; then
    STATE=$(cat "$PROC_ROOT/$DAEMON_PID/status" 2>/dev/null | grep "^State:" | awk '{print $2}')
    if [ "$STATE" = "Z" ]; then
        echo "UNHEALTHY: daemon is zombie"
        exit 1
    fi
fi

# If agent processes are running, daemon is working — don't restart!
AGENTS=$(pgrep -f "$AGENT_PATTERN" 2>/dev/null | wc -l | tr -d ' ')
if [ "$AGENTS" -gt 0 ]; then
    echo "HEALTHY: daemon running with $AGENTS active agents"
    exit 0
fi

# Only check log staleness when no agents are running
LAST_LOG=$(stat -c %Y "$LOG" 2>/dev/null || echo 0)
NOW=$(date +%s)
AGE=$((NOW - LAST_LOG))
if [ "$AGE" -gt 900 ]; then
    echo "UNHEALTHY: log not updated in ${AGE}s and no agents running"
    exit 1
fi

echo "HEALTHY: 1 daemon, log age ${AGE}s"
exit 0
