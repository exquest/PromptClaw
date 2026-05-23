# Task T-044c: Voice FX Bus Routing Unit Tests

## Problem Statement

T-044b wired `SenseweaveVoice.note_on(...)` to emit an `fx_bus_id` OSC
argument from `cypherclaw.space_reverb.VOICE_REVERB_PROFILES` when the selected
timbre maps to a profiled CypherClaw voice. The positive routing test proved a
profiled voice carries a bus id, but it did not explicitly guard against
cross-voice leakage: a lookup drift or stale timbre state could route a voice to
another voice's FX return bus while still emitting a valid-looking integer.

T-044c adds unit-level regression coverage that each voice emits only on its own
assigned FX bus and that mismatched bus ids from other voice profiles are
rejected by the test contract.

## Technical Approach

- Extend the existing `tests/test_senseweave_voice.py::TestFxBusRouting` unit
  surface because that class already tests `SenseweaveVoice.note_on(...)` at the
  OSC argument boundary.
- Use `TIMBRE_MAP` as the runtime timbre-to-synth source of truth and
  `VOICE_REVERB_PROFILES` as the expected voice-to-FX-bus source of truth.
- For every profiled timbre, assert the emitted `/s_new` args contain exactly one
  `fx_bus_id`, equal to the voice's own profile bus and absent from the set of
  all foreign profile buses.
- Exercise timbre switching with `set_timbre(...)` to prove the next emitted
  note recomputes the FX bus from the new synth profile and does not leak a
  stale bus id from the previous timbre.
- Keep this as a test-only subtask. The implementation needed to pass these
  assertions already landed in T-044b; no production change, dependency,
  migration, provider secret, runtime state directory, or startup-flow change is
  required.

## Edge Cases

- Timbres whose synths do not have a `VOICE_REVERB_PROFILES` entry remain
  covered by the existing negative test and must not emit `fx_bus_id`.
- Multiple timbres may map to the same profiled synth; each still has to emit
  that synth profile's bus and reject all foreign profile buses.
- `set_timbre(...)` must route from current timbre state at note-spawn time, not
  from any cached or previously emitted bus id.
- Unknown timbre names are outside this subtask because `set_timbre(...)`
  ignores them and `note_on(...)` already falls back through existing behavior.
- The generated startup hardening feedback targets identity bootstrapping, not
  this voice-routing test surface. The relevant startup identity anchors remain
  verification commands and are not reimplemented here.

## Acceptance Criteria

1. Profiled SenseWeave timbres emit exactly one `fx_bus_id` and that id equals
   the bus assigned to the synth's own `VoiceReverbProfile`.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestFxBusRouting::test_note_on_routes_each_voice_to_its_assigned_fx_bus_id -q`

2. A profiled voice's emitted `fx_bus_id` is rejected if it matches any other
   voice profile's FX bus.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestFxBusRouting::test_note_on_rejects_other_voices_fx_bus_ids -q`

3. Timbres without a `VoiceReverbProfile` do not emit `fx_bus_id`.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestFxBusRouting::test_note_on_skips_fx_bus_id_for_voices_without_a_profile -q`

4. `set_timbre(...)` recomputes routing for the new voice and does not leak the
   prior voice's bus id into the next `/s_new` args.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestFxBusRouting::test_set_timbre_reroutes_to_the_new_voices_fx_bus_id -q`

5. The full T-044/T-044c routing test surface remains green.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestFxBusRouting tests/test_space_reverb_profiles.py -q`

6. Startup identity hardening remains covered without broadening this test-only
   audio task into startup rewiring.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

7. Task documentation and status mention T-044c and the FX-bus mismatch
   regression contract.
   VERIFY: `rg -n "T-044c|mismatched bus|fx_bus_id|foreign voice buses" specs/t-044c-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

8. Required final validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`

## Current State Notes

The T-044c tests already landed in commit `07335db` before this spec file was
added. That commit records a mutation check: bumping the emitted bus by `+1` in
`SenseweaveVoice.note_on(...)` causes the new mismatch and stale-route tests to
fail.
