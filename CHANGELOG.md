# Changelog

## Unreleased

- Added quota-aware graceful degradation for CypherClaw live command routing using `sdp-cli` provider headroom.
- Added provider status monitoring, runtime quota-error detection, Telegram `/quota` reporting, and routing fallback away from exhausted providers.
- Added quota-aware selector and daemon tests covering degraded-mode routing, retry fallback, and provider status transitions.
- Added disk-authoritative resilience tools for CypherClaw runtime operations: checkpoint export, preflight validation, maintenance-mode state, tmpfs workdir bootstrap, runner launcher, and safe reboot flow.
- Added systemd unit definitions for `cypherclaw-bootstrap.service` and `cypherclaw-sdp-runner.service`.
- Removed backup-restore and ad hoc pipeline-start behavior from `boot_hardening.sh` so runtime authority stays with the managed bootstrap and runner path.
- Unified `promptclaw doctor` with optional runtime preflight so live CypherClaw roots report config health and runtime readiness through one entry point.

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
