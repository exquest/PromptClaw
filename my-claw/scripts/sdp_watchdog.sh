#!/bin/bash
#
# SDP Runner Watchdog
# ===================
#
# Runs every 5 minutes via cron. Alerts via Telegram if the SDP pipeline
# is stuck — so we never silently lose hours of dev time again.
#
# Alert conditions (any one triggers):
#   1. systemd unit `cypherclaw-sdp-runner.service` is not active
#   2. sdp-cli process not found at all
#   3. Circuit breaker is open
#   4. No new task_runs in the last 45 minutes (pipeline stalled)
#   5. Restart counter >= 10 in the last hour (hot-loop)
#
# Alerts are rate-limited to one per hour per condition to avoid spam.
#
# Install:
#   cp sdp_watchdog.sh /home/user/cypherclaw/scripts/
#   chmod +x /home/user/cypherclaw/scripts/sdp_watchdog.sh
#   crontab -e
#   # Add:  */5 * * * * /home/user/cypherclaw/scripts/sdp_watchdog.sh

set -uo pipefail

readonly STATE_DIR="/tmp/sdp-watchdog"
readonly LOG_FILE="${STATE_DIR}/watchdog.log"
readonly STATE_DB="/home/user/cypherclaw/.sdp/state.db"
readonly ALERT_COOLDOWN_SECONDS=3600  # 1 hour between alerts per condition
readonly STALL_THRESHOLD_MINUTES=45   # no task_runs for this long = stalled
readonly TELEGRAM_SCRIPT="/home/user/cypherclaw/src/cypherclaw/telegram.py"

mkdir -p "$STATE_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# Alert with cooldown. First arg: condition name. Second: message.
alert() {
    local condition="$1"
    local message="$2"
    local cooldown_file="${STATE_DIR}/${condition}.last_alert"
    local now=$(date +%s)

    if [[ -f "$cooldown_file" ]]; then
        local last=$(cat "$cooldown_file")
        local elapsed=$((now - last))
        if (( elapsed < ALERT_COOLDOWN_SECONDS )); then
            log "SUPPRESSED [$condition]: $message (${elapsed}s since last alert)"
            return 0
        fi
    fi

    log "ALERT [$condition]: $message"
    echo "$now" > "$cooldown_file"

    # Send via telegram.py
    if [[ -f "$TELEGRAM_SCRIPT" ]]; then
        /usr/bin/python3 "$TELEGRAM_SCRIPT" send "⚠️ CypherClaw SDP Watchdog: ${message}" >> "$LOG_FILE" 2>&1 || true
    fi
}

ok() {
    local condition="$1"
    local cooldown_file="${STATE_DIR}/${condition}.last_alert"
    if [[ -f "$cooldown_file" ]]; then
        # Clear the cooldown so recovery is announced on next failure
        rm -f "$cooldown_file"
        log "RECOVERED [$condition]"
        if [[ -f "$TELEGRAM_SCRIPT" ]]; then
            /usr/bin/python3 "$TELEGRAM_SCRIPT" send "✅ CypherClaw SDP Watchdog: ${condition} recovered" >> "$LOG_FILE" 2>&1 || true
        fi
    fi
}

# ═══════════════════════════════════════════════════════════════════
# Check 1: systemd unit active
# ═══════════════════════════════════════════════════════════════════
check_systemd_active() {
    if systemctl is-active cypherclaw-sdp-runner.service &>/dev/null; then
        ok "systemd_inactive"
        return 0
    fi
    local state=$(systemctl show -p ActiveState --value cypherclaw-sdp-runner.service 2>/dev/null || echo unknown)
    alert "systemd_inactive" "cypherclaw-sdp-runner.service is not active (state=${state})"
    return 1
}

# ═══════════════════════════════════════════════════════════════════
# Check 2: sdp-cli process exists
# ═══════════════════════════════════════════════════════════════════
check_process_exists() {
    if pgrep -f "sdp-cli.*orchestrate\|sdp-cli.*run" >/dev/null; then
        ok "process_missing"
        return 0
    fi
    # The process might be briefly gone between runs — only alert if systemd is also unhappy
    if ! systemctl is-active cypherclaw-sdp-runner.service &>/dev/null; then
        alert "process_missing" "No sdp-cli process running and systemd unit not active"
        return 1
    fi
    return 0
}

