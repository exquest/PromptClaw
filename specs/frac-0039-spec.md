# Task frac-0039 Specification: PromptClaw Models Depth 2

## Problem Statement

`promptclaw/models.py` owns the core dataclasses shared by config loading,
routing, agent runtime, artifact writing, state persistence, memory summaries,
and prompt construction. It currently classifies at fractal depth 0 because it
contains only dataclass declarations and no functions. The dataclasses are
useful as transport objects, but operators and integration tests have no
single typed helper path that turns a config, route decision, agent, or run
state into meaningful JSON-safe diagnostic output.

This task deepens the module to a simple depth-2 implementation by adding
one stdlib-only summary/report path while preserving existing dataclass
fields and call sites. The recurring startup hardening gap is also in scope:
the CLI entry point already calls `bootstrap_identity()`, but ASGI runners
that import `cypherclaw.narrative_api.main:app` must also bootstrap identity
on startup so first boots mint and persist identity automatically.

## Technical Approach

- Add a frozen `ConfigModelReport` dataclass in `promptclaw/models.py` that
  captures project name, artifact root, control-plane mode, verification
  setting, retry count, and aggregate agent counts.
- Add typed pure helpers:
  - `sorted_agents(config)` for deterministic agent ordering.
  - `summarize_agent(agent)` for JSON-safe per-agent diagnostics.
  - `config_model_report(config)` for aggregate config counts.
  - `summarize_config_model(config)` for one JSON-safe config summary.
  - `summarize_route_decision(decision)` for route diagnostics.
  - `summarize_run_state(state)` for end-to-end run diagnostics.
- Preserve all existing dataclass fields and default values; no call site
  should need to change to keep current behavior.
- Wire `cypherclaw.narrative_api.main._build_app()` to call
  `bootstrap_identity()` before creating the FastAPI app, covering ASGI
  import startup in addition to `python -m cypherclaw.narrative_api`.
- Keep the startup path mode-neutral: the default bootstrap call reuses any
  existing standalone or federated identity and only mints on first boot.
- Do not add dependencies, migrations, database columns, provider secrets,
  runtime state files, or agent command strings.

## Edge Cases

- Config summaries must be deterministic even when `config.agents` was built
  from an unordered source, so agent rows are sorted by agent name.
- Command agents may configure either `command` or `shell_command`; either
  should count as command-configured in summaries.
- Disabled agents remain visible in summaries and contribute to
  `disabled_agent_count`.
- `summarize_run_state()` must handle missing verifier/final-summary fields
  without raising and must report useful counts for events, errors, recovery
  actions, and coherence violations.
- JSON-safe summaries must serialize with `json.dumps()` without custom
  encoders.
- ASGI import startup must call the real bootstrap path before app creation
  and must preserve the same identity between repeated boots.
- Existing daemon startup ordering remains authoritative for
  `bootstrap_identity()` before `FirstBootAnnouncer`.

## Acceptance Criteria

1. Existing config, routing, and orchestrator behavior remains unchanged.
   VERIFY: `pytest tests/test_config.py tests/test_router.py tests/test_orchestrator.py -q`

2. The models module exposes typed, deterministic config/agent summaries with
   meaningful counts and JSON-safe output.
   VERIFY: `pytest tests/test_promptclaw_models_depth.py::test_config_model_report_counts_agent_surface tests/test_promptclaw_models_depth.py::test_summarize_config_model_is_json_safe_and_sorted -q`

3. Route decisions and run states produce meaningful JSON-safe diagnostics,
   including an end-to-end orchestrator run summary.
   VERIFY: `pytest tests/test_promptclaw_models_depth.py::test_route_and_run_state_summaries_are_json_safe tests/test_promptclaw_models_depth.py::test_run_state_summary_matches_orchestrator_end_to_end -q`

4. Fractal depth for `promptclaw/models.py` reaches at least depth 2.
   VERIFY: `pytest tests/test_promptclaw_models_depth.py::test_models_module_reaches_depth_two -q`

5. ASGI startup imports bootstrap identity and preserve the same identity
   between repeated boots.
   VERIFY: `pytest tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Startup identity hardening remains covered for standalone/federated
   persistence and daemon bootstrap-before-announcer ordering.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_main_calls_bootstrap_identity -q`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
