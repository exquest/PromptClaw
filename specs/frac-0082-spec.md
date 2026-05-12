# Task frac-0082 Specification: test_groove_engine Depth 2

## Problem Statement

`tests/test_groove_engine.py` already has broad helper-level coverage for
`my-claw/tools/senseweave/groove_engine.py`: profile lookup, swing IOI math,
meter policies, microtiming, breath points, polyrhythm/polymeter metadata,
entrainment nudges, tempo-dependent swing, and tracker scene propagation.
The missing depth-2 work is a named end-to-end test path that proves those
functions produce meaningful output together through the tracker scene contract.

The affected production surface already implements the simple one-path groove
runtime:

- `groove_for_section`
- `meter_policy_for_phase`
- `apply_groove_to_ioi`
- `groove_metadata_for_step`
- `entrainment_tempo_nudge`
- `build_scene_from_score` groove metadata propagation in
  `my-claw/tools/senseweave/music_tracker.py`

This task deepens the test surface without changing existing locked assertions
unless the new red tests expose a concrete production gap.

## Technical Approach

- Preserve existing assertions in `tests/test_groove_engine.py`.
- Add a depth gate at `tests/test_test_groove_engine_depth.py` that requires
  `tests/test_groove_engine.py` to contain `GrooveEngineEndToEndTests` and to
  classify at depth >= 2 through the repo-local `sdp.fractal.classify_depth`.
- Append `GrooveEngineEndToEndTests` to `tests/test_groove_engine.py`. The
  class will drive one deterministic groove path through profile resolution,
  meter policy overlay, IOI adjustment, metadata generation, scene compilation,
  JSON-safe diagnostics, and entrainment.
- Use only stdlib test support and existing `senseweave` imports.
- Treat the generated startup identity hardening checks as regression anchors.
  Existing CLI, first-boot, daemon-ordering, and narrative ASGI tests already
  cover `bootstrap_identity()` before `FirstBootAnnouncer` and identity
  persistence across standalone/federated boots, so this task re-runs those
  anchors instead of broadening groove-engine code.

## Edge Cases

- This depth-2 pass intentionally exercises one deterministic happy path rather
  than expanding malformed-input matrices.
- Existing helper-level tests remain the authority for swing clamps, unsupported
  meters, short phrases, zero entrainment, and high-tempo straightening.
- Scene metadata should remain string-keyed/string-valued so tracker diagnostics
  can be JSON serialized without special handling.
- The tracker scene should preserve groove identity, meter/subdivision policy,
  swing ratio, breath/polyrhythm metadata, lane-level timing offsets, and
  positive row lengths through compilation.
- No new dependencies, migrations, provider secrets, database columns, runtime
  state files, HTTP routes, or auth behavior are introduced.

## Acceptance Criteria

1. Existing groove-engine assertions remain green.
   VERIFY: `pytest tests/test_groove_engine.py -q`

2. The new depth gate confirms `tests/test_groove_engine.py` reaches depth >= 2
   and contains `GrooveEngineEndToEndTests`.
   VERIFY: `pytest tests/test_test_groove_engine_depth.py -q`

3. `GrooveEngineEndToEndTests` drives one meaningful public groove path through
   profile lookup, meter policy overlay, IOI adjustment, entrainment, metadata,
   JSON serialization, and tracker scene compilation.
   VERIFY: `pytest tests/test_groove_engine.py::GrooveEngineEndToEndTests -q`

4. Groove integration remains behavior-compatible with the syncopation and
   tracker consumers.
   VERIFY: `pytest tests/test_groove_engine.py tests/test_syncopation_features.py -q`

5. Startup identity hardening remains covered for CLI startup, standalone and
   federated identity persistence, daemon bootstrap-before-announcer ordering,
   and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing notes mention the frac-0082 groove-engine depth-2 work.
   VERIFY: `grep -n "frac-0082" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
