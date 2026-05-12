# CypherClaw Phase 2 Discovery Report

**Date:** 2026-03-28
**Server:** cypherclaw (Ubuntu, 12 cores, 62GB RAM, 1.8TB NVMe SSD)
**Project root:** `/home/user/cypherclaw/`

---

## Section A -- Disaster Recovery

### Crontab (user)

| Schedule | Command | Purpose |
|----------|---------|---------|
| `*/2 * * * *` | `ionice -c3 pkill -9 --older 300 -f "claude\|codex\|gemini"` | Kill stale AI agent processes older than 5 min |
| `*/30 * * * *` | `cp ...state.db ...backup; cp ...observatory.db ...backup` | Snapshot SDP state + Observatory DB every 30 min |
| `*/15 * * * *` | `sync_workdir.sh` | Sync tmpfs working directory to persistent disk |
| `@reboot` | `init_workdir.sh` | Initialize tmpfs working directory on boot |
| `*/10 * * * *` | `pipeline_watchdog.sh` | Auto-restart dead pipeline components |
| `*/10 * * * *` | `post_restructure_heal.sh` | Post-restructure auto-heal |

**Sudo crontab:** Empty (no root cron jobs).

### Systemd Timers

| Timer | Service | Status |
|-------|---------|--------|
| `io-guard.timer` | `io-guard.service` | Active, fires every 30s |
| `dpkg-db-backup.timer` | `dpkg-db-backup.service` | System default, daily at midnight |

### Backup & Restore Scripts (CypherClaw-relevant)

- `/home/user/cypherclaw/.promptclaw/observatory.db.backup` -- Observatory DB snapshot (cron)
- `/home/user/cypherclaw/.sdp/state.db.backup` -- SDP state snapshot (cron)
- `/home/user/.claude/backups/` -- Claude config backups (5 files)

**Gap identified:** No off-server backup (no rsync, rclone, or S3 push). Backups are local-only snapshots. A disk failure would lose everything.

### Observatory Files

Located at:
- `/home/user/cypherclaw/.promptclaw/observatory.db` (main, with WAL)
- `/home/user/cypherclaw/.promptclaw/observatory.db.backup` (cron snapshot)
- `/run/cypherclaw-tmp/observatory/observatory.db` (tmpfs copy, currently empty)
- `/home/user/.promptclaw/observatory.db` (home-level copy)
- Agent worktree copies: `agent-ab42d2ba`, `agent-a55ac8eb`
- Source: `/home/user/cypherclaw/tools/observatory.py` (13K)

### SQLite Databases

| Path | Purpose |
|------|---------|
| `/home/user/cypherclaw/.promptclaw/observatory.db` | Observatory events |
| `/home/user/cypherclaw/.sdp/state.db` | SDP pipeline state |
| `/home/user/.sdp/timing.db` | SDP timing data |
| `/home/user/sdp-cli/.sdp/sdp_state.db` | SDP CLI state |
| `/home/user/sdp-cli/.sdp/state.db` | SDP CLI state |
| `/home/user/sdp-cli/.sdp/sdp.db` | SDP CLI data |
| `/home/user/projects/ProjectDocumentation/data/projects.db` | Project docs |

### tmpfs

```
tmpfs  32G  99M  32G  1%  /run/cypherclaw-tmp
```

Mounted as `tmpfs` with `rw,relatime,size=33554432k,mode=755,uid=1000,gid=1000`. 32GB allocated, 99MB used (1%). This is volatile -- data lost on reboot unless synced by `sync_workdir.sh`.

### Redis

| Config | Value |
|--------|-------|
| `save` | `3600 1 300 100 60 10000` (RDB snapshots) |
| `appendonly` | `no` (AOF disabled) |
| `dir` | `/var/lib/redis` |
| `LASTSAVE` | `1774714047` (epoch) |
| Keyspace | `db1: 2 keys, 2 expires, avg_ttl=3577244` |
| DBSIZE (db0) | `0` |

**Findings:** Redis is nearly empty (2 keys in db1, 0 in db0). RDB persistence is on but AOF is off. Minimal data at risk.

### Git Repos

Found 2 CypherClaw-relevant repos:
- `/home/user/cypherclaw/.git`
- `/home/user/cypherclaw-workspace/.git`

Plus 80+ project repos under `/home/user/projects/`.

### Git Config

- **Version:** 2.43.0
- **user.email:** (not set)
- **user.name:** (not set)

**Gap:** Git identity not configured globally. Commits will use system defaults.

### SSH Keys

```
~/.ssh/authorized_keys  (341 bytes)
~/.ssh/known_hosts      (142 bytes)
```

