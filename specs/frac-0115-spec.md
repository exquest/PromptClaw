# Task frac-0115 Specification: test_startle Depth 2

## Problem Statement

`tests/test_startle.py` currently verifies `my-claw/tools/senseweave/startle.py`
at focused helper depth: RMS spike detection, cooldown readiness,
`StartleState` defaults, state replacement on quiet/startled paths, face
reaction shape, and mute recommendation thresholds.

Missing depth-2 coverage is a single realistic end-to-end test path proving
the public startle surface produces meaningful output across the full
lifecycle:

1. quiet room input does not startle and renders a calm face,
2. a loud spike over the rolling baseline creates a startled state,
3. a second spike during cooldown is blocked,
4. later spikes after cooldown still inside the 30-second recent-startle
   window increment count and eventually recommend muting,
5. a stable operator-style diagnostic captures state, face, mute, and
   detection details in JSON-safe form.

The production module already implements this one-path behavior. This task
therefore deepens the test surface unless the red tests expose a concrete
source gap.

The generated startup identity hardening bullets target the existing identity
startup subsystem. Current CLI, first-boot, daemon-ordering, and narrative
ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer`
plus standalone/federated identity persistence. This task keeps those tests as
mandatory regression anchors rather than changing unrelated startup code.

The active ADP process is the task prompt's Explore -> Specify -> Test ->
Implement -> Verify -> Document workflow, as mirrored in
`sdp/templates/candidates/lead_t2/v006.md`.

## Technical Approach

- Add `tests/test_test_startle_depth.py` using the recent depth-gate pattern.
  The gate requires:
  - `StartleEndToEndTests` exists in `tests/test_startle.py`;
  - the named method
    `test_startle_lifecycle_reacts_cools_down_mutes_and_round_trips_json_diagnostic`
    exists;
  - `classify_depth("tests/test_startle.py").depth >= 2`.
- Confirm the red phase by running the new depth gate before the end-to-end
  class exists.
- Append `StartleEndToEndTests` to `tests/test_startle.py` without modifying
  existing locked assertions. The class drives one deterministic path:
  - use a monkeypatched clock so cooldown and recent-startle timing are stable;
  - call `detect_startle(...)` and `startle_cooldown(...)` as explicit
    preflight checks for quiet and loud samples;
  - run `update_startle(...)` through quiet, first-startle, cooldown-blocked,
    second-startle, and third-startle states;
  - use `startle_to_face_reaction(...)` and `should_mute_output(...)` to render
    consumer-facing outputs from those states;
  - build a primitive diagnostic payload and verify
    `json.dumps(..., sort_keys=True)` / `json.loads(...)` round-trips it.
- Preserve production behavior unless the red tests reveal a runtime gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- This is intentionally one simple happy path for depth-2 coverage. Existing
  focused tests remain responsible for boundary thresholds, zero baselines,
  exact cooldown boundaries, and fallback mute-count logic.
- The monkeypatched clock keeps cooldown and 30-second mute-window behavior
  deterministic without sleeping.
- The diagnostic payload only stores strings, booleans, ints, floats, lists,
  and nested dicts, so JSON serialization stays deterministic and hermetic.
- No database schema changes are introduced, so no migration or index work is
  required.
- Startup identity hardening remains a regression anchor and is not widened
  inside the startle tests.

## Acceptance Criteria

1. Existing startle assertions remain green.
   VERIFY: `pytest tests/test_startle.py -q`

2. The depth gate confirms `tests/test_startle.py` reaches depth >= 2 and
   contains the named end-to-end class/method.
   VERIFY: `pytest tests/test_test_startle_depth.py -q`

3. `StartleEndToEndTests` drives the quiet/startled/cooldown/repeated-startle
   lifecycle, face reaction, mute recommendation, and JSON-safe diagnostic.
   VERIFY: `pytest tests/test_startle.py::StartleEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0115 startle test deepening with
   no new dependencies or migrations.
   VERIFY: `grep -n "frac-0115" CHANGELOG.md progress.md ESCALATIONS.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
