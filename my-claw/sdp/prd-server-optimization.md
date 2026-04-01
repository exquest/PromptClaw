# PRD: Server Optimization — Maximize CypherClaw's Home

## Overview

CypherClaw's home server (Intel i5-10505, 64GB DDR4, 1.8TB SSD) is using <5% of its capacity. This PRD addresses the remaining optimizations to fully utilize the server's resources: expanding Redis usage, enabling sdp-cli concurrency, setting up auto-recovery systems, and ensuring all services are resilient to reboots and failures.

**Depends on:** `prd-home-resilience.md` (authoritative state, safe reboot, runner lifecycle), `prd-restructure.md` (stable runtime paths), `prd-model-awareness.md` (provider/model-aware agent execution)

**Server profile after immediate fixes applied:**
- CPU: 12 threads @ 4.6GHz boost, performance governor
- RAM: 64GB DDR4-2667 (XMP to 3200 pending BIOS change)
- tmpfs: 32GB
- Disk: 1.8TB SSD, ext4 with commit=60, noatime

## Execution Role

This PRD is no longer the first stop for resilience. `prd-home-resilience.md` now owns authoritative state, safe reboot, preflight, and runner continuity.

Treat this PRD as:

- phase-2 operational optimization after the resilience spine is complete
- the place for performance tuning, visibility polish, and secondary automation