**No private keys on server.** No deploy keys for GitHub push. Currently pull-only or manual.

### Disk Layout

```
/dev/mapper/ubuntu--vg-ubuntu--lv  1.8T  25G  1.7T  2%  /  (ext4, LVM)
/dev/nvme0n1p2                     2.0G  201M 1.6G  11% /boot
/dev/nvme0n1p1                     1.1G  6.2M 1.1G  1%  /boot/efi
tmpfs 32G                          99M   32G  1%         /run/cypherclaw-tmp
```

**1.7TB free.** Disk space is not a concern. Single NVMe drive with LVM.

---

## Section B -- Local LLM (Ollama)

### Ollama Service

- **Status:** Active (running) since 2026-03-27 23:29:44 UTC (16h uptime)
- **Enabled:** Yes (starts on boot)
- **PID:** 1219
- **Memory:** 47.6M (peak 58.5M) -- extremely lightweight when idle
- **CPU:** 808ms total

### Installed Models

| Model | Size | Quantization | Family |
|-------|------|-------------|--------|
| `llama3.2:3b` | 2.0 GB | Q4_K_M | llama |

### Embedding Models

**None installed.** No embedding model available for vector search.

### Memory Availability

```
Total: 62Gi  Used: 1.6Gi  Free: 58Gi  Available: 60Gi
Swap:  4.0Gi  Used: 0B
```

**60GB available RAM.** More than enough to run additional models (e.g., `nomic-embed-text` at ~275MB, or a 7B model at ~4GB).

### Top Processes by Memory

| Process | RSS | Notes |
|---------|-----|-------|
| claude | 257MB | Active Claude Code agent |
| dockerd | 81MB | Docker daemon |
| sdp-cli run | 60MB | SDP pipeline |
| containerd | 51MB | Container runtime |
| tailscaled | 48MB | Tailscale VPN |
| fwupd | 46MB | Firmware updater |
| cypherclaw_daemon.py | 41MB | Main CypherClaw daemon |
| systemd-journald | 38MB | System journal |
| ollama serve | 36MB | Ollama (idle) |

---

## Section C -- Vector Store

### Package Status

| Package | System | Venv |
|---------|--------|------|
| chromadb | Not installed | Not installed |
| faiss-cpu | Not installed | Not installed |

**No vector store is installed anywhere.**

### Existing Vector-Related Directories

Only Redis vectorset modules found (from redis Python package):
- `/home/user/cypherclaw/.venv/lib/python3.12/site-packages/redis/commands/vectorset`
- `/home/user/.local/lib/python3.12/site-packages/redis/commands/vectorset`

No chroma, faiss, or custom vector directories exist.

### Disk Space for Vector Store

1.7TB available on `/`. Plenty of room for any vector store.

---

## Section D -- Verification System

### Files with Verification Logic

| File | Notes |
|------|-------|
| `tools/researcher.py` | Contains verify references |
| `tools/sdp_bridge.py` | Contains verify references |
| `tools/cypherclaw_daemon.py` | Contains verify references |
| `tools/glyphweave/pet_animations.py` | Contains verify references |
| `tools/agent_selector.py` | Contains verify references |

### Severity Classification System (healer.py)

The healer implements a 3-tier severity system:

| Level | Constant | Value | Behavior |
|-------|----------|-------|----------|
| SILENT | `SILENT` | 1 | Auto-fix, no notification |
| NOTIFY | `NOTIFY` | 2 | Auto-fix, notify Anthony after |
| ASK | `ASK` | 3 | Ask Anthony before acting |

**Classification rules:**
- Missing pip package -> SILENT (auto-install)
- Agent failure <3 tries -> SILENT (retry); >=3 tries -> NOTIFY
- Gate failure <3 tries -> SILENT; >=3 tries -> ASK
- Deploy rollback -> NOTIFY (auto-rollback) or ASK (if no rollback possible)
- Crash-looping (>3 in 5 min) -> ASK
- Stale task (no progress 30+ min) -> NOTIFY (kill and report)
- Unknown -> ASK (safe default)

### Observatory Events Database

**Main DB:** `/home/user/cypherclaw/.promptclaw/observatory.db`

**Tables:** `events`, `sqlite_sequence`, `task_results`, `healing_log`, `agent_skills`, `daily_rollups`, `model_art_fitness` (last one only in tmpfs copy)

**Event Distribution (106 total):**

| Event Type | Count |
|------------|-------|
| user_message | 67 |
| routing_decision | 28 |
| health_check | 3 |
| research_completed | 2 |
| research_started | 2 |
| shell_executed | 2 |
| context_pulse | 1 |
| daily_brief_sent | 1 |

