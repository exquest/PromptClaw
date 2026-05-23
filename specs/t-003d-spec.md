# Task T-003d: Affective Coupling Integration Test

## Problem Statement

T-003a added the flag-gated `affective_state_bus` reader, T-003b added the
coupling multiplier helper, and T-003c added render-time modulator-depth
scaling. The remaining gap is an integration contract that proves the voice
render path composes those pieces correctly: with `CYPHERCLAW_V2_COUPLING` on
and a known bus value, every voice timbre should emit depths scaled by the PRD
multiplier; with the flag off, the same path should preserve the nominal
baseline depths and avoid reading the bus.

## Technical Approach

- Add integration coverage to `tests/test_senseweave_voice.py` because the
  existing reader, multiplier, and render-time scaling coverage already lives
  there.
- Exercise all entries in `TIMBRE_MAP`, treating those timbres as the current
  Python-side "all voices" surface for `SenseweaveVoice`.
- Use the existing fake control-bus reader with a known bus value.
- Add a small typed `SenseweaveVoice.note_on_with_affective_coupling(...)`
  helper that:
  - reads the affective bus through `read_affective_state_bus(...)`;
  - converts that value with `coupling_multiplier_from_bus_value(...)`;
  - delegates to `note_on(...)` with the resulting multiplier.
- Keep existing `note_on(...)` behavior unchanged for callers that do not use
  the new integration helper.

## Edge Cases

- Coupling flag unset or falsey must preserve nominal modulator depths.
- Coupling flag off must not touch the bus reader.
- Known enabled bus values are clamped by the existing reader before the
  multiplier is computed.
- The integration path must preserve the synth selected by each timbre.
- No database schema, migration, dependency, provider secret, runtime state
  directory, HTTP route, or SuperCollider compilation change is required.
- The generated startup-hardening bullets target the existing identity startup
  subsystem. This task does not modify startup paths; the existing standalone
  and federated identity regression anchors remain mandatory verification.

## Acceptance Criteria

1. With `CYPHERCLAW_V2_COUPLING=1` and a known bus value, every
   `TIMBRE_MAP` timbre emits modulator depths scaled by
   `1.0 + DEFAULT_COUPLING_STRENGTH * bus_value`.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestAffectiveCouplingIntegration::test_flag_on_known_bus_value_scales_depths_across_all_timbres -q`

2. With `CYPHERCLAW_V2_COUPLING` off, every `TIMBRE_MAP` timbre emits baseline
   nominal modulator depths and the bus reader is not touched.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestAffectiveCouplingIntegration::test_flag_off_preserves_baseline_depths_across_all_timbres -q`

3. Existing T-003a/T-003b/T-003c reader, multiplier, and render-time scaling
   tests remain green.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestAffectiveStateBusReader tests/test_senseweave_voice.py::TestCouplingMultiplier tests/test_senseweave_voice.py::TestRenderTimeModulatorDepthScaling -q`

4. Existing affective-bus writer, flag, and decay behavior remain green.
   VERIFY: `pytest tests/test_affective_state_bus.py -q`

5. Startup identity hardening anchors still pass for standalone and federated
   persistence paths.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Required validation passes before final commit.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