Do not schedule legacy tmpfs-authority assumptions from this PRD ahead of Home Resilience.

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| OPT-001 | Increase sdp-cli agent concurrency from 1 to 2. With all hot writes on tmpfs, disk I/O is eliminated during pipeline operation. Modify the daemon's `_agent_semaphore` to 2. Monitor for 24 hours — if I/O guard triggers more than twice, revert to 1. Log semaphore utilization to Observatory so we can track whether both slots are actually used. | SHOULD | T1 | - Semaphore set to 2<br/>- 24-hour monitoring period with no jbd2 issues<br/>- Observatory logs concurrent agent count<br/>- Revert mechanism documented |
| OPT-002 | Expand Redis usage beyond metrics. Move these to Redis: (a) conversation history cache — last 50 messages for instant retrieval during routing, (b) agent prompt cache — cache the AGENT_CONTEXT + recent conversation to avoid rebuilding per request, (c) model fitness scores — cache Observatory skill scores with 5-min TTL for fast selector queries, (d) pet status cache — current pet stats for instant /pets responses. Use Redis key prefixes: `claw:conv:`, `claw:prompt:`, `claw:fitness:`, `claw:pet:`. | SHOULD | T2 | - Conversation history in Redis with 50-message cap<br/>- Agent prompts cached and reused<br/>- Fitness scores cached with TTL<br/>- Pet stats cached<br/>- All reads from Redis, writes to both Redis + persistent store |
| OPT-003 | Create a unified auto-recovery service. When any critical service fails, automatically recover: (a) sdp-cli pipeline — if not running and circuit breaker is closed, restart with ionice/nice from tmpfs workdir, (b) Ollama — if not responding, restart via systemctl, (c) daemon — already handled by systemd, but add pre-start hook to ensure tmpfs dirs exist, (d) Redis — monitor and restart. Create `tools/auto_recover.sh` that runs every 5 minutes via systemd timer, checking all services and restarting as needed. Send Telegram alert on any recovery action. | MUST | T2 | - Auto-recovery script checks: daemon, sdp-cli, Ollama, Redis, PostgreSQL<br/>- Restarts failed services automatically<br/>- Sends Telegram alert on recovery<br/>- Runs every 5 minutes via systemd timer<br/>- Logs all actions to tmpfs |
| OPT-004 | Make the daemon fully reboot-resilient. On startup, the daemon should: (a) ensure all tmpfs dirs exist (call init_workdir.sh if needed), (b) restore state.db from backup if tmpfs copy is missing, (c) verify Observatory DB exists, (d) verify Ollama is running, (e) verify Redis is running, (f) check if sdp-cli pipeline should be restarted (was it running before reboot?). Add a `_boot_recovery()` function called at the start of `poll_loop()`. | MUST | T2 | - Daemon starts cleanly after any reboot<br/>- No crash loops from missing tmpfs files<br/>- State restored from backup automatically<br/>- All services verified on startup<br/>- sdp-cli restarted if it was running before reboot |
| OPT-005 | Add the 30-minute heartbeat with server stats to Telegram. Every 30 minutes, send a compact message showing: uptime, I/O%, memory%, load, agent count, sdp-cli progress, pet XP summary. This is the foundation for the GlyphWeave art heartbeat (which will replace the text-only version later). Include a link to the gallery when it's available. | MUST | T1 | - Heartbeat fires at :00 and :30 each hour<br/>- Shows uptime, I/O, memory, load, agents, pipeline progress<br/>- Pet summary included<br/>- Renders correctly in Telegram<br/>- Heartbeat logged to Observatory |
| OPT-006 | Set up Nginx reverse proxy for internal services. Configure Nginx to serve: (a) gallery at `cypherclaw:8080` → localhost:8080, (b) Ollama API at `cypherclaw:11434` → localhost:11434, (c) a simple status page at `cypherclaw:80` showing server health, service status, and pipeline progress as static HTML refreshed every minute. All accessible via Tailscale only. | SHOULD | T2 | - Nginx proxies to gallery and Ollama<br/>- Status page at port 80 with auto-refresh<br/>- Only accessible via Tailscale (bind to tailscale0 or use allow/deny)<br/>- SSL not required (internal only) |
| OPT-007 | Implement sdp-cli pipeline auto-restart. When the I/O guard kills the pipeline, or the pipeline exits due to escalation/circuit breaker, automatically restart it after a 5-minute cooldown. The auto-recovery service (OPT-003) should: detect pipeline not running, check circuit breaker state, reset if needed, and restart from the tmpfs working copy. Track restart count — if more than 3 restarts in an hour, stop and alert Anthony. | MUST | T2 | - Pipeline auto-restarts after I/O guard kill<br/>- 5-minute cooldown between restarts<br/>- Circuit breaker auto-reset on restart<br/>- Max 3 restarts per hour before giving up<br/>- Telegram alert on each restart and on give-up |
| OPT-008 | Optimize the sync between tmpfs working copy and disk. Current sync is a blunt `git push` every 15 minutes. Improve to: (a) only sync when there are new commits (check `git rev-parse HEAD` against last synced), (b) also sync the state.db and observatory.db, (c) on sync failure, alert but don't crash, (d) track sync history in Redis. This ensures no work is lost while minimizing disk writes. | SHOULD | T1 | - Sync only when new commits exist<br/>- state.db and observatory.db backed up on sync<br/>- Sync failures logged and alerted<br/>- Sync history in Redis<br/>- No unnecessary disk writes |
| OPT-009 | Create a server status dashboard as a simple HTML page. Generate a static HTML file every 60 seconds at `/var/www/html/index.html` showing: server vitals (CPU, RAM, I/O, load), service status (daemon, sdp-cli, Ollama, Redis, PostgreSQL), pipeline progress (tasks complete/total, ETA), pet status (all 4 pets with class and level), recent events (last 10 Observatory entries). Use a systemd timer to regenerate. Served by Nginx at port 80. | SHOULD | T2 | - HTML dashboard generated every 60s<br/>- Shows all vitals, services, pipeline, pets<br/>- Accessible at cypherclaw:80 via Tailscale<br/>- Auto-refreshes in browser<br/>- Works without JavaScript (pure HTML/CSS) |
| OPT-010 | Set up tmpfs working copy validation. Before starting the sdp-cli pipeline, verify the tmpfs working copy is valid: (a) .git directory exists, (b) remote points to disk repo, (c) state.db exists and is valid SQLite, (d) sdp.toml symlink is valid, (e) AGENTS.md and pyproject.toml exist. If any check fails, re-initialize from disk. Add this as a pre-check in the auto-recovery service. | MUST | T1 | - Validation checks all 5 conditions<br/>- Auto-reinitializes from disk on failure<br/>- Runs before every pipeline start<br/>- Logged to tmpfs |

## Implementation Phases

### Phase 1: Resilience (OPT-003, OPT-004, OPT-007, OPT-010)
Auto-recovery, boot resilience, pipeline auto-restart, workdir validation. The server should run unattended without manual intervention.

### Phase 2: Visibility (OPT-005, OPT-009)
Heartbeat messages and status dashboard. Anthony can see what's happening without SSH.

### Phase 3: Performance (OPT-001, OPT-008)
Increase concurrency, optimize sync. More throughput with less overhead.

### Phase 4: Infrastructure (OPT-002, OPT-006)
Redis expansion, Nginx proxy. Better caching and service access.

## Success Metrics

| Metric | Target |
|--------|--------|
| Unattended uptime | >24 hours without manual intervention |
| Pipeline auto-recovery | <5 minutes from kill to restart |
| Heartbeat reliability | 100% delivery at :00 and :30 |
| Service recovery | All services back within 5 minutes of failure |
| Disk I/O during pipeline | 0% (tmpfs only) |
| Sync data loss window | <15 minutes (worst case between syncs) |
