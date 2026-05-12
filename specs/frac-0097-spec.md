# Task frac-0097 Specification: test_ollama_routing Depth 2

## Problem Statement

`tests/test_ollama_routing.py` covers the R750 dual-socket Ollama route table at
focused level: built-in roles exist, socket ports are pinned to 11434/11435,
`get_ollama_route(...)` returns model/port pairs, unknown categories fall back
to `default`, route dictionaries are returned by copy, and
`OLLAMA_ROUTE_JSON` can override or extend routes.

The missing frac-0097 work is to make the depth-2 contract explicit for this
test module. The production route implementation in
`my-claw/tools/agent_selector.py` already exposes the simple one-path behavior:
`OLLAMA_ROUTE_DEFAULTS`, `_load_ollama_routes()`, and
`get_ollama_route(category)`. This task deepens the test surface with a
deterministic depth gate plus one end-to-end class that drives the existing
routing surface through default selection, env override merge, fallback routing,
copy isolation, and JSON-safe diagnostic serialization.

The generated startup identity hardening bullets target the existing identity
startup subsystem. This checkout already wires `bootstrap_identity()` into both
daemon poll loops before `FirstBootAnnouncer`, and the CLI/narrative ASGI paths
plus standalone/federated identity persistence are covered by regression tests.
This task keeps those tests as mandatory hardening anchors rather than changing
unrelated startup code without a discovered gap.

## Technical Approach

- Add `tests/test_test_ollama_routing_depth.py` with a deterministic depth gate
  requiring `tests/test_ollama_routing.py` to contain
  `OllamaRoutingEndToEndTests` and classify at depth >= 2 through the repo-local
  `sdp.fractal.classify_depth`.
- Confirm the red phase by running the new depth gate before
  `OllamaRoutingEndToEndTests` exists.
- Append `OllamaRoutingEndToEndTests` to `tests/test_ollama_routing.py` without
  modifying existing locked assertions.
- Drive one meaningful routing lifecycle inside the class:
  - start from defaults and confirm coding, review, netops, orchestrator, and
    default resolve to the expected socket/model pairs;
  - set one `OLLAMA_ROUTE_JSON` payload that overrides coding, adds writing,
    includes an incomplete ignored review override, and leaves unmentioned roles
    intact;
  - confirm unknown categories fall back to the active default route;
  - mutate one returned route and confirm a fresh lookup is isolated from that
    mutation;
  - serialize a combined diagnostic payload through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)` so routing output is
    safe for operator status surfaces.
- Preserve existing production behavior unless the red tests expose a concrete
  gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path intentionally covers one default route table, one merged
  env override payload, and one unknown-category fallback. Existing focused
  tests continue to own malformed JSON, empty env, non-dict env, and single-role
  override branches.
- Incomplete override entries are ignored so partial env data cannot erase a
  known production route.
- Route lookups must return copies; caller mutation must not modify subsequent
  route resolution.
- Startup identity hardening remains covered by the existing CLI, first-boot,
  daemon-ordering, and narrative ASGI tests; this task does not change identity
  startup wiring.

## Acceptance Criteria

1. Existing Ollama routing assertions remain green.
   VERIFY: `pytest tests/test_ollama_routing.py -q`

2. The depth gate confirms `tests/test_ollama_routing.py` reaches depth >= 2
   and contains `OllamaRoutingEndToEndTests`.
   VERIFY: `pytest tests/test_test_ollama_routing_depth.py -q`

3. `OllamaRoutingEndToEndTests` drives one meaningful routing lifecycle through
   defaults, env override merge, fallback routing, copy isolation, and JSON-safe
   diagnostics.
   VERIFY: `pytest tests/test_ollama_routing.py::OllamaRoutingEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0097 Ollama routing test
   deepening.
   VERIFY: `grep -n "frac-0097" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
