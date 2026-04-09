# Changelog

## Unreleased

- Added a Telegram `/local` built-in backed by a shared daemon status snapshot so operators can request per-socket Ollama health, loaded models, and latency on demand.
- Wired `ollama_health()` into the `/status` Telegram command and half-hour heartbeat so operators can see per-socket Ollama health, loaded models, and latency without SSH.
- Added daemon-local `ollama_health()` dual-socket reporting for ports `11434` and `11435`, including per-instance loaded models and measured probe latency.
- Added quota-aware graceful degradation for CypherClaw live command routing using `sdp-cli` provider headroom.
- Hardened the managed runner service contract: `cypherclaw-sdp-runner.service` now uses `Restart=always` so clean `sdp-cli run` exits do not strand the queue, while maintenance-gated launcher exits use status `75` and are treated as intentional non-restarting stops.
- Hardened the managed runner launcher so it auto-exports a sibling `sdp-cli/src` checkout into `PYTHONPATH` when available, keeping the live runner on the checked-out source tree instead of a stale installed package.
- Added provider status monitoring, runtime quota-error detection, Telegram `/quota` reporting, and routing fallback away from exhausted providers.
- Hardened `my-claw/tools/telegram.py` so pytest-driven or explicit test-mode subprocesses suppress live bot sends by default; operators must set `PROMPTCLAW_ALLOW_LIVE_TELEGRAM=1` to allow real Telegram delivery during drills.
- Extended Telegram suppression to copied tmpfs task-run workdirs under `/run/cypherclaw-tmp/workdir/`, so live queue tasks that execute pytest or drill code from the ephemeral workdir cannot leak reboot/checkpoint alerts into the operator chat unless explicitly opted in.
- Added quota-aware selector and daemon tests covering degraded-mode routing, retry fallback, and provider status transitions.
- Added a queue-backed Telegram `/prd` built-in so roadmap summaries follow the live dependency graph instead of routed prose.
- Taught Telegram `/prd` to load stage order from `sdp/execution-roadmap.md` and batch mappings from `sdp/execution-roadmap.queue-map.json`, so roadmap output follows the current clone/identity/embodiment/publication plan instead of a stale hardcoded stage list.
- Made Telegram `/prd` stage labels more descriptive: frozen-only stages now render as `frozen`, split-parent-only stages render as `decomposed`, and `not loaded` now means the roadmap stage truly has no queued work.
- Replaced Telegram `/tasks` with a queue-backed operator view that shows running work, next root tasks, split-needed work, and attention items by default, plus filtered views like `/tasks pending 10`, `/tasks attention`, `/tasks frozen`, and `/tasks all 20`.
- Added roadmap-aware `/tasks` views so operators can inspect one implementation stage at a time with `/tasks prd <n>` or `/tasks stage <name>`, using the same roadmap/batch mapping as `/prd`.
- Taught Telegram `/monitor` to prefer the real `sdp-cli monitor --last` snapshot when available, so Telegram now mirrors the live run/phase/timing/quota/risk panel from the terminal monitor instead of a thinner daemon-only summary.
- Expanded Telegram `/monitor` with compact `sdp-cli`-style status lines for completion gate, latest completed run verdict/pair, and live per-agent quota/provider health.
- Added a queue-backed Telegram `/monitor` built-in so live queue progress and active task status come from the authority DB instead of stale routed status text.
- Unified queue-progress totals across Telegram and `sdp-cli`: counts now use live executable tasks and exclude only split parents.
- Normalized Telegram `/monitor` and `/prd` status buckets with `sdp-cli` so split parents show as `skipped` and live pending/blocked/running counts match the CLI.
- Kept `needs_split` as a first-class queue bucket across Telegram and `sdp-cli` instead of folding it into `pending`, so queue shape remains visible during decomposition.
- Added long-term active-run drift detection and repair for stale open `task_runs`, and taught `/monitor` to surface queue-state drift explicitly when runtime bookkeeping falls out of sync.
- Added the missing `OPT-005` half-hour Telegram heartbeat in the live daemon scheduler, including uptime, I/O wait, memory, load, available-agent count, queue progress, pet XP summary, and Observatory logging.
- Added disk-authoritative resilience tools for CypherClaw runtime operations: checkpoint export, preflight validation, maintenance-mode state, tmpfs workdir bootstrap, runner launcher, and safe reboot flow.
- Hardened maintenance-mode authority and safety: the canonical flag now lives at `.sdp/MAINTENANCE`, direct maintenance entry refuses to stop an active runner without an explicit operator override, and `safe_reboot.sh prepare` uses that override automatically.
- Hardened the managed runner restart path so stale `.sdp/run.lock` files are repaired automatically before preflight, preventing systemd restart loops after a dead runner PID is left behind.
- Added systemd unit definitions for `cypherclaw-bootstrap.service` and `cypherclaw-sdp-runner.service`.
- Removed backup-restore and ad hoc pipeline-start behavior from `boot_hardening.sh` so runtime authority stays with the managed bootstrap and runner path.
- Unified `promptclaw doctor` with optional runtime preflight so live CypherClaw roots report config health and runtime readiness through one entry point.
- Hardened the CypherClaw Telegram helper so bot token and chat ID must come from environment instead of hardcoded defaults.
- Hardened runtime portability across the MacBook and Linux server homes: daemon status checks are platform-aware, optional watchdog imports no longer break type checks, and dashboard/Gemini-image/test fixtures no longer assume a single repo layout.
- Sanitized daemon child-process environments so agent CLIs and helper commands no longer inherit systemd watchdog variables or spam `Got notification message from PID ...` warnings in the service journal.
- Added Observatory-backed semaphore visibility for the live daemon and restored full dashboard compatibility coverage so server-side `pytest` and `mypy src tools` gates pass again.