**Time Range:** 2026-03-27T18:44:29 to 2026-03-28T14:16:37 (~20 hours of data)

**tmpfs copy** (`/run/cypherclaw-tmp/observatory/observatory.db`): Has `model_art_fitness` table (extra), but 0 events. Appears to be a fresh schema that isn't being written to.

### Agent Infrastructure

The daemon (`cypherclaw_daemon.py`, 96K) includes:
- `AGENT_CONTEXT` -- System prompt defining CypherClaw's identity and capabilities
- `_build_context_snapshot()` / `_get_context_snapshot()` -- Builds a live state snapshot, cached for 5 minutes
- Context snapshot is injected into all LLM calls alongside AGENT_CONTEXT

---

## Section E -- Proactive Scanner

### System Load

```
0.09 0.09 0.07 1/378
```

Load average well under 1.0. Server is nearly idle.

### Available Tools

| Tool | Status |
|------|--------|
| `sar` (sysstat) | Binary exists at `/usr/bin/sar` but not functional (`sar not available`) |
| `jq` | Installed, version 1.7 |

### Outdated Packages (venv)

| Package | Current | Latest |
|---------|---------|--------|
| pip | 24.0 | 26.0.1 |
| pydantic_core | 2.41.5 | 2.44.0 |

Only 2 outdated packages. The venv is very current.

---

## Section F -- Undocumented Tools & Infrastructure

### Python Tools Inventory (by size)

| File | Size | Description |
|------|------|-------------|
| `cypherclaw_daemon.py` | 96K | Main orchestrator daemon |
| `project_scanner.py` | 61K | Project scanning/analysis |
| `reviewer.py` | 24K | Code review tool |
| `healer.py` | 19K | Self-healing engine |
| `glyphweave/scenes.py` | 17K | GlyphWeave art scenes |
| `researcher.py` | 17K | Research tool |
| `io_watchdog.py` | 16K | I/O monitoring watchdog |
| `tamagotchi.py` | 14K | Pet/tamagotchi system |
| `research_tools.py` | 14K | Research utilities |
| `glyphweave/pet_sprites.py` | 14K | Pet sprite rendering |
| `observatory.py` | 13K | Event tracking/observability |
| `glyphweave/dsl.py` | 13K | GlyphWeave DSL |
| `glyphweave/pet_animations.py` | 12K | Pet animation system |
| `server_health.py` | 11K | Server health monitoring |
| `glyphweave/player.py` | 8.5K | GlyphWeave audio player |
| `glacier_cleanup.py` | 7.8K | AWS Glacier cleanup tool |
| `effort_router.py` | 7.7K | Effort-based routing |
| `lifeimprover_bridge.py` | 7.6K | LifeImprover integration |
| `sdp_bridge.py` | 7.0K | SDP pipeline bridge |
| `agent_selector.py` | 6.9K | Agent selection logic |
| `telegram.py` | 5.9K | Telegram bot interface |
| `context_pulse.py` | 5.5K | Context pulse system |
| `dice_roller.py` | 3.0K | Dice rolling utility |
| `gemini_image.py` | 2.8K | Gemini image generation |
| `glyphweave/__init__.py` | 1.1K | GlyphWeave package init |
| `__init__.py` | 370B | Tools package init |

**Total: 26 Python files, ~430K of code.**

### Shell Scripts

| File | Size | Purpose |
|------|------|---------|
| `pipeline_watchdog.sh` | 7.4K | Auto-restart failed pipeline components |
| `post_restructure_heal.sh` | 2.2K | Post-restructure healing |
| `io_guard.sh` | 1.8K | I/O guard (systemd timer) |
| `healthcheck.sh` | 1.6K | Health check script |
| `init_workdir.sh` | 1.6K | Initialize tmpfs workdir on boot |
| `sync_workdir.sh` | 518B | Sync tmpfs to persistent disk |

### PRDs (Product Requirement Documents)

17 PRDs found in `/home/user/cypherclaw/sdp/`:

| PRD | Topic |
|-----|-------|
| `prd-glyphweave-art-studio.md` | GlyphWeave Art Studio |
| `prd-local-llm-integration.md` | Local LLM integration |
| `prd-model-awareness.md` | Model awareness |
| `prd-pet-system-v2.md` | Pet system v2 |
| `prd-proactive-intelligence.md` | Proactive intelligence |
| `prd-restructure.md` | Codebase restructure |
| `prd-server-optimization.md` | Server optimization |
| `prd-snapshot.md` | Snapshot system |
| `prd-verification-system.md` | Verification system |
| `prd-web-platform.md` | Web platform |
| `prd-093670b3.md` | (hash-named) |
| `prd-662a9eba.md` | (hash-named) |
| `prd-7787782b.md` | (hash-named) |
| `prd-7c3d44f0.md` | (hash-named) |
| `prd-84c88f39.md` | (hash-named) |
| `prd-bac7fccb.md` | (hash-named) |
| `prd-f8e2ed74.md` | (hash-named) |

