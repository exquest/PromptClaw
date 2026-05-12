# PromptClaw Discovery Report
## 2026-03-28

### Overview
PromptClaw/CypherClaw is an always-on AI orchestrator running on a dedicated Ubuntu home server (Intel i5-10505, 64GB RAM, 1.8TB SSD). It coordinates multiple AI agents (Claude, Codex, Gemini) via Telegram, manages a Tamagotchi pet system that evolves with agent usage, and runs a software development pipeline (sdp-cli) that executes PRD-driven tasks autonomously. The project is in Phase 2 — core infrastructure is built and running, with 9 PRDs totaling ~150 tasks queued for self-improvement features.

### 1. Self-Improvement
**Implemented:**
- `tools/observatory.py` — Append-only event store tracking every task, agent call, failure, and healing action. Agent skill scores updated via exponential moving average (α=0.3) per task category.
- `tools/agent_selector.py` — Fitness-based agent rotation with alternation penalty (0.3), cross-provider bonus (0.25), 10% exploration rate. Learns which agent is best at which task type over time.
- `tools/reviewer.py` — Scheduled daily briefs (8am), weekly retros (Monday), monthly reviews analyzing Observatory data for patterns and recommendations.
- Smart pipeline watchdog (`tools/pipeline_watchdog.sh`) — Auto-diagnoses failures, clears blocked tasks, resets circuit breaker, restarts pipeline. Progress stall detection (2h threshold).

**Planned:**
- PI-004: Auto-generated weekly self-improvement reports that propose and auto-apply low-risk changes to prompts/config (prd-proactive-intelligence.md)
- VER-001-011: Universal verification system — risk-tiered lead/verify on all actions, not just pipeline tasks (prd-verification-system.md)
- CT-001-003: Cost tracking and auto-degradation to cheaper models when budget limits approached (prd-proactive-intelligence.md)

### 2. Introspection
**Implemented:**
- `tools/context_pulse.py` — `/pulse` command shows real-time system awareness: conversation memory, workspace artifacts, Observatory events, agent fitness, pet status, CPU/RAM/disk. Self-recording (logs the pulse event itself).
- Rich context snapshot (`_build_context_snapshot()` in daemon) — Pre-computed every 5 min, injected into every agent prompt. Includes server health, pipeline progress, pet states, last 20 conversation messages.
- AGENT_CONTEXT — Identity block prepended to all agent calls with full capabilities list, available services, and 8 active PRDs.

**Planned:**
- RAG-001-005: Vector store memory using local LLM embeddings (ChromaDB/FAISS). Index all conversations, events, decisions. Semantic search via `/remember`. Context briefing for new sessions (prd-proactive-intelligence.md).

### 3. Self-Healing
**Implemented:**
- `tools/healer.py` — Severity-based healing engine (SILENT/NOTIFY/ASK). Handles: agent_error (retry with fallback), missing_dep (auto-install), process_crash (restart with crash-loop detection), gate_failure (error feedback loop), server_unhealthy (rollback), stale_task (kill and reassign).
- `tools/io_watchdog.py` — Monitors disk I/O every 30s via /proc/diskstats, stores metrics in Redis. Circuit breaker kills agents at 85% I/O utilization before jbd2 journal freeze.
- `tools/io_guard.sh` — Independent systemd timer (every 30s), kills agents AND sdp-cli at 75% I/O. Sends Telegram alert. Operates independently of the daemon.
- `tools/pipeline_watchdog.sh` — Smart self-healing: diagnoses why pipeline stopped (circuit_breaker, task_escalated, missing_file, config_error, killed), takes corrective action, restarts. Progress stall detection skips stuck tasks after 2 hours.
- `tools/server_health.py` — Health checks (disk, memory, load, zombies, daemon, services, temperature). Auto-maintenance: kills stale agents, cleans temp files, truncates oversized logs.

**Planned:**
- OPT-003: Unified auto-recovery service checking all services every 5 min (prd-server-optimization.md)
- OPT-004: Full boot-resilience — verify all tmpfs dirs, restore DBs, verify services, restart pipeline on boot (prd-server-optimization.md)
- VER-006: Self-healing integration with verification system — failed verifications route to healer before escalation (prd-verification-system.md)