## 3.0.0

### Coherence Engine (core feature)
- Added event-sourced state system replacing JSON file-based state store.
- Added SQLite event store (zero-dependency) with PostgreSQL backend for production.
- Added Decision Store for Architecture Decision Records (ADRs) with keyword-based retrieval.
- Added Constitutional Enforcement with YAML/JSON rule definitions, regex and keyword matching.
- Added per-agent Trust Scoring (0.0-1.0) with penalties for violations and rewards for compliance.
- Added Self-Graduating Enforcement that auto-promotes from monitor to soft to full mode.
- Added 7 orchestrator hooks (pre/post routing, lead, verify, and finalize) for coherence checks.
- Added decision context and constitutional rules injection into agent prompts.
- Added NullCoherenceEngine fallback for graceful degradation.
- Added optional dependencies: `pip install promptclaw[coherence-pg]` for PostgreSQL + Redis + pgvector.
- Added example constitution at `examples/constitution.json`.

### Infrastructure
- Added `promptclaw/coherence/` package with 7 modules and 70+ dedicated tests.
- Updated prompt_builder.py with `coherence_context` parameter on all build functions.
- Updated orchestrator.py with coherence engine initialization and hook calls.
- Updated config.py to load coherence configuration from `promptclaw.json`.
- Updated pyproject.toml with optional dependency groups.

## 2.1.0

- Fixed live command-agent path rendering so `{prompt_file}` and `{project_root}` resolve correctly even when commands are launched from a relative project path.
- Added an interactive startup wizard that asks onboarding questions one at a time.
- Added heuristic follow-up questions when startup answers are vague or underspecified.
- Added playful terminal styling with ASCII and emoji output for project creation and wizard flows.
- Added startup artifacts: `docs/STARTUP_PROFILE.md`, `docs/STARTUP_TRANSCRIPT.md`, and `.promptclaw/onboarding/startup-session.md`.
- Added agent roster customization and capability inference during startup.
- Improved heuristic clarification questions for ambiguous runtime tasks.
- Updated docs and manuals to reflect the new onboarding flow.

## 2.0.0

- Added an LLM-driven orchestrator control plane with heuristic fallback.
- Added artifact-based handoff flow for lead, verify, and clarification phases.
- Added project bootstrap commands for creating custom PromptClaw projects.
- Added rolling project memory, run state, and resumable clarification flow.
- Added markdown-first docs and starter prompt packs for building new claws.
