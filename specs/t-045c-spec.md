# Task T-045c: Scene Playback Space Resolver Wiring

## Problem Statement

T-045b added the pure mood-space resolver and wired faithful MIDI scene payloads
plus the standalone `build_voice_s_new_args(...)` helper. The live scene
render/playback path still does not consistently carry that resolved space to
each scheduled voice event: tracker scene events do not expose the resolved
space metadata, and live voice playback still derives `fx_bus_id` from the
sounding voice alone.

T-045c wires the resolver through the scene event and playback path so the
sounding synth voice stays unchanged while its FX bus follows the scene's
resolved `mood_mode` and house context.

## Technical Approach

- Add shared helpers in `cypherclaw.space_reverb` for scene metadata lookup:
  `mood_mode` falls back to `space_mode` and then `matched`; `active_house`
  falls back to `patch_name` and then the resolver's default house.
- Use those helpers in tracker event construction so every
  `ScheduledTrackerEvent.metadata` carries `mood_mode`, `active_house`,
  `render_space_voice`, `render_space_id`, and `render_fx_bus_id`.
- Extend `SenseweaveVoice.note_on(...)` and
  `note_on_with_affective_coupling(...)` with optional `mood_mode` and
  `active_house` parameters. Profiled timbres keep their selected synth but
  route `fx_bus_id` through the resolver.
- Wire tracker playback in `duet_composer.py` so `_play_tracker_event(...)`
  passes `event.scene_metadata["mood_mode"]` and the scene house context into
  `play_voice(...)`.
- Extend `play_voice(...)` so profiled runtime-safe voices append one
  resolver-selected `fx_bus_id` to `/s_new` args while preserving all existing
  per-note shaping, EMSD performance controls, and sounding synth selection.
- Keep sampler hardening intact: `sw_sampler.scd` already exposes
  `fx_bus_id` and writes its FX send to `fx_bus_id`, so this task should not
  rename sampler controls or add a new SuperCollider dependency.

## Edge Cases

- `house-bound` scenes with `active_house` use that explicit house.
- `house-bound` tracker scenes without `active_house` use `patch_name` as the
  house context because instrument patches are named `house_*`.
- Unknown or missing house context falls back to the existing `house_chamber`
  resolver default.
- Unknown mood modes still normalize to `matched`.
- Unknown voices still follow the existing runtime voice fallback behavior;
  profiled runtime aliases such as `tabla_ge -> tabla_tin` route through the
  resolved space for the alias target.
- Non-profiled synths keep their existing OSC args and do not receive a bogus
  `fx_bus_id`.
- No database schema, migration, dependency, provider secret, runtime state
  directory, HTTP route, or SuperCollider source change is required.
- Candidate hardening: focused verification must include the existing
  `fx_bus_id` SynthDef and `sw_sampler.scd` controls so recurring
  `fx_bus_id`/`fx_bus` regressions stay covered.

## Acceptance Criteria

1. Scene metadata helpers resolve mood and house context from tracker metadata,
   including `patch_name` fallback for house-bound mode.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_scene_space_context_uses_active_house_then_patch_name -q`

2. Tracker scene events carry resolver-derived space metadata without changing
   the scheduled sounding voice.
   VERIFY: `pytest tests/test_music_tracker_runtime.py::TestBuildSceneEvents::test_resolves_mood_space_metadata_from_scene_context -q`

3. `SenseweaveVoice.note_on(...)` accepts mood-space context and routes
   profiled timbres to the resolved FX bus while preserving the sounding synth.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestFxBusRouting::test_note_on_uses_resolved_mood_space_without_changing_synth -q`

4. The live tracker playback closure passes scene mood/house context to
   `play_voice(...)`, and `play_voice(...)` appends the resolved `fx_bus_id`
   for profiled runtime-safe voices.
   VERIFY: `pytest tests/test_duet_composer_space_routing.py -q`

5. Existing resolver, faithful MIDI render, tracker runtime, voice routing,
   and sampler hardening anchors remain green.
   VERIFY: `pytest tests/test_space_reverb_profiles.py tests/test_midi_scene.py tests/test_midi_faithful_render_contract.py tests/test_music_tracker_runtime.py tests/test_senseweave_voice.py::TestFxBusRouting tests/test_sw_sampler.py::TestRoutingAndFxSend -q`

6. Startup identity hardening remains covered even though this task does not
   change startup flow.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

7. Task documentation and status mention T-045c, scene playback wiring,
   `patch_name` house fallback, no new dependencies, and no migration.
   VERIFY: `rg -n "T-045c|scene playback|patch_name|No new dependencies|No database" specs/t-045c-spec.md CHANGELOG.md progress.md ESCALATIONS.md docs/architecture.md docs/handoff-protocol.md docs/command-reference.md docs/startup-wizard.md`

8. Required final validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
