# Task frac-0117 Specification: test_syncopation_features Depth 2

## Problem Statement

`tests/test_syncopation_features.py` currently verifies the syncopation
and polyrhythmic-cross lane phasing surface introduced across
`my-claw/tools/senseweave/groove_engine.py` and
`my-claw/tools/senseweave/music_tracker.py` at focused helper depth: the
`GROOVE_TYPES` vocabulary additions (`syncopated`, `polyrhythmic_cross`),
the new `GrooveProfile.syncopation_intensity` and
`GrooveProfile.lane_phase_offsets` fields, the registered
`_GROOVE_PROFILES["syncopated"]` and `_GROOVE_PROFILES["polyrhythmic_cross"]`
profiles (with calm profiles confirmed at intensity zero), the
`syncopate_phrase(...)` rest-insertion / role-scaling / no-op-below-threshold
behavior, the `_parse_lane_phase_offsets(...)` CSV / tuple / list / clamp /
malformed parser, and the `_quantize_phrase_to_lane(... phase_offset_rows=...)`
melody shift / bass-anchor exemption plus the `DEFAULT_LANE_PHASE_OFFSETS`
sanity tuple.

Missing depth-2 coverage is a single realistic end-to-end test path that
proves the public syncopation + polyrhythmic-cross surface produces
meaningful output across the full lifecycle:

1. the `syncopated` and `polyrhythmic_cross` groove vocabulary entries
   resolve to registered `GrooveProfile` records with non-zero
   `syncopation_intensity` and non-empty `lane_phase_offsets` tuples,
2. `_parse_lane_phase_offsets(...)` accepts a CSV scene-metadata string
   and converts it to a tuple, agreeing with a directly supplied tuple,
3. `syncopate_phrase(...)` with `intensity=1.0` deterministically inserts
   leading rests into a melody phrase while preserving total duration,
   stamps `metadata["syncopated"] == "true"`, and at `intensity=0.6`
   produces fewer rests for a `bass` phrase than for a `melody` phrase
   under the same RNG seed,
4. `_quantize_phrase_to_lane(...)` honors the per-lane `phase_offset_rows`
   for a `melody` phrase (first step row equal to the requested offset)
   while exempting a `bass` phrase (first step row stays on row 0) when
   the same offset is requested,
5. a stable operator-style diagnostic captures the resolved groove
   profiles, the parsed CSV / direct lane offsets, the syncopated melody /
   bass durations and rest counts, the bass-anchor and offset-shifted
   tracker rows, and the `DEFAULT_LANE_PHASE_OFFSETS` tuple in JSON-safe
   form and round-trips through `json.dumps(..., sort_keys=True)` /
   `json.loads(...)`.

The production surface already implements this one-path behavior. This
task therefore deepens the test surface unless the red tests expose a
concrete source gap.

The generated startup identity hardening bullets target the existing
identity startup subsystem. Current CLI, first-boot, daemon-ordering, and
narrative ASGI tests already cover `bootstrap_identity()` before
`FirstBootAnnouncer` plus standalone/federated identity persistence. This
task keeps those tests as mandatory regression anchors rather than
changing unrelated startup code.

The active ADP process is the task prompt's Explore -> Specify -> Test ->
Implement -> Verify -> Document workflow.

## Technical Approach

- Add `tests/test_test_syncopation_features_depth.py` using the recent
  depth-gate pattern. The gate requires:
  - `SyncopationFeaturesEndToEndTests` exists in
    `tests/test_syncopation_features.py`;
  - the named method
    `test_syncopation_features_groove_lifecycle_round_trips_json_diagnostic`
    exists;
  - `classify_depth("tests/test_syncopation_features.py").depth >= 2`;
  - the test module declares a machine-readable depth-2 marker either in
    the module docstring (`depth: 2`) or as a top-level `DEPTH = 2`
    constant.
- Confirm the red phase by running the new depth gate before the
  end-to-end class and marker exist.
- Append `SyncopationFeaturesEndToEndTests` to
  `tests/test_syncopation_features.py` without modifying existing locked
  assertions, and add a `depth: 2` marker to the module docstring. The
  class drives one deterministic path:
  - resolve the `syncopated` and `polyrhythmic_cross` profiles from
    `_GROOVE_PROFILES` and capture their `syncopation_intensity` and
    `lane_phase_offsets`;
  - parse `"0,1,2,3,1"` via `_parse_lane_phase_offsets(...)` and confirm
    it matches the directly supplied `(0, 1, 2, 3, 1)` tuple;
  - run `syncopate_phrase(...)` on a melody phrase at `intensity=1.0`
    with a deterministic seed, asserting rest insertion, total-duration
    preservation, and the `metadata["syncopated"] == "true"` stamp;
  - run `syncopate_phrase(...)` on bass and melody phrases at
    `intensity=0.6` with the same seed and confirm the melody rest count
    is at least the bass rest count (role scaling);
  - quantize the melody and bass phrases via `_quantize_phrase_to_lane(...)`
    with a non-zero `phase_offset_rows` and confirm the melody first step
    row equals the offset while the bass first step row is anchored at 0;
  - build a primitive diagnostic of the profile values, parsed offsets,
    rest counts, durations, first-step rows, and
    `DEFAULT_LANE_PHASE_OFFSETS` and verify
    `json.loads(json.dumps(..., sort_keys=True))` round-trips it.
- Preserve production behavior unless the red tests reveal a runtime gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- This is intentionally one simple happy path for depth-2 coverage.
  Existing focused tests remain responsible for the full malformed CSV
  matrix, negative-value clamping, empty-input handling, short-note
  no-split behavior, calm-profile zero defaults, and the
  `DEFAULT_LANE_PHASE_OFFSETS` length / bass-zero invariants.
- The deterministic RNG seed keeps `syncopate_phrase(...)` output stable
  without depending on global random state.
- The diagnostic payload only stores strings, booleans, ints, floats,
  lists, and nested dicts, so JSON serialization stays deterministic and
  hermetic.
- No database schema changes are introduced, so no migration or index
  work is required.
- Startup identity hardening remains a regression anchor and is not
  widened inside the syncopation tests.

## Acceptance Criteria

1. Existing syncopation assertions remain green.
   VERIFY: `pytest tests/test_syncopation_features.py -q`

2. The depth gate confirms `tests/test_syncopation_features.py` reaches
   depth >= 2 and contains the named end-to-end class/method plus the
   machine-readable depth-2 marker.
   VERIFY: `pytest tests/test_test_syncopation_features_depth.py -q`

3. `SyncopationFeaturesEndToEndTests` drives the syncopated /
   polyrhythmic_cross profile lookup, CSV / tuple offset parsing,
   `syncopate_phrase(...)` rest insertion + role scaling, lane phase
   offset quantize + bass exemption, and JSON-safe diagnostic round-trip.
   VERIFY: `pytest tests/test_syncopation_features.py::SyncopationFeaturesEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0117 syncopation test
   deepening with no new dependencies or migrations.
   VERIFY: `grep -n "frac-0117" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
