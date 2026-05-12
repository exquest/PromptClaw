# Task frac-0085 Specification: test_instrument_patches Depth 2

## Problem Statement

`tests/test_instrument_patches.py` already covers selection of instrument
patches by cadence/family and the per-patch voice normalization rules at the
helper level for `my-claw/tools/senseweave/instrument_patches.py`. The missing
depth-2 work is a named end-to-end test path that proves
`select_instrument_patch` and `normalize_patch_voice` produce meaningful
output together when used as the public surface of the patch runtime.

The affected production surface already implements the simple one-path patch
runtime:

- `select_instrument_patch`
- `normalize_patch_voice`
- `INSTRUMENT_PATCHES`
- `InstrumentPatch`

This task deepens the test surface without changing existing locked assertions
or production behavior unless the new red tests expose a concrete production
gap.

## Technical Approach

- Preserve existing assertions in `tests/test_instrument_patches.py`.
- Add a depth gate at `tests/test_test_instrument_patches_depth.py` that
  requires `tests/test_instrument_patches.py` to contain
  `TestInstrumentPatchesEndToEnd` and to classify at depth >= 2 through the
  repo-local `sdp.fractal.classify_depth`.
- Append `TestInstrumentPatchesEndToEnd` to
  `tests/test_instrument_patches.py`. The class will drive one deterministic
  public patch-runtime path through:
  - cadence/family-driven patch selection,
  - explicit `patch_name` override selection,
  - per-role voice normalization across melody, bass, color, and counter,
  - allowed-voice passthrough, remap, and fallback resolution,
  - JSON-safe diagnostics built from the resolved palette.
- Use only stdlib test support and existing `senseweave` imports.
- Treat the generated startup identity hardening checks as regression anchors.
  Existing CLI, first-boot, daemon-ordering, and narrative ASGI tests already
  cover `bootstrap_identity()` before `FirstBootAnnouncer` and identity
  persistence across standalone/federated boots, so this task re-runs those
  anchors rather than broadening patch-runtime code.

## Edge Cases

- This depth-2 pass intentionally exercises one deterministic happy path
  rather than expanding malformed-input matrices.
- Existing helper-level tests remain the authority for individual remap
  entries and per-cadence selection rules.
- The end-to-end normalized palette must remain JSON-safe (string keys and
  string values) so it can be serialized into tracker diagnostics without
  special handling.
- No new dependencies, migrations, provider secrets, database columns, runtime
  state files, HTTP routes, or auth behavior are introduced.

## Acceptance Criteria

1. Existing instrument-patches assertions remain green.
   VERIFY: `pytest tests/test_instrument_patches.py -q`

2. The new depth gate confirms `tests/test_instrument_patches.py` reaches
   depth >= 2 and contains `TestInstrumentPatchesEndToEnd`.
   VERIFY: `pytest tests/test_test_instrument_patches_depth.py -q`

3. `TestInstrumentPatchesEndToEnd` drives one meaningful public patch-runtime
   path through cadence/family selection, explicit-name override, per-role
   voice normalization, and JSON-safe palette serialization.
   VERIFY: `pytest tests/test_instrument_patches.py::TestInstrumentPatchesEndToEnd -q`

4. Startup identity hardening remains covered for CLI startup, standalone and
   federated identity persistence, daemon bootstrap-before-announcer ordering,
   and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing notes mention the frac-0085 instrument-patches depth-2 work.
   VERIFY: `grep -n "frac-0085" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
