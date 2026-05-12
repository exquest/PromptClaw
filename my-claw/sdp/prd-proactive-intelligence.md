# PRD: Proactive Intelligence, Cost Tracking, Disaster Recovery, Cross-Session Memory & Project Health

## Overview

Five interconnected systems that transform CypherClaw from a reactive tool into a proactive, self-managing AI that maintains institutional memory, tracks its own costs, monitors project health, backs itself up, and carries context across sessions. CypherClaw should act autonomously on low-risk tasks (dep updates, security patches, prompt improvements) and ask before high-risk actions (deployments, deletions, architecture changes).

**Depends on:** `prd-home-resilience.md` (reliable unattended runtime), `prd-model-awareness.md` (provider/model routing), `prd-verification-system.md` (safe autonomous action), `prd-context-engine.md` (cross-session operational memory), `prd-capability-approval-framework.md` (approval boundaries), `prd-local-llm-integration.md` (local models for RAG embedding/search), `prd-server-optimization.md` (auto-recovery infrastructure), `prd-web-platform.md` (dashboard for visibility)

## Execution Role

This is an autonomy multiplier, not a foundation PRD. It should follow the execution spine plus the continuity/governance layers.

## 1. Proactive Intelligence

CypherClaw proactively scans, detects, plans, and acts — not just when asked.

### Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| PI-001 | Create `tools/proactive_scanner.py` — a scheduler that runs scans at low-load times (load < 2.0, no active agents). Scans include: repo health (outdated deps, security advisories), deployed site uptime, SSL cert expiry, pipeline failure patterns, pet stat anomalies. Each scan type has a configurable interval and priority. React to events immediately: GitHub push → scan that repo, SSL < 14 days → escalate now. | MUST | T2 | - Scanner runs at low-load times only<br/>- 5+ scan types implemented<br/>- Event-reactive for high-priority items<br/>- Load-aware: pauses when agents are active<br/>- Scan results stored in Observatory |
| PI-002 | Implement autonomous action for low-risk tasks. When the scanner detects issues, auto-fix without asking: (a) outdated pip/npm deps in repos → create PR with update, (b) security advisory matches → create PR with patch, (c) own prompt improvements → update AGENTS.md or routing prompts based on Observatory failure patterns, (d) stale agent processes → kill, (e) service restarts → auto-recover. All autonomous actions logged to Observatory with before/after state. | MUST | T2 | - Auto-creates PRs for dep updates<br/>- Auto-updates own prompts from failure patterns<br/>- Auto-kills stale processes<br/>- All actions logged with audit trail<br/>- No autonomous deployment or deletion |
| PI-003 | Implement ask-before-act for high-risk tasks. When the scanner detects issues requiring human judgment: generate a plan/PRD, send it via Telegram (notification channel) and make it visible on the web platform, wait for Anthony's approval. High-risk includes: production deployments, repo deletions, architecture changes, spending above budget, changes to other people's projects. Track pending approvals with timeout alerts. | MUST | T2 | - High-risk actions generate approval requests<br/>- Sent to Telegram and visible on web platform<br/>- Approval/rejection tracked<br/>- Timeout alert after 24h of no response<br/>- No high-risk action without approval |
| PI-004 | Build a self-improvement feedback loop. Every week, analyze Observatory data: which agents fail most at which tasks, which routing decisions were wrong (agent returned error), which prompts produce empty responses. Auto-generate a "self-improvement report" with specific proposed changes to routing prompts, AGENTS.md, and agent selection weights. Apply low-risk improvements automatically, queue high-risk ones for approval. | SHOULD | T2 | - Weekly analysis runs automatically<br/>- Report identifies top 5 failure patterns<br/>- Proposes specific prompt/config changes<br/>- Low-risk changes auto-applied<br/>- Report visible on web platform and sent to Telegram |
| PI-005 | Create intelligent morning briefing. Every day at 7:30am, send a briefing that's actually useful: what the pipeline accomplished overnight (tasks completed, new code committed), any failures or issues that need attention, project health changes (site went down, cert expiring), pet evolution events, upcoming scheduled tasks. Use local LLM to generate a natural-language summary from raw data. | MUST | T1 | - Briefing sent at 7:30am daily<br/>- Covers overnight pipeline progress<br/>- Highlights issues needing attention<br/>- Natural language (not raw data dumps)<br/>- Sent to Telegram and web platform |

