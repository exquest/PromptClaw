# Task frac-0076 Specification: test_generation_client_protocol Depth 2

## Problem Statement

`tests/test_generation_client_protocol.py` covers the shared generation
protocol shape and one typed Replicate path, but it does not yet prove the
protocol helpers work as one deterministic end-to-end surface. The production
module `my-claw/tools/senseweave/generation/client_protocol.py` already
implements meaningful output helpers:

- `cost_per_second`
- `result_summary`
- `format_result_log_line`
- `validate_generation_result`

The gap is the test surface. The suite should demonstrate that a
`GenerationClient` implementation can accept a typed `GenerationRequest`,
return a `GenerationResult`, summarize it for operators, render a single-line
log entry, validate it against the request, and expose JSON-safe diagnostics.

## Technical Approach

- Preserve existing assertions in `tests/test_generation_client_protocol.py`.
- Add a depth gate in `tests/test_test_generation_client_protocol_depth.py`
  requiring `tests/test_generation_client_protocol.py` to contain
  `GenerationClientProtocolEndToEndTests` and classify at depth >= 2.
- Append `GenerationClientProtocolEndToEndTests` to
  `tests/test_generation_client_protocol.py`.
- Drive the existing public protocol helpers through a small fake client that
  writes no external runtime state and returns typed `GenerationResult` values.
- Cover one deterministic happy path:
  - request -> client.generate -> `GenerationResult`
  - `result_summary` JSON round-trip
  - `format_result_log_line` operator output
  - `cost_per_second` agreement with summary output
  - `validate_generation_result` success and ordered failure reasons
  - runtime `GenerationClient` structural checks for fake and Replicate clients
- Keep production source unchanged unless the tests expose a real behavior gap.
- Treat generated startup identity hardening checks as regression anchors.
  Existing CLI, daemon, first-boot, and narrative ASGI tests already cover
  `bootstrap_identity()` before `FirstBootAnnouncer` and persistence across
  standalone/federated boots, so this task re-runs those tests rather than
  changing unrelated startup flow.

## Edge Cases

- This depth-2 pass intentionally exercises one deterministic protocol path,
  not every invalid request shape.
- Duration, model, and CLAP centroid validation remain owned by
  `GenerationRequest`; protocol result validation compares an already-created
  request/result pair.
- JSON diagnostics must use only JSON-safe primitives and stringified paths.
- Empty request ids are still covered by the existing log-line fallback test.
- No new dependencies, migrations, provider secrets, database columns, runtime
  state directories, HTTP routes, or auth behavior are introduced.

## Acceptance Criteria

1. Existing generation protocol tests remain green.
   VERIFY: `pytest tests/test_generation_client_protocol.py -q`

2. The new depth gate confirms `tests/test_generation_client_protocol.py`
   reaches depth >= 2 and contains `GenerationClientProtocolEndToEndTests`.
   VERIFY: `pytest tests/test_test_generation_client_protocol_depth.py -q`

3. `GenerationClientProtocolEndToEndTests` drives the full typed request,
   generated result, summary, log-line, validation, JSON-safe diagnostic, and
   structural protocol path through the public API.
   VERIFY: `pytest tests/test_generation_client_protocol.py::GenerationClientProtocolEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, standalone and
   federated identity persistence, daemon bootstrap-before-announcer ordering,
   and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing notes mention the frac-0076 generation protocol depth-2
   work.
   VERIFY: `grep -n "frac-0076" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
