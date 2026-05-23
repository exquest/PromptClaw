# Task T-045d: Mood-Space Unit Coverage

## Problem Statement

T-045a added the `mood_mode` schema, T-045b implemented the pure mood-space
resolver, and T-045c wired that resolver into scene playback. The remaining
coverage gap is explicit unit coverage for the full FX-bus routing matrix:
matched default, expressive mismatch, house-bound uniform routing, and the
documented fallback when house-bound mode has no active house context.

This task does not introduce a new routing mode. It hardens the existing
CC-004 behavior and prepares the CC-005 unit-test expectation that every voice
routes to the expected FX bus under every supported mood-space mode.

## Technical Approach

- Add focused unit tests in `tests/test_space_reverb_profiles.py` using
  `build_voice_s_new_args(...)` as the unit under test because it is the OSC
  argument surface that carries the final `fx_bus_id`.
- Cover all canonical voices for each mode:
  - matched default: omit `mood_mode` and require each voice to route to its
    own `VOICE_REVERB_PROFILES[voice].fx_bus_id`.
  - expressive mismatch: use `mood_mode="expressive"` and require the
    deterministic `EXPRESSIVE_SPACE_VOICE_BY_VOICE` table, with no self-match.
  - house-bound uniform: use `mood_mode="house-bound"` plus
    `active_house="house_garden"` and require every voice to route to the
    garden/table-tin space bus while preserving the sounding synth voice.
- Add a separate unit test for `mood_mode="house-bound"` with no
  `active_house`, pinning the existing fallback to `house_chamber`.
- Expose the default house-bound fallback in
  `summarize_voice_reverb_profiles()` so diagnostics can report the fallback
  contract alongside the expressive and house-bound mapping tables.
- Do not change SuperCollider sources, database schema, migrations, runtime
  state directories, HTTP routes, provider secrets, or dependencies.

## Edge Cases

- Matched mode must be the default when `mood_mode` is omitted.
- Expressive mode must never route a voice into its own matched bus.
- House-bound mode must be uniform across every supported voice when an active
  house is supplied.
- House-bound mode without `active_house` must use `house_chamber`, which maps
  to the breath/glass-bell-jar profile and bus.
- The sounding synth name must remain `sw_<voice>` even when the selected
  reverb space belongs to a different voice profile.
- Unknown-house behavior stays covered by existing T-045b/T-045c tests and is
  not changed here.
- Candidate startup hardening for `bootstrap_identity()` remains an existing
  startup subsystem concern; this task re-runs the identity anchors rather than
  broadening mood-space unit coverage into startup rewiring.

## Acceptance Criteria

1. Unit tests cover all canonical voices in matched default, expressive, and
   house-bound modes through the emitted OSC `fx_bus_id`.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_voice_routing_fx_bus_matrix_covers_all_mood_modes -q`

2. Unit tests explicitly verify house-bound mode with no active house uses the
   documented `house_chamber` fallback and routes every voice to the breath
   space bus without changing the sounding synth.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_house_bound_without_active_house_uses_documented_default_house_space -q`

3. Reverb-profile diagnostics expose the default house-bound fallback beside
   the existing expressive and house-bound routing tables.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_house_bound_without_active_house_uses_documented_default_house_space -q`

4. Existing resolver, faithful scene, tracker playback, and voice-routing
   anchors remain green.
   VERIFY: `pytest tests/test_space_reverb_profiles.py tests/test_midi_scene.py tests/test_music_tracker_runtime.py::TestBuildSceneEvents::test_resolves_mood_space_metadata_from_scene_context tests/test_senseweave_voice.py::TestFxBusRouting::test_note_on_uses_resolved_mood_space_without_changing_synth -q`

5. Startup identity hardening remains covered with standalone/federated
   persistence and bootstrap-before-announcer anchors.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_midi_intake_daemon.py::test_main_invokes_bootstrap_identity tests/test_midi_intake_daemon.py::test_identity_persistence_between_boots tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Task documentation and status mention T-045d, the mode matrix, fallback
   house, no new dependencies, and no database migration.
   VERIFY: `rg -n "T-045d|mode matrix|house_chamber|No new dependencies|No database" specs/t-045d-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

7. Required final validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
