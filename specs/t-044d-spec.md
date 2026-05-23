# Task T-044d: Synthesis Suite and Smoke Render Routing Fix

## Problem Statement

T-044a through T-044c locked the voice-side `fx_bus_id` routing contract, but
the master bus still has to collect the same return buses at the end of the
synthesis graph. The focused synthesis suite passes today, yet a smoke render
trace exposes a regression: the seven CypherClaw v2 voices emit buses `16..22`
while `master_smooth.scd` still reads the older `18/20/22/24/26/28/30` map.
That means several voice FX sends are never collected by the master chain and
several stale buses are read instead.

## Technical Approach

- Keep `cypherclaw.space_reverb.VOICE_REVERB_PROFILES` as the source of truth
  for canonical voice order and bus ids.
- Add regression coverage that parses `master_smooth.scd` and asserts its FX
  return controls exactly match the profile table: `fx_bus_<voice>` for every
  canonical profile, no stale `gong` or `bell` controls, and matching
  `In.ar(fx_bus_<voice>, 2)` reads.
- Add a smoke-render style regression that builds one `/s_new` arg list per
  canonical voice via `build_voice_s_new_args(...)` and verifies every emitted
  `fx_bus_id` is collected by the master return map.
- Fix only the source-level master routing contract in
  `my-claw/tools/senseweave/synthesis/master_smooth.scd`. The compiled
  `.scsyndef` artifact still has to be regenerated on a SuperCollider host.
- Re-run the synthesis suite, the smoke regression, and startup identity
  hardening anchors.

## Edge Cases

- The master source must reject stale or future return controls that are not in
  `VOICE_REVERB_PROFILES`, because extra reads can mask missing buses.
- `tabla_tin` must be included even though it is not in the legacy
  `SenseweaveVoice.TIMBRE_MAP` convenience presets.
- Existing dry `out_bus` routing remains unchanged.
- The sampler bus remains outside the seven voice-space return map.
- Startup identity hardening is a regression anchor for this task, not a reason
  to change unrelated startup code unless a startup test fails.

## Acceptance Criteria

1. The current synthesis suite is runnable and green before/after the fix.
   VERIFY: `pytest tests/test_senseweave_voice.py tests/test_space_reverb_profiles.py tests/test_sw_sampler.py tests/test_master_bus.py -q`

2. `master_smooth.scd` declares exactly one FX return control per canonical
   `VOICE_REVERB_PROFILES` voice, with default bus ids equal to the profile
   table and no stale legacy voice controls.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_master_smooth_fx_returns_match_voice_reverb_profiles -q`

3. The smoke render trace proves every emitted voice `fx_bus_id` is collected by
   the master return map and that no unused master return bus remains.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_smoke_render_voice_fx_bus_ids_are_collected_by_master_smooth -q`

4. Existing T-044/T-044c voice routing assertions remain unchanged and green.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestFxBusRouting tests/test_space_reverb_profiles.py::test_each_voice_routes_only_to_its_assigned_fx_bus -q`

5. Startup identity hardening remains covered for CLI startup, first boot,
   midi-intake startup, daemon ordering before `FirstBootAnnouncer`,
   standalone/federated persistence, and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_midi_intake_daemon.py::test_main_invokes_bootstrap_identity tests/test_midi_intake_daemon.py::test_identity_persistence_between_boots tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Task documentation and status mention T-044d, the synthesis suite, smoke
   render, and the master FX-bus routing fix.
   VERIFY: `rg -n "T-044d|smoke render|synthesis suite|master.*FX|fx_bus" specs/t-044d-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

7. Required final validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
