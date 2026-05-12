# Task frac-0107 Specification: test_research_runtime Depth 2

## Problem Statement

`tests/test_research_runtime.py` currently covers the CypherClaw research
runtime at helper depth: scope classification, medium-report generation,
quick research, web page cleaning, subprocess experiment delegation, and
benchmark aggregation each have focused assertions. The missing depth-2
coverage is a single end-to-end path that drives the public research runtime
through automatic scope classification, multi-agent deep research synthesis,
tool findings, persisted report output, observability events, and JSON-safe
operator diagnostics.

The generated startup identity hardening bullets target the existing identity
startup subsystem. Exploration found that daemon poll loops already call
`bootstrap_identity()` before `FirstBootAnnouncer`, and CLI, first-boot, and
narrative ASGI tests already verify standalone/federated identity persistence.
This task keeps those tests as mandatory regression anchors rather than
changing unrelated startup code.

No standalone ADP documentation file was found beyond the task prompt's
Explore -> Specify -> Test -> Implement -> Verify -> Document workflow, so this
spec treats that prompt workflow as the active ADP process.

## Technical Approach

- Add `tests/test_test_research_runtime_depth.py` using the established depth
  gate pattern. The gate requires:
  - `ResearchRuntimeEndToEndTests` exists in `tests/test_research_runtime.py`;
  - the named method
    `test_auto_deep_research_persists_verified_report_and_json_diagnostic`
    exists;
  - `classify_depth("tests/test_research_runtime.py").depth >= 2`.
- Confirm the red phase by running the new depth gate before the end-to-end
  class exists.
- Append `ResearchRuntimeEndToEndTests` to `tests/test_research_runtime.py`
  without modifying existing locked assertions. The class drives one
  deterministic path:
  - instantiate `Researcher` with fake send and Observatory callbacks;
  - replace `tools` with the existing `FakeTools` test double;
  - monkeypatch `_run_agent(...)` with deterministic Claude/Gemini/Codex
    responses;
  - call `research(..., scope="auto")` with a query that classifies as `deep`
    and triggers web, academic, and local-code findings;
  - assert meaningful `ResearchResult` output: `scope == "deep"`,
    `verified is True`, non-empty summary/report, three sources, and a
    high/medium/low confidence breakdown;
  - assert lifecycle side effects: research-started/completed events,
    user-facing progress messages, expected agent invocations, and one
    persisted markdown report under the configured workspace;
  - build a primitive diagnostic payload from result fields, findings,
    messages, events, and agent calls, then round-trip it through
    `json.dumps(..., sort_keys=True)` / `json.loads(...)`.
- Preserve production behavior in `my-claw/tools/researcher.py` and
  `my-claw/tools/research_tools.py` unless the red tests expose a concrete
  implementation gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The new end-to-end path intentionally covers one simple happy path. Existing
  focused tests continue to own individual properties such as quick/medium
  routing, HTML cleanup, experiment execution, and benchmark ordering.
- The fake agent runner keeps the test hermetic and prevents live provider
  calls, matching the requirement to mock external services in tests.
- The deep path uses `ThreadPoolExecutor`; assertions count agent calls by
  provider instead of depending on concurrent call ordering.
- Report persistence uses `tmp_path` so the test does not write runtime state
  under `.promptclaw/` or the operator home.
- Startup identity hardening remains a regression anchor and is not widened
  inside the research-runtime module.
- No database schema, foreign keys, or migrations are introduced.

## Acceptance Criteria

1. Existing research-runtime assertions remain green.
   VERIFY: `pytest tests/test_research_runtime.py -q`

2. The depth gate confirms `tests/test_research_runtime.py` reaches depth >= 2
   and contains the named end-to-end class/method.
   VERIFY: `pytest tests/test_test_research_runtime_depth.py -q`

3. `ResearchRuntimeEndToEndTests` drives the full auto-deep research lifecycle
   and JSON-safe diagnostics.
   VERIFY: `pytest tests/test_research_runtime.py::ResearchRuntimeEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0107 research-runtime test
   deepening with no new dependencies or migrations.
   VERIFY: `grep -n "frac-0107" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
