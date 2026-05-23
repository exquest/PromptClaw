# Task T-003c: Render-Time Coupling Depth Scaling

## Problem Statement

T-003a added a flag-gated reader for the shared `affective_state_bus`, and
T-003b added the pure coupling multiplier helper:

```text
1.0 + coupling_strength * affective_state
```

The voice render path still does not apply that multiplier to modulator depths
when a note is emitted. T-003c wires the multiplier into the
`SenseweaveVoice.note_on(...)` render-time argument path so callers that supply
nominal modulator depths get effective depths in the emitted OSC args.

Per CypherClaw v2 PRD feature 8 / CC-072:

```text
effective_depth = nominal_depth * coupling_multiplier
```

This task covers the Python render argument path shared by every
`SenseweaveVoice` timbre. SuperCollider synthdef internals, audible A/B
coupling, and composer-side expression generation remain later tasks.

## Technical Approach

- Add a typed helper in
  `my-claw/tools/senseweave/synthesis/senseweave_voice.py` that accepts a
  mapping of nominal modulator depth args and a render-time multiplier, and
  returns a new dict of scaled depths.
- Keep the helper side-effect-free and preserve the incoming parameter names so
  future synthdefs can accept the same depth controls.
- Extend `SenseweaveVoice.note_on(...)` with keyword-only optional
  `modulator_depths` and `coupling_multiplier` arguments.
- When `modulator_depths` is supplied, scale every depth by
  `coupling_multiplier` immediately before emitting `/s_new`, then append the
  resulting arg pairs to the OSC argument list.
- Leave existing calls unchanged: when no modulator depths are supplied, the
  emitted OSC argument list is identical to the existing path.
- Test the shared render path across every timbre in `TIMBRE_MAP` so each voice
  path proves `depth_out = depth_in * multiplier`.

## Edge Cases

- An empty depth mapping returns an empty mapping and appends no args.
- A multiplier of `1.0` preserves nominal depths.
- A multiplier of `0.0` produces zero effective depths.
- Negative nominal depths are scaled arithmetically rather than clamped; T-003c
  only applies the multiplier, while upstream gesture validation owns depth
  range policy.
- The helper returns a fresh dict and must not mutate caller-owned mappings.
- Coupling-off behavior remains unchanged because existing callers do not pass
  modulator depths, and T-003a still returns `0.0` until the rollout flag is on.
- The generated startup hardening bullets target the existing identity startup
  subsystem. This task does not modify startup paths; existing identity
  regression anchors remain mandatory verification.
- No database schema, migration, dependency, provider secret, runtime state
  directory, HTTP route, OSC read, or SuperCollider compilation change is
  required.

## Acceptance Criteria

1. The pure render helper scales every supplied modulator depth by the supplied
   multiplier and does not mutate the input mapping.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestRenderTimeModulatorDepthScaling::test_scales_depth_mapping_without_mutating_input -q`

2. The live `SenseweaveVoice.note_on(...)` OSC render path appends scaled
   modulator-depth args for every timbre in `TIMBRE_MAP`, proving
   `depth_out = depth_in * multiplier` across voices.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestRenderTimeModulatorDepthScaling::test_note_on_applies_multiplier_to_depth_args_across_timbres -q`

3. Existing T-003a/T-003b reader and multiplier tests remain green.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestAffectiveStateBusReader tests/test_senseweave_voice.py::TestCouplingMultiplier -q`

4. Existing affective-bus writer, flag, and decay behavior remain green.
   VERIFY: `pytest tests/test_affective_state_bus.py -q`

5. Startup identity hardening anchors still pass for standalone and federated
   persistence paths.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Required validation passes before final commit.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
