#!/bin/bash
# PAL 2026 Auto-Shutdown Script
# Runs every 5 minutes via cron, checks if it is time to shut down.

CONFIG=/opt/pal/config/shutdown.conf
LOG=/opt/pal/logs/shutdown.log

mkdir -p "$(dirname "$LOG")"
source "$CONFIG"

if [ "$ENABLED" != "true" ]; then
    echo "$(date): Auto-shutdown disabled, skipping." >> "$LOG"
    exit 0
fi

if [ -f "$OVERRIDE_FILE" ]; then
    echo "$(date): Override flag present, skipping shutdown." >> "$LOG"
    exit 0
fi

CURRENT_TIME=$(TZ=$TIMEZONE date +%H:%M)
SHUTDOWN_HOUR=$(echo "$SHUTDOWN_TIME" | cut -d: -f1)
SHUTDOWN_MIN=$(echo "$SHUTDOWN_TIME" | cut -d: -f2)
CURRENT_HOUR=$(echo "$CURRENT_TIME" | cut -d: -f1)
CURRENT_MIN=$(echo "$CURRENT_TIME" | cut -d: -f2)

SHUTDOWN_HOUR=$((10#$SHUTDOWN_HOUR))
SHUTDOWN_MIN=$((10#$SHUTDOWN_MIN))
CURRENT_HOUR=$((10#$CURRENT_HOUR))
CURRENT_MIN=$((10#$CURRENT_MIN))

if [ "$CURRENT_HOUR" = "$SHUTDOWN_HOUR" ] && \
   [ "$CURRENT_MIN" -ge "$SHUTDOWN_MIN" ] && \
   [ "$CURRENT_MIN" -lt $((SHUTDOWN_MIN + 5)) ]; then
    echo "$(date): Shutdown time reached. Stopping services and powering down." >> "$LOG"
    cd /opt/pal && docker compose down
    sleep 5
    shutdown -h now
fi