## 2. Cost Tracking

Track and manage API/CLI usage across all providers. Note: primary usage is via CLI (Pro accounts), not API. Costs estimated from input/output length and published pricing. Local models are free.

### Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CT-001 | Create `tools/cost_tracker.py` that estimates costs per agent invocation. For CLI usage: measure input prompt length (tokens estimated at ~4 chars/token) and output length, multiply by published per-token pricing for the model used. For API usage: parse response headers for actual token counts. Track per-model, per-day, per-task costs. Store in PostgreSQL table `cost_events` (timestamp, agent, model, input_tokens_est, output_tokens_est, cost_est_usd, source: cli/api, task_id). | MUST | T2 | - Cost estimated for every agent invocation<br/>- CLI and API usage both tracked<br/>- Per-model published pricing maintained<br/>- Daily/weekly cost aggregates queryable<br/>- Stored in PostgreSQL |
| CT-002 | Implement budget alerts and automatic degradation. Configure daily and weekly budget thresholds per provider. When approaching limit (80%): alert via Telegram. When exceeded (100%): automatically degrade to cheaper models — opus→sonnet→haiku for Claude, gpt-5.4→codex-spark for OpenAI, pro→flash for Gemini. When all cloud budgets tight: shift to local models (free). Budget resets daily/weekly. | MUST | T2 | - Budget thresholds configurable per provider<br/>- Alert at 80% of budget<br/>- Auto-degrade at 100%<br/>- Local models used as free fallback<br/>- Budget resets on schedule<br/>- Current spend visible via /cost command and web dashboard |
| CT-003 | Add `/cost` command to Telegram and web API. Shows: today's estimated spend by provider, this week's total, budget remaining, cost per task average, most expensive tasks, local vs cloud usage ratio. Compact format for Telegram, detailed table for web. | SHOULD | T1 | - `/cost` shows daily/weekly spend<br/>- Per-provider breakdown<br/>- Local vs cloud ratio shown<br/>- Budget remaining visible<br/>- Works in both Telegram and web |

## 3. Disaster Recovery

Full backup system with private GitHub repo as the single source of truth.

### Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| DR-001 | Create a private GitHub repo `cypherclaw-private` as monorepo backup. Structure: `code/` (CypherClaw daemon + tools), `config/` (sdp.toml, systemd services, nginx config, crontab), `state/` (state.db snapshots, Observatory snapshots), `history/` (conversation logs, event exports), `art/` (gallery renders, experiment data), `pets/` (pet snapshots), `prds/` (all PRDs and sdp artifacts). Use `gh` CLI to create and manage. Push automatically. | MUST | T2 | - Private repo created on GitHub<br/>- Directory structure established<br/>- Initial push with all current data<br/>- Repo accessible only to Anthony<br/>- .gitignore excludes API keys and secrets |
| DR-002 | Implement continuous backup to the private repo. Every 30 minutes: export state.db, Observatory events (since last export), pet snapshots, cost data, and conversation history to the private repo. Push via `git push`. Only push when there are actual changes (check git status first). Backup script runs via cron, logs to tmpfs. | MUST | T2 | - Auto-backup every 30 minutes<br/>- Only pushes when changes exist<br/>- State, Observatory, pets, history all backed up<br/>- Secrets excluded from backup<br/>- Backup log in tmpfs |
| DR-003 | Create `tools/full_restore.sh` — a one-command script that rebuilds CypherClaw from the private repo on any Ubuntu 24.04 machine. Steps: install system deps (Python, PostgreSQL, Redis, Ollama, Nginx, Docker), clone private repo, restore config files, restore databases, set up systemd services, set up tmpfs, start all services. Target: fresh machine to fully running CypherClaw in under 30 minutes. | SHOULD | T3 | - Script runs on fresh Ubuntu 24.04<br/>- Installs all dependencies<br/>- Restores all data from private repo<br/>- Sets up all systemd services<br/>- CypherClaw fully operational after script completes<br/>- Tested on a fresh VM |
| DR-004 | Implement pre-backup validation. Before each backup push: verify state.db is valid SQLite (not corrupted), verify Observatory DB is valid, verify pet data is parseable, verify no secrets in staged files. If validation fails, skip backup and alert via Telegram. Keep the last 7 days of state.db snapshots in the repo (rotating). | MUST | T1 | - Validation runs before every backup<br/>- Corrupted databases not pushed<br/>- Alert on validation failure<br/>- 7-day snapshot rotation<br/>- No secrets in repo (verified by pre-commit hook) |