### TODOs / FIXMEs

**None found** in `/home/user/cypherclaw/tools/`. The codebase has no TODO/FIXME/STUB markers.

### Systemd Units

| Unit | Type | State | Description |
|------|------|-------|-------------|
| `run-cypherclaw-tmp.mount` | mount | active (mounted) | tmpfs at /run/cypherclaw-tmp |
| `cpu-performance.service` | service | active (exited) | Set CPU governor to performance |
| `cypherclaw.service` | service | active (running) | CypherClaw Daemon |
| `io-guard.service` | service | activating (start) | I/O Guard |
| `ollama.service` | service | active (running) | Ollama Service |
| `io-guard.timer` | timer | active (running) | I/O Guard Timer |

**Enabled at boot:** `cpu-performance.service`, `cypherclaw.service`, `io-guard.timer`

---

## Implementation Readiness Summary

| Capability | Status | Readiness | Blocking Issues |
|------------|--------|-----------|-----------------|
| **Disaster Recovery** | Partial | YELLOW | Local-only backups; no off-server replication; no git push identity |
| **Local LLM (Ollama)** | Running | GREEN | llama3.2:3b available; 60GB RAM free for more models |
| **Embedding Model** | Missing | RED | No embedding model installed; needed for vector search |
| **Vector Store** | Missing | RED | Neither ChromaDB nor FAISS installed; no vector data exists |
| **Verification System** | Implemented | GREEN | healer.py has 3-tier severity (SILENT/NOTIFY/ASK); 5 files with verify logic |
| **Observatory** | Active | GREEN | 106 events over 20h; 6 tables; WAL-mode SQLite |
| **Agent Infrastructure** | Active | GREEN | Daemon running (41MB), context snapshot cached 5min, full system prompt |
| **Proactive Scanner** | Partial | YELLOW | Load avg 0.09; sar not functional; jq available; only 2 outdated pkgs |
| **tmpfs Working Dir** | Active | GREEN | 32GB allocated, 99MB used; init/sync scripts in cron |
| **Redis** | Minimal | YELLOW | Only 2 keys; RDB on, AOF off; low utilization |
| **Systemd Services** | Active | GREEN | 4 custom units all enabled and running |
| **Tool Coverage** | Comprehensive | GREEN | 26 Python files (~430K), 6 shell scripts, 0 TODOs |

---

## Recommended First Actions

### Priority 1 -- Fix RED Items

1. **Install embedding model:**
   ```bash
   ollama pull nomic-embed-text
   ```
   ~275MB, fits easily in 60GB RAM. Required before any vector/RAG pipeline can work.

2. **Install vector store (ChromaDB recommended):**
   ```bash
   /home/user/cypherclaw/.venv/bin/pip install chromadb
   ```
   ChromaDB is the simplest path -- embeds natively with Ollama, persists to SQLite, and needs no external server. FAISS is an alternative if raw speed matters more than ease.

### Priority 2 -- Fix YELLOW Items

3. **Set up off-server backups:** Add an rsync/rclone cron job pushing critical data (`.promptclaw/`, `.sdp/`, `tools/`, `sdp/`) to a remote location (e.g., the MacBook via Tailscale, or an S3 bucket). The 1.7TB disk is a single point of failure.

4. **Configure git identity:**
   ```bash
   git config --global user.email "anthony@example.com"
   git config --global user.name "Anthony"
   ```

5. **Fix sysstat/sar:** Either install properly (`sudo apt install sysstat && sudo systemctl enable sysstat`) or remove the dependency. Currently the binary exists but doesn't work.

6. **Evaluate Redis utilization:** Only 2 keys with expiry in db1. Determine whether Redis is actually needed, or if its role can be absorbed by SQLite/tmpfs.

### Priority 3 -- Housekeeping

7. **Review hash-named PRDs:** 7 PRDs have hash names (`prd-093670b3.md`, etc.) -- these should be renamed to human-readable names for discoverability.

8. **Generate SSH deploy key:** If automated git push is desired, generate a deploy key on the server and add it to GitHub.

9. **Update pip and pydantic_core:** Minor version bumps available, low risk.

10. **Investigate empty tmpfs observatory:** `/run/cypherclaw-tmp/observatory/observatory.db` has the schema (including `model_art_fitness` table) but 0 events. Either events aren't being routed there, or it was recently re-initialized.
