# Task frac-0108 Specification: test_router Depth 2

## Problem Statement

`tests/test_router.py` currently covers the PromptClaw heuristic router at
helper depth: `infer_task_type` is checked for the `code` and `architecture`
families, `detect_ambiguity` is checked once for a vague phrase, and
`heuristic_route` is checked for two lead-agent assignments. Missing depth-2
coverage is a single end-to-end path that drives the public router surface
through one realistic routing lifecycle: agent-catalog rendering, task-type
inference, ambiguity detection, lead/verifier selection (with trust filtering),
markdown rendering, and round-trip JSON parsing via `parse_route_decision`.

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

- Add `tests/test_test_router_depth.py` using the established depth gate
  pattern. The gate requires:
  - `RouterEndToEndTests` exists in `tests/test_router.py`;
  - the named method
    `test_route_lifecycle_renders_markdown_and_round_trips_decision`
    exists;
  - `classify_depth("tests/test_router.py").depth >= 2`.
- Confirm the red phase by running the new depth gate before the end-to-end
  class exists.
- Append `RouterEndToEndTests` to `tests/test_router.py` without modifying
  existing locked assertions. The class drives one deterministic path:
  - build a `default_project_config(...)` and assert
    `agent_catalog_markdown(...)` lists each enabled agent with its
    capabilities;
  - call `heuristic_route(...)` on a code-implementation task and assert the
    decision is non-ambiguous, `lead_agent == "codex"`, the verifier agent is
    enabled and distinct from the lead, `task_type == "code"`, and confidence
    sits above the ambiguous threshold;
  - call `heuristic_route(...)` again with a `trust_scores` mapping that zeroes
    `codex` trust and assert the lead agent shifts away from `codex`, proving
    trust filtering participates in the lifecycle;
  - call `heuristic_route(...)` on an explicitly vague task and assert
    ambiguity is detected, a clarification question is generated, and the
    confidence drops below the non-ambiguous case;
  - call `route_markdown(...)` on the primary decision and assert the rendered
    block contains the lead, verifier, task type, confidence, reason, and
    handoff brief;
  - serialize the primary decision to JSON, round-trip it through
    `parse_route_decision(...)`, and assert structural equality on
    `lead_agent`, `verifier_agent`, `task_type`, and `ambiguous`;
  - build a primitive diagnostic payload from the catalog markdown, the
    primary/trust-shifted/ambiguous decisions, and the round-tripped decision,
    then verify it survives `json.dumps(..., sort_keys=True)` /
    `json.loads(...)`.
- Preserve production behavior in `promptclaw/router.py` unless the red tests
  expose a concrete implementation gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The new end-to-end path intentionally covers one simple happy path. Existing
  focused tests continue to own individual properties such as code-vs-
  architecture inference and the original ambiguity check.
- The trust-shift assertion only checks that `codex` is no longer the lead when
  its trust drops below the 0.2 floor; it does not pin the exact replacement
  because ranking ties depend on capability counts.
- Round-trip parsing uses the JSON object emitted from the dataclass, which
  matches the contract `parse_route_decision` already accepts.
- Startup identity hardening remains a regression anchor and is not widened
  inside the router module.
- No database schema, foreign keys, or migrations are introduced.

## Acceptance Criteria

1. Existing router assertions remain green.
   VERIFY: `pytest tests/test_router.py -q`

2. The depth gate confirms `tests/test_router.py` reaches depth >= 2 and
   contains the named end-to-end class/method.
   VERIFY: `pytest tests/test_test_router_depth.py -q`

3. `RouterEndToEndTests` drives the full router lifecycle and JSON-safe
   diagnostics.
   VERIFY: `pytest tests/test_router.py::RouterEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0108 router test deepening with
   no new dependencies or migrations.
   VERIFY: `grep -n "frac-0108" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