## 4. Cross-Session Memory (RAG)

Searchable long-term memory that persists across Claude Code sessions.

### Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| RAG-001 | Create `tools/memory_store.py` — a vector store using local LLM embeddings (via Ollama). Index: all conversation messages (Telegram + web), Observatory events, task completion summaries, architectural decisions, failure post-mortems, pet evolution history. Use ChromaDB or a simple FAISS index stored on disk. Embedding model: nomic-embed-text via Ollama (384-dim, fast on CPU). | MUST | T2 | - Vector store created and populated<br/>- Conversations indexed with timestamps<br/>- Events indexed with metadata<br/>- Search returns relevant results for natural language queries<br/>- Embedding via local Ollama model (no cloud API) |
| RAG-002 | Implement automatic indexing pipeline. New data indexed as it arrives: (a) every Telegram/web message → index immediately, (b) every Observatory event → batch index every 5 minutes, (c) every task completion → index summary + verdict, (d) every pet evolution event → index, (e) every architectural decision (commit messages, PRD changes) → index. Each indexed item has: text, timestamp, source, metadata tags. | MUST | T2 | - Real-time indexing for messages<br/>- Batch indexing for events (5-min cycle)<br/>- All 5 data sources indexed<br/>- Metadata preserved for filtering<br/>- Index size manageable (<1GB for months of data) |
| RAG-003 | Create a context briefing system for new sessions. When the daemon detects a new Claude Code session (or web platform connection), automatically generate a context brief: (a) query the vector store for recent activity (last 48h), (b) summarize using local LLM, (c) include: what tasks completed, what failed, current pipeline state, any pending approvals, pet status, server health. Store the brief at `tools/workspace/session_brief.md` where the new session's CLAUDE.md can reference it. | MUST | T2 | - Brief generated on new session detection<br/>- Covers last 48h of activity<br/>- Summarized by local LLM (not raw data)<br/>- Stored at accessible path<br/>- Updated every 30 minutes while session is active |
| RAG-004 | Add semantic search to Telegram and web. `/remember <query>` searches the memory store and returns the top 5 most relevant items with context. On the web platform, a dedicated Memory tab with full search UI, filters by date/source/type, and browseable timeline view. | SHOULD | T2 | - `/remember` returns relevant results<br/>- Web platform has Memory tab<br/>- Filters by date, source, type<br/>- Results include surrounding context<br/>- Response time <5s for search queries |
| RAG-005 | Index the full conversation history from this session and all prior sessions. Parse the Claude Code JSONL transcript files at `~/.claude/projects/` and index all messages. This gives CypherClaw memory of everything that's ever been discussed. Run as a one-time migration, then continuous indexing going forward. | SHOULD | T2 | - All JSONL transcripts parsed and indexed<br/>- Historical context searchable<br/>- One-time migration completes without errors<br/>- Forward indexing continues automatically |

## 5. Project Health Dashboard

Monitor deployed sites and active repos.

### Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| PH-001 | Create `tools/project_health.py` — monitors deployed sites: tickets.cascadiantech.com, promptlab.cascadiantech.com, cascadiantech.com. Checks: HTTP status (200?), response time, SSL cert expiry date, DNS resolution. Run every 15 minutes. Alert immediately on: site down, SSL < 14 days, DNS failure. Store results in PostgreSQL `site_health` table. | MUST | T2 | - 3 sites monitored every 15 minutes<br/>- HTTP, SSL, DNS checks all working<br/>- Alerts on down/expiring/failing<br/>- Results in PostgreSQL<br/>- Historical uptime percentage queryable |
| PH-002 | Monitor active GitHub repos: CypherClaw (exquest/PromptClaw), PromptLab (exquest/LGPromptLab), CTTickets, LifeImprover, sdp-cli. Check: open PRs (count, age), last commit age, CI/Actions status (passing/failing), open issues count. Use `gh` CLI for queries. Run daily at 3am. Alert on: CI failing, PR older than 7 days, no commits in 14 days. | MUST | T2 | - 5+ repos monitored daily<br/>- PR, CI, commit, issue data collected<br/>- Alerts on failing CI and stale PRs<br/>- Data in PostgreSQL `repo_health` table<br/>- Accessible from web platform and Telegram |
| PH-003 | Integrate project health into morning briefing (PI-005) and web platform dashboard. Show: site uptime badges (green/red), repo status cards, SSL countdown, stale PR list. On the web platform, a Projects section with expandable cards per project. | SHOULD | T1 | - Site uptime visible on dashboard<br/>- Repo status cards on web platform<br/>- SSL expiry countdown shown<br/>- Integrated into morning briefing<br/>- Color-coded health indicators |

## Private Repo Structure

```
cypherclaw-private/
├── code/                    # Daemon + tools (synced from main repo)
│   ├── tools/
│   └── sdp/
├── config/                  # System configuration
│   ├── sdp.toml
│   ├── systemd/             # All service files
│   ├── nginx/               # Nginx config
│   ├── crontab.txt          # Exported crontab
│   └── env.encrypted        # Encrypted API keys (age/sops)
├── state/                   # Database snapshots
│   ├── state.db             # Latest sdp-cli state
│   ├── observatory.db       # Latest Observatory
│   └── snapshots/           # Rolling 7-day history
├── history/                 # Conversation & event logs
│   ├── conversations/       # Telegram + web chat logs
│   ├── events/              # Observatory event exports
│   └── decisions/           # Architectural decision records
├── art/                     # GlyphWeave gallery
│   ├── renders/             # PNG/GIF renders
│   └── metadata/            # Generation stats, scores
├── pets/                    # Pet evolution history
│   └── snapshots/           # Daily pet state snapshots
├── prds/                    # All PRDs
├── memory/                  # RAG vector store
│   └── index/               # ChromaDB/FAISS index files
└── restore/                 # Disaster recovery
    └── full_restore.sh      # One-command rebuild script
```

## Cost Estimation Model

| Provider | Model | Input $/1M tokens | Output $/1M tokens | CLI Estimation Method |
|----------|-------|-------------------|--------------------|-----------------------|
| Anthropic | claude-opus-4-6 | $15.00 | $75.00 | Prompt chars / 4 |
| Anthropic | claude-sonnet-4-6 | $3.00 | $15.00 | Prompt chars / 4 |
| Anthropic | claude-haiku-4-5 | $0.80 | $4.00 | Prompt chars / 4 |
| OpenAI | gpt-5.4 | $2.00 | $8.00 | Prompt chars / 4 |
| Google | gemini-3.1-pro | $1.25 | $5.00 | Prompt chars / 4 |
| Google | gemini-3-flash | $0.075 | $0.30 | Prompt chars / 4 |
| Local | all | $0.00 | $0.00 | Free |

Note: These are estimates for CLI usage via Pro accounts. Actual costs may differ. The tracker provides directional awareness, not accounting-grade precision.

## Success Metrics

| Metric | Target |
|--------|--------|
| Proactive scan coverage | All active repos + deployed sites scanned daily |
| Autonomous fix success rate | >90% of auto-applied fixes work correctly |
| Morning briefing usefulness | Covers all overnight activity, actionable |
| Cost tracking accuracy | Within 30% of actual (for CLI estimates) |
| Budget compliance | Never exceed daily budget by more than 20% |
| Backup reliability | 100% of scheduled backups succeed |
| Restore time | Fresh machine → running CypherClaw < 30 minutes |
| RAG search relevance | Top-5 results contain answer >80% of the time |
| Memory indexing latency | New messages indexed within 60 seconds |
| Site monitoring uptime | 100% of checks executed on schedule |
| Alert latency | < 5 minutes from detection to Telegram notification |
