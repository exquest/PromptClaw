# PRD: System Introspector — Self-Healing Intelligence Service

## Core Philosophy: Verify/Scan/Fix

This is the foundational operating pattern for the entire CypherClaw system:

1. **DO** — take action (fix a bug, deploy code, change config)
2. **VERIFY** — confirm it worked (run tests, check output, validate state)
3. **SCAN** — look for related issues and side effects
4. **FIX** — resolve anything found
5. **REPEAT** — loop steps 2-4 until clean

Verification depth scales with risk:
- **Simple changes**: functional check only
- **Moderate changes**: functional + ripple scan (check everything the change touches)
- **Critical changes**: full system health scan (all imports, gates, services, logs)

Every fix must be verified by a **different LLM provider** than the one that generated it. Cross-provider verification catches model-specific blind spots.

This pattern applies at every level: conversation agents, sdp-cli pipeline agents, the daemon, and this Introspector service. The Introspector is the autonomous embodiment of this loop — running 24/7 without human intervention.

## Overview

A separate always-on service (`tools/introspector.py`) that continuously monitors all system logs and data sources, detects error patterns, autonomously diagnoses and fixes issues using a generate/verify/fix cycle with cross-provider agent verification, and reports activity via tiered Telegram notifications. The introspector is CypherClaw's immune system — it watches everything, learns from patterns, and heals proactively.

**Depends on:** `prd-verification-system.md` (risk classification), `prd-model-awareness.md` (agent selector for cross-provider routing), `prd-agent-runtime-substrate.md` (shared process/session control), `prd-capability-approval-framework.md` (approval boundaries for destructive repair)

## Execution Role

This is a later-stage automation layer. It should not precede the execution spine.

The intended order is:

1. Home resilience
2. Restructure
3. Model awareness
4. Agent runtime substrate
5. Capability and approval framework
6. Verification system
7. Introspector

That order keeps the immune system from trying to operate on a body whose bones are still moving.

## Design Decisions

1. **All 8 data sources** — daemon log, pipeline log, I/O guard log, event stream, watchdog log, Observatory DB, health check output, systemd journal
2. **Full autonomy with verification** — auto-fix anything, but every fix must pass generate/verify/fix with a cross-provider agent before applying. Only ask permission for destructive actions (delete data, restart daemon, modify production config).
3. **Separate systemd service** — independent from the daemon. Can diagnose daemon issues, restart independently, run at its own pace.
4. **Always cross-provider verification** — if Claude diagnoses, Codex or Gemini verifies. Never same-provider for diagnosis and verification.
5. **Tiered notifications** — critical issues: immediate Telegram. Fixes applied: notify as they happen. Pattern analysis: weekly digest.

## Architecture

```
tools/introspector.py          # Main service — systemd managed
tools/introspector/
├── __init__.py
├── scanner.py                 # Log scanner — reads all 8 data sources
├── pattern_db.py              # Known error patterns + resolution history
├── diagnostician.py           # Root cause analysis via agent call
├── fixer.py                   # Fix generation + cross-provider verification
├── reporter.py                # Tiered Telegram notifications + weekly digest
└── migrations/
    └── 001_introspector.sql   # Pattern DB + fix history schema
```

**Database:** `~/.promptclaw/introspector.db` (SQLite)

## Data Sources

| ID | Source | Path | Check Interval | What to Look For |
|----|--------|------|---------------|-----------------|
| DS-1 | Daemon log | `tools/cypherclaw_daemon.log` | 2 min | Exceptions, tracebacks, repeated errors |
| DS-2 | Pipeline log | `/run/cypherclaw-tmp/sdp-cli-run.log` | 5 min | Task failures, escalations, agent timeouts |
| DS-3 | I/O guard log | `/run/cypherclaw-tmp/io_guard.log` | 2 min | Sustained high I/O, false alarm frequency |
| DS-4 | Event stream | `/run/cypherclaw-tmp/event_stream.jsonl` | 1 min | Error messages sent to user, failed commands |
| DS-5 | Watchdog log | `/run/cypherclaw-tmp/pipeline_watchdog.log` | 5 min | Pipeline stops, restart frequency, diagnosis patterns |
| DS-6 | Observatory DB | `.promptclaw/observatory.db` | 10 min | Agent success rate drops, performance degradation |
| DS-7 | Health check | Telegram health check messages | 5 min | Stale data, tracebacks in health output |
| DS-8 | Systemd journal | `journalctl` | 5 min | OOM kills, service crashes, kernel errors |