### 4. Evolving Systems
**Implemented:**
- `tools/tamagotchi.py` — 4 Tamagotchi pets (Claude, Codex, Gemini, CypherClaw) with 6 evolution stages (Egg→Master), XP tracking, mood/hunger/energy stats, idle decay. Pets evolve based on agent usage.
- `tools/glyphweave/pet_sprites.py` — Dynamic ASCII art portraits per pet × stage × state (6 stages × 7 states). Evolution animations with sparkle effects.
- `tools/glyphweave/pet_animations.py` — Contextual narrations per agent personality × task category. Pet behavior changes based on what the agent is doing.
- Agent fitness evolution — Observatory skill scores update with each task, influencing future selection. Agents develop specializations over time.

**Planned:**
- PET-001-012: Multi-class pet evolution — 6 classes (Scholar, Engineer, Explorer, Artist, Guardian, Diplomat), unbounded levels with diminishing returns, personality traits that shift from behavior, functional bonuses to agent selector, rebirth cycles, PostgreSQL storage with daily snapshots (prd-pet-system-v2.md)
- GW-001-020: GlyphWeave Art Studio — 30-min art generation cycles experimenting with all models, scientific calibration framework, vision-based scoring, gallery website (prd-glyphweave-art-studio.md)
- LLM-001-016: Local LLM integration — Qwen3.5, Gemma3, llamafile for local routing/coding/vision, local-vs-cloud calibration (prd-local-llm-integration.md)

### 5. Self-Reflection
**Implemented:**
- `tools/reviewer.py` — Daily brief analyzes overnight activity, weekly retro identifies patterns and failure trends, monthly review tracks long-term evolution.
- Observatory queries — `get_agent_stats()`, `get_agent_skills()`, `get_healing_log()`, `get_routing_accuracy()` provide structured self-analysis.
- `tools/server_health.py` — Periodic health reflection (disk, memory, load, services) with auto-maintenance actions.
- Watchdog progress tracking — Records task completion rate, detects stalls, alerts on degradation.

**Planned:**
- PI-001: Proactive scanner — scan repos for outdated deps, security issues, CI failures at low-load times (prd-proactive-intelligence.md)
- PI-005: Enhanced morning briefing — overnight pipeline progress, failures, project health changes, pet events, natural-language summary via local LLM (prd-proactive-intelligence.md)
- PH-001-003: Project health dashboard — monitor deployed sites, GitHub repos, SSL certs, integrate into web platform (prd-proactive-intelligence.md)
- DR-001-004: Disaster recovery — private GitHub repo backup, continuous backup every 30 min, one-command full restore script (prd-proactive-intelligence.md)

### Summary & Gaps

**Strongest areas (well-implemented):**
- Self-healing — healer engine, I/O watchdog, pipeline watchdog, server health all working and battle-tested through multiple server crashes
- Basic introspection — Observatory event store + context pulse provide good system awareness
- Agent fitness evolution — selection improves over time based on real performance data

**Most significant gaps:**
1. **No RAG/long-term memory** — Each agent call starts from scratch. No semantic search over past conversations or decisions. This is the #1 gap limiting intelligence.
2. **No proactive self-improvement** — The system reacts to failures but doesn't proactively identify and fix patterns. The weekly retro generates reports but doesn't auto-apply improvements.
3. **Pet system is basic** — Single XP/stage tracking exists but multi-class evolution, personality traits, and functional bonuses are all planned but unbuilt.
4. **No verification system** — Code changes go through sdp-cli lead/verify but Telegram responses, routing decisions, and operational actions have no verification.
5. **No disaster recovery** — All state is on tmpfs (volatile) with 15-min cron backups. No cloud backup, no one-command restore.

**Priority gaps (zero implementation):**
- RAG vector store memory (RAG-001-005)
- Proactive scanner (PI-001)
- Autonomous low-risk fixes (PI-002)
- Cost tracking (CT-001-003)
- Project health monitoring (PH-001-003)
- Web platform (WEB-001-017)
