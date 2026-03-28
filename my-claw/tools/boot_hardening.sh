#!/usr/bin/env bash
# CypherClaw Server Boot Hardening
# Run on boot via systemd to prevent I/O saturation crashes

set -euo pipefail
LOG="/var/log/cypherclaw-boot.log"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG"; }

log "=== CypherClaw boot hardening started ==="

# 1. Kill any stale agent processes from before crash
log "Killing stale agents..."
pkill -9 -f "claude.*agent\|codex.*agent\|gemini.*agent" 2>/dev/null || true
pkill -9 -f "sdp-cli run" 2>/dev/null || true

# 2. Clear stale lock files
rm -f /run/cypherclaw-tmp/workdir/cypherclaw-work/.sdp/run.lock 2>/dev/null || true
log "Cleared stale locks"

# 3. Ensure tmpfs directories exist
mkdir -p /run/cypherclaw-tmp/workdir
mkdir -p /run/cypherclaw-tmp/cache
log "tmpfs directories verified"

# 4. Set CPU governor to performance
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo performance > "$cpu" 2>/dev/null || true
done
log "CPU governor set to performance"

# 5. Set I/O scheduler to mq-deadline (better for SSD under load)
for disk in /sys/block/sd*/queue/scheduler; do
    echo mq-deadline > "$disk" 2>/dev/null || true
done
log "I/O scheduler set to mq-deadline"

# 6. Tune ext4 for less journal pressure
mount -o remount,commit=60,noatime / 2>/dev/null || true
log "ext4 tuned: commit=60, noatime"

# 7. Set process limits to prevent CPU saturation
# Max 8 agent processes at once (leaves headroom on 12 threads)
# This is enforced by the daemon's semaphore, but belt-and-suspenders
cat > /etc/security/limits.d/cypherclaw.conf << 'LIMITS'
user    soft    nproc    256
user    hard    nproc    512
LIMITS
log "Process limits configured"

# 8. Disable console screen blanking (for gallery display)
setterm -blank 0 -powerdown 0 --term linux < /dev/tty1 2>/dev/null || true
log "Screen blanking disabled"

# 9. Verify critical services
for svc in redis-server postgresql ollama; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        log "$svc: running"
    else
        log "$svc: NOT running — attempting start"
        systemctl start "$svc" 2>/dev/null || log "Failed to start $svc"
    fi
done

# 10. Restore state.db from backup if tmpfs copy is missing
TMPFS_STATE="/run/cypherclaw-tmp/workdir/cypherclaw-work/.promptclaw/state.db"
BACKUP_STATE="/home/user/cypherclaw/.promptclaw/state.db.backup"
if [ ! -f "$TMPFS_STATE" ] && [ -f "$BACKUP_STATE" ]; then
    cp "$BACKUP_STATE" "$TMPFS_STATE"
    log "Restored state.db from backup"
fi

# 11. Start sdp-cli pipeline with safety limits (after 30s delay for services to settle)
(sleep 30 && cd /run/cypherclaw-tmp/workdir/cypherclaw-work && \
 ionice -c3 nice -n19 /home/user/.local/bin/sdp-cli run >> /tmp/sdp-pipeline.log 2>&1 &) &
log "Scheduled sdp-cli pipeline start (30s delay)"

log "=== Boot hardening complete ==="