## Requirements

| ID | Description | Tier |
|----|-------------|------|
| IN-001 | Create `tools/introspector.py` as a standalone service with main loop. Scan all 8 data sources at their configured intervals. Track last-read position per source to avoid re-processing. Run as systemd service with auto-restart. | T1 |
| IN-002 | Create `introspector/scanner.py` — log scanner that reads each data source, extracts error lines (tracebacks, lines containing ERROR/FAIL/Exception/❌), and returns structured findings: source, timestamp, error_text, frequency, first_seen, last_seen. | T1 |
| IN-003 | Create `introspector/pattern_db.py` — SQLite-backed pattern database. Tables: known_patterns (pattern_id, regex, severity, resolution_template, times_seen, auto_fixable), fix_history (fix_id, pattern_id, diagnosis, fix_applied, verified_by, success, timestamp), scan_state (source_id, last_offset, last_scan_at). Deduplicates errors by pattern matching. | T1 |
| IN-004 | Create `introspector/diagnostician.py` — given an error finding, call an agent to diagnose root cause. Send the error text + surrounding context (10 lines before/after) + relevant source file snippets. Agent returns structured diagnosis: root_cause, severity (critical/warning/info), suggested_fix, files_to_modify, is_destructive. Use agent_selector with task_category "diagnosis". | T2 |
| IN-005 | Create `introspector/fixer.py` — given a diagnosis, generate a fix using one agent, then verify with a DIFFERENT provider agent. Fix types: code_patch (modify a .py file), config_change (modify .json/.toml), process_restart (systemctl restart), cache_clear (delete stale files), db_repair (sqlite3 recover). Only apply fix if verification passes. Destructive actions (restart daemon, delete data, modify promptclaw.json) require Telegram approval from Anthony. | T2 |
| IN-006 | Create `introspector/reporter.py` — tiered Telegram notifications. Critical (service down, data corruption, security): send immediately. Fix applied: send short message ("Fixed: [description]"). Pattern analysis + trends: weekly digest (Sunday morning). All messages under 300 chars except weekly digest. | T1 |
| IN-007 | Create systemd service file `introspector.service`. Runs as user service, auto-restart on failure, depends on redis and cypherclaw-daemon. Wrap in I/O protection (ionice -c3 nice -n19). Start after daemon. | T1 |
| IN-008 | Implement error pattern learning. When the introspector fixes an error, record the pattern regex + resolution in pattern_db. Next time the same pattern appears, apply the known fix immediately without re-diagnosing. Track fix success rate per pattern — if a pattern's fix fails 3 times, escalate to full diagnosis. | T2 |
| IN-009 | Implement Observatory integration. Record all findings and fixes as Observatory events. Track: errors_detected_per_hour, fixes_applied_per_day, mean_time_to_detect, mean_time_to_fix, fix_success_rate. Feed into the daemon's health check display. | T2 |
| IN-010 | Implement cross-provider verification protocol. Diagnosis agent and verification agent must ALWAYS be different providers (Anthropic vs OpenAI vs Google vs local Ollama). If only one provider is available, queue the fix for later verification instead of applying unverified. Log provider pairs used for each fix. | T2 |
| IN-011 | Implement weekly digest generation. Every Sunday at 8am, compile: total errors detected, total fixes applied, top 5 recurring patterns, agent performance trends, system stability score (uptime % + fix success rate), recommendations for manual review. Send via Telegram. | T2 |
| IN-012 | Seed known_patterns with common errors observed so far: dev_task empty description, SQLite WAL corruption, stale sdp-cli status cache, pipeline lock file stale, Redis connection refused after reboot, missing tmpfs venv, health check traceback from corrupt DB. Each pattern includes regex, severity, and resolution template. | T1 |
