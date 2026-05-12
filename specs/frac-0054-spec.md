# Task frac-0054 Specification: conftest Depth 2

## Problem Statement

`tests/conftest.py` owns repository-wide pytest startup behavior: it adds
`src/` to `sys.path`, registers live-test options and markers, and skips
expensive or host-specific tests when their opt-in conditions are not met.
It currently classifies at fractal depth 1 because two of the three pytest
hook functions are direct call sequences and only the collection hook has
branching logic (`2/3 trivial, 1 real`).

That leaves no module-owned typed surface for tests, diagnostics, or future
hooks to inspect:

- Which collection gates exist.
- Whether a marker is enabled for a given pytest config/environment.
- How many collected items match each gated marker.
- How many items were skipped by each gate.
- A JSON-safe summary of the gating decision that preserves the hook's
  default behavior.

This task deepens `tests/conftest.py` to a simple depth-2 implementation:
one path, meaningful output, and an end-to-end `decide -> apply -> summarize`
flow while preserving existing pytest option/marker names and skip reasons.

## Technical Approach

- Add a frozen `CollectionGateDecision` dataclass to represent one marker
  gate with fields for marker name, option source, enabled state, skip
  reason, matched item count, and skipped item count.
- Store the existing option definitions and marker definitions in typed
  module constants.
- Refactor `pytest_addoption` and `pytest_configure` to iterate those
  constants. The externally visible pytest options and marker descriptions
  remain unchanged.
- Add `collection_gate_decisions(config, items, environ=None) -> tuple[CollectionGateDecision, ...]`
  to compute the live Modal, live Replicate, and CypherClaw e2e decisions.
  The default environment source is `os.environ`; tests may inject a mapping.
- Add `apply_collection_gate_decisions(config, items, environ=None) -> tuple[CollectionGateDecision, ...]`
  to apply `pytest.mark.skip(...)` to matching items when a decision is not
  enabled, returning the same decisions with concrete match/skip counts.
- Add `summarize_collection_gate_decisions(decisions) -> dict[str, object]`
  to emit JSON-safe totals and per-marker rows.
- Refactor `pytest_collection_modifyitems` to call the application helper.
- Use only the standard library plus existing `pytest`; no new dependencies,
  migrations, provider secrets, database columns, runtime state files, HTTP
  routes, or auth changes are required.

## Edge Cases

- Live Modal tests stay skipped by default unless `--run-live-modal` is set.
- Live Replicate tests stay skipped by default unless `--run-live-replicate`
  is set; the existing test-level `REPLICATE_API_TOKEN` guard remains
  responsible for token presence.
- `cypherclaw_e2e` tests remain runnable by default on a local host and are
  skipped only when `CI` is present in the environment, matching the current
  hook behavior and the generation PRD wording.
- Items without gated markers are never modified.
- The summary renders tuples as lists/dicts so `json.dumps(...)` works.
- The startup identity hardening bullets target the app/daemon startup
  subsystem outside `tests/conftest.py`; this task re-runs the existing
  startup identity anchors as mandatory regression coverage.

## Acceptance Criteria

1. `tests.conftest` exposes a frozen `CollectionGateDecision` dataclass and
   the collection-gate helper surface.
   VERIFY: `pytest tests/test_conftest_depth.py::test_conftest_exposes_collection_gate_surface -q`

2. `pytest_addoption` registers the existing live Modal and live Replicate
   opt-in flags.
   VERIFY: `pytest tests/test_conftest_depth.py::test_pytest_addoption_registers_live_flags -q`

3. `pytest_configure` registers the existing `live_modal`, `live_replicate`,
   and `cypherclaw_e2e` marker descriptions.
   VERIFY: `pytest tests/test_conftest_depth.py::test_pytest_configure_registers_expected_markers -q`

4. Default collection gating skips `live_modal` and `live_replicate` items
   while leaving `cypherclaw_e2e` runnable off CI.
   VERIFY: `pytest tests/test_conftest_depth.py::test_default_gate_application_skips_live_markers_only -q`

5. Enabled live flags allow live Modal/Replicate items while `CI` skips
   `cypherclaw_e2e` items.
   VERIFY: `pytest tests/test_conftest_depth.py::test_enabled_live_flags_and_ci_gate_apply_expected_skips -q`

6. `summarize_collection_gate_decisions` emits JSON-safe totals and
   per-marker rows.
   VERIFY: `pytest tests/test_conftest_depth.py::test_collection_gate_summary_is_json_safe -q`

7. Fractal depth for `tests/conftest.py` reaches at least depth 2.
   VERIFY: `pytest tests/test_conftest_depth.py::test_conftest_reaches_depth_two -q`

8. Startup identity hardening remains covered for CLI startup and
   standalone/federated first-boot persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