# ═══════════════════════════════════════════════════════════════════
# Check 3: Circuit breaker closed
# ═══════════════════════════════════════════════════════════════════
check_circuit_breaker() {
    local breaker_state=$(cd /home/user/cypherclaw && /home/user/.local/bin/sdp-cli circuit status 2>&1 \
        | grep -oP "Status:\s*\K\w+" | head -1)
    if [[ "$breaker_state" == "closed" ]]; then
        ok "breaker_open"
        return 0
    fi
    if [[ -z "$breaker_state" ]]; then
        log "Could not read circuit breaker state"
        return 0
    fi
    alert "breaker_open" "Circuit breaker is ${breaker_state} — run: sdp-cli circuit reset"
    return 1
}

# ═══════════════════════════════════════════════════════════════════
# Check 4: Recent task_runs (pipeline making progress)
# ═══════════════════════════════════════════════════════════════════
check_progress() {
    if [[ ! -f "$STATE_DB" ]]; then
        log "State DB not found at $STATE_DB"
        return 0
    fi

    local last_run_age_minutes
    last_run_age_minutes=$(sqlite3 "$STATE_DB" "
        SELECT CAST(
            (julianday('now') - julianday(MAX(started_at))) * 24 * 60
            AS INTEGER
        )
        FROM task_runs;
    " 2>/dev/null)

    if [[ -z "$last_run_age_minutes" || "$last_run_age_minutes" == "" ]]; then
        log "No task_runs in DB yet"
        return 0
    fi

    if (( last_run_age_minutes < STALL_THRESHOLD_MINUTES )); then
        ok "pipeline_stalled"
        return 0
    fi

    # Is there pending work? If the queue is empty, stall is expected.
    local pending_count
    pending_count=$(sqlite3 "$STATE_DB" "
        SELECT COUNT(*) FROM tasks
        WHERE status IN ('pending', 'needs_split', 'running');
    " 2>/dev/null || echo 0)

    if (( pending_count == 0 )); then
        log "Pipeline idle — no pending tasks, stall is expected"
        ok "pipeline_stalled"
        return 0
    fi

    alert "pipeline_stalled" \
        "No task runs in ${last_run_age_minutes}min, but ${pending_count} tasks are pending. Runner may be stuck."
    return 1
}

# ═══════════════════════════════════════════════════════════════════
# Check 5: systemd hot-loop detection
# ═══════════════════════════════════════════════════════════════════
check_hot_loop() {
    # Count systemd restart events in the last hour
    local restart_count=0
    if command -v journalctl >/dev/null 2>&1; then
        restart_count=$(journalctl -u cypherclaw-sdp-runner.service \
            --since "1 hour ago" --no-pager 2>/dev/null \
            | grep -E "Scheduled restart job|Started cypherclaw-sdp-runner" \
            | wc -l)
        # Strip any whitespace
        restart_count="${restart_count// /}"
        [[ -z "$restart_count" ]] && restart_count=0
    fi

    if (( restart_count < 10 )); then
        ok "hot_loop"
        return 0
    fi

    alert "hot_loop" \
        "systemd has restarted cypherclaw-sdp-runner ${restart_count} times in the last hour. Hot-loop detected."
    return 1
}

# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

main() {
    log "=== watchdog run ==="

    local failures=0
    check_systemd_active || ((failures++))
    check_process_exists || ((failures++))
    check_circuit_breaker || ((failures++))
    check_progress || ((failures++))
    check_hot_loop || ((failures++))

    if (( failures == 0 )); then
        log "all checks passed"
    else
        log "${failures} check(s) failed"
    fi

    # Rotate log if it gets huge
    if [[ -f "$LOG_FILE" ]] && (( $(stat -c %s "$LOG_FILE" 2>/dev/null || echo 0) > 1048576 )); then
        mv "$LOG_FILE" "${LOG_FILE}.old"
        log "log rotated"
    fi
}

main "$@"
