# Task T-045a: Mood-Mode Scene Schema

## Problem Statement

CC-004 requires per-scene mood-driven space behavior with three modes:
`matched`, `expressive`, and `house-bound`. The current faithful scene payload
has a string `space_mode` that defaults to `matched`, but there is no typed
`mood_mode` scene-schema field for downstream resolver and playback tasks to
consume. The scene metadata validator also only checks tuning fields today, so
bad or missing mood-mode metadata can pass through silently.

T-045a is the schema/parser/validator slice only. T-045b/T-045c/T-045d own the
space-selection resolver, active-house lookup, playback wiring, and full
voice-by-mode routing assertions.

## Technical Approach

- Add a typed mood-mode enum to `cypherclaw.midi_scene` with canonical values:
  `matched`, `expressive`, and `house-bound`.
- Keep `matched` as the default for new scenes and for invalid parser input.
- Add a parser that accepts enum values plus common serialized aliases such as
  `house_bound` and `house bound`, normalizing them to canonical enum values.
- Add top-level and per-step `mood_mode` metadata to faithful scene payloads.
- Extend `validate_faithful_scene_metadata(...)` so serialized scene metadata
  requires `mood_mode` and rejects values outside the enum.
- Add the same default/normalization contract to `TrackerScene` metadata and
  `validate_scene(...)`, because runtime tracker scenes are the downstream
  schema consumed by later resolver/playback tasks.
- Preserve existing `space_mode=matched` behavior until the resolver task lands.

## Edge Cases

- Missing `mood_mode` in serialized metadata is invalid.
- Unsupported serialized `mood_mode` values are invalid.
- Parser input from runtime settings is forgiving: blank, unknown, or `None`
  normalizes to `matched`.
- `house-bound`, `house_bound`, and `house bound` normalize to the same enum
  value while serializing as `house-bound`.
- Empty faithful scenes still emit default `mood_mode=matched` metadata.
- No database schema, migration, dependency, provider secret, runtime state,
  HTTP route, or SuperCollider source change is required.
- Hardening check: existing synthdef routing must remain anchored by tests for
  `fx_bus_id` on voice synthdefs and `sw_sampler.scd`.

## Acceptance Criteria

1. Faithful scene payloads include `mood_mode=matched` by default at top level
   and per step, and the metadata validates after JSON round-trip.
   VERIFY: `pytest tests/test_midi_scene.py::test_scene_metadata_defaults_to_matched_mood_mode_and_validates -q`

2. The mood-mode parser exposes the three canonical enum values, accepts common
   aliases, and falls back to `matched` for invalid runtime input.
   VERIFY: `pytest tests/test_midi_scene.py::test_mood_mode_parser_accepts_enum_values_aliases_and_fallback -q`

3. Explicit `expressive` and `house-bound` mood modes serialize as canonical
   scene metadata and survive JSON round-trip validation.
   VERIFY: `pytest tests/test_midi_scene.py::test_scene_metadata_round_trips_explicit_mood_modes -q`

4. Scene metadata validation rejects missing or unsupported `mood_mode` values
   while preserving existing tuning-curve validation.
   VERIFY: `pytest tests/test_midi_scene.py::test_validate_faithful_scene_metadata_rejects_missing_and_bad_mood_mode -q`

5. Tracker scene construction defaults `mood_mode` to `matched`, normalizes
   explicit aliases, and `validate_scene(...)` rejects unsupported values.
   VERIFY: `pytest tests/test_music_tracker.py::TestBuildSceneFromScore::test_scene_metadata_defaults_to_matched_mood_mode tests/test_music_tracker.py::TestBuildSceneFromScore::test_scene_metadata_normalizes_explicit_mood_mode tests/test_music_tracker.py::TestValidateScene::test_reports_invalid_mood_mode_metadata -q`

6. Existing faithful MIDI render, intake, and synthesis routing anchors remain
   green, including the recurring `fx_bus_id` and `sw_sampler.scd` checks.
   VERIFY: `pytest tests/test_midi_scene.py tests/test_midi_faithful_render_contract.py tests/test_space_reverb_profiles.py::test_voice_synthdefs_declare_fx_bus_id_routing_contract tests/test_space_reverb_profiles.py::test_master_smooth_fx_returns_match_voice_reverb_profiles tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_send_writes_to_fx_bus tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_bus_default_is_sampler_bus -q`

7. Task documentation and status mention T-045a, the mood-mode enum, the
   `matched` default, and the schema-only scope.
   VERIFY: `rg -n "T-045a|mood-mode|mood_mode|matched default|schema-only" specs/t-045a-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

8. Required final validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
