# Task T-048b: Morph Curve Parameter Interpolation

## Problem Statement

T-047 added the `morph_voice` SynthDef and T-048a added a validation-only
composer API schema for source/target voice morph requests. The codebase still
does not have a deterministic composer-side interpolation helper for turning a
normalized phrase position into `morph_x` and numeric voice-parameter values.
Without that helper, later scheduling code would either duplicate curve math or
hand-roll inconsistent `linear`, `exponential`, and `sigmoid` shapes.

## Technical Approach

- Add a small typed `cypherclaw.instrument_morph` package.
- Add `MorphInterpolationCurve` with canonical values:
  - `linear`
  - `exponential`
  - `sigmoid`
- Add `morph_curve_position(position, curve)`:
  - validates `position` is finite and within `[0.0, 1.0]`;
  - normalizes string/enum curve input;
  - returns a normalized curve value in `[0.0, 1.0]`;
  - preserves exact endpoints for all curves.
- Use these curve laws:
  - `linear`: `position`
  - `exponential`: normalized exponential ease-in,
    `(exp(k * position) - 1) / (exp(k) - 1)` with a fixed standard-library
    strength chosen in code.
  - `sigmoid`: normalized logistic S-curve centered at `0.5`, with exact
    endpoint normalization.
- Add `interpolate_voice_parameters(source, target, position, curve)`:
  - common numeric keys interpolate from source to target using the curved
    position;
  - source-only keys retain the source value;
  - target-only keys retain the target value;
  - output order is deterministic by sorted key.
- Add `build_morph_parameter_frames(source, target, frame_count, curve)` for
  later scheduler/OSC use. It must include exact source and target endpoint
  frames and require at least two frames.
- Keep T-048a's `MorphCurveType` and `morph_curve_type` response fields as
  SuperCollider gain-law selectors (`linear` / `equal-power`). T-048b's
  `linear` / `exponential` / `sigmoid` curves are phrase-progression curves for
  composer-side `morph_x` and parameter interpolation.

## Edge Cases

- Non-finite or out-of-range positions raise `ValueError`.
- Unknown curve names raise `ValueError`.
- Non-numeric parameter values raise `TypeError`.
- Empty source/target parameter maps are allowed and return only keys provided
  by either side.
- Missing keys are not invented or defaulted to zero because different voices
  expose different parameter sets.
- Endpoints return exact source/target values for shared keys, avoiding floating
  point drift at phrase boundaries.
- No database schema changes are introduced, so no migration or FK index is
  required.
- No new dependencies, provider secrets, agent commands, runtime state
  directories, startup-flow changes, or SuperCollider source changes are
  required.
- Mandatory hardening note: the generated startup-identity candidate hardening
  feedback is unrelated to this composer-side interpolation slice. Existing
  startup identity tests remain the proper regression anchors.

## Acceptance Criteria

1. The three curve laws normalize positions deterministically, preserve exact
   endpoints, make exponential slower than linear at the midpoint, and make
   sigmoid symmetric around `0.5`.
   VERIFY: `pytest tests/test_instrument_morph_curves.py::test_morph_curve_position_shapes_are_deterministic -q`

2. Numeric source/target voice parameters interpolate with each curve and keep
   source/target endpoints exact.
   VERIFY: `pytest tests/test_instrument_morph_curves.py::test_interpolate_voice_parameters_uses_curve_values_and_exact_endpoints -q`

3. Parameters that exist on only one side are preserved without inventing zero
   defaults, and output keys are deterministic.
   VERIFY: `pytest tests/test_instrument_morph_curves.py::test_interpolate_voice_parameters_preserves_one_sided_parameters -q`

4. Frame generation returns an endpoint-inclusive morph trajectory suitable for
   later OSC scheduling.
   VERIFY: `pytest tests/test_instrument_morph_curves.py::test_build_morph_parameter_frames_returns_endpoint_inclusive_trajectory -q`

5. Invalid positions, curve names, frame counts, and non-numeric parameter
   values fail clearly.
   VERIFY: `pytest tests/test_instrument_morph_curves.py::test_morph_interpolation_rejects_invalid_inputs -q`

6. Existing T-048a composer API validation remains compatible with the new
   interpolation helpers.
   VERIFY: `pytest tests/test_composer_api.py -q`

7. Startup identity candidate-hardening anchors still pass without expanding
   this task into startup rewiring.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

8. Task documentation and status mention T-048b, morph curve interpolation, no
   migration, no new dependencies, and the startup-hardening scope decision.
   VERIFY: `rg -n "T-048b|morph curve interpolation|No new dependencies|No database|startup" specs/t-048b-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

9. Required final validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
