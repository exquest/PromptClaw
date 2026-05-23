# Task T-003a: Affective State Bus Reader Helper

## Problem Statement

The CypherClaw v2 coupling slice has a shared `affective_state_bus` writer,
bus constants, slow decay, and the `CYPHERCLAW_V2_COUPLING` rollout flag. The
voice layer still lacks a small Python-side reader helper that reads the
current bus value before later subtasks apply the coupling multiplier to
modulator depths.

T-003a adds that reader helper in the voice module. It must default to a
coupling-off result of `0.0`, so existing playback remains unchanged until the
operator explicitly enables `CYPHERCLAW_V2_COUPLING`.

## Technical Approach

- Add a typed control-bus reader protocol to
  `my-claw/tools/senseweave/synthesis/senseweave_voice.py`.
- Add `read_affective_state_bus(reader, *, env=None) -> float` in the same
  module.
- Reuse `senseweave.affective_state_bus.coupling_enabled(...)` so the flag
  truth table stays aligned with the writer.
- Reuse the canonical `AFFECTIVE_STATE_BUS_INDEX`, min, and max constants from
  `senseweave.affective_state_bus`.
- When coupling is disabled or unset, return `0.0` without touching the reader.
- When coupling is enabled, call
  `reader.read_control_bus(AFFECTIVE_STATE_BUS_INDEX)` and clamp the result
  into `[0.0, 1.0]`.
- Keep this slice Python-only. Later T-003 subtasks can wire the value into
  per-voice modulator-depth math.

## Edge Cases

- Missing `CYPHERCLAW_V2_COUPLING` is OFF and returns `0.0`.
- Explicit falsey values such as `0` are OFF and return `0.0`.
- OFF mode must not read the bus, avoiding accidental OSC/network work and
  avoiding stale state effects.
- Enabled mode clamps negative bus values to `0.0` and values above `1.0` to
  `1.0`, matching the shared bus contract.
- Reader failures in enabled mode are not swallowed; a broken enabled coupling
  reader should be visible to callers rather than silently changing musical
  behavior.
- No database schema, migration, dependency, provider secret, startup flow, or
  runtime state directory change is required.
- The generated startup hardening bullets target the existing identity startup
  subsystem. This task does not modify startup paths; the existing identity
  regression anchors will be re-run as verification.

## Acceptance Criteria

1. The voice-module reader returns the current affective-state bus value when
   `CYPHERCLAW_V2_COUPLING` is enabled and reads the canonical bus index.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestAffectiveStateBusReader::test_reader_returns_bus_value_when_coupling_enabled -q`

2. The reader returns `0.0` and does not touch the bus reader when the coupling
   flag is unset or falsey.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestAffectiveStateBusReader::test_reader_returns_zero_without_touching_bus_when_flag_off -q`

3. The reader clamps enabled bus values into the documented `[0.0, 1.0]`
   range.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestAffectiveStateBusReader::test_reader_clamps_bus_values_when_coupling_enabled -q`

4. Existing affective-bus writer, flag, and decay behavior remain green.
   VERIFY: `pytest tests/test_affective_state_bus.py -q`

5. Startup identity hardening anchors still pass.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Required validation passes before final commit.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
