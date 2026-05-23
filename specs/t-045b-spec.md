# Task T-045b: Space-Selection Resolver

## Problem Statement

CC-004 requires scene-level mood-driven space behavior after T-045a added the
`mood_mode` schema field. The current render code still selects only the
matched per-voice space, so `expressive` and `house-bound` metadata do not
change the target FX bus or rendered space payload. T-045b implements the
resolver slice: given a sounding voice, mood mode, and active house patch, it
returns the reverb profile that should receive that voice.

## Technical Approach

- Add a typed, pure resolver in `cypherclaw.space_reverb` that returns a
  `VoiceReverbProfile` for `(voice, mood_mode, active_house)`.
- Preserve the existing matched behavior by default: each voice selects its
  own `VOICE_REVERB_PROFILES[voice]` entry.
- Add an explicit expressive mismatch table. The rule is deterministic and
  has no self-matches:
  - `pluck -> kotekan`
  - `breath -> pad`
  - `choir -> bowed`
  - `kotekan -> tabla_tin`
  - `pad -> pluck`
  - `bowed -> breath`
  - `tabla_tin -> choir`
- Add an active-house table for house-bound selection. The PRD names the
  behavior but does not provide this table, so this task makes the mapping
  explicit and logs it in `ESCALATIONS.md`:
  - `house_monastery -> choir` / `stone_cathedral`
  - `house_chamber -> breath` / `glass_bell_jar`
  - `house_garden -> tabla_tin` / `dusk_garden`
  - `house_procession -> kotekan` / `humid_forest_canopy`
  - `house_workshop -> pluck` / `small_wooden_room`
- Update `build_voice_s_new_args(...)` to keep the sounding synth voice
  unchanged while selecting `fx_bus_id` from the resolved space profile.
- Update faithful MIDI scene rendering to use the resolver for `render_space`
  and per-step `render_fx_bus_id`, with optional `active_house` settings.
- Preserve parser forgiveness for runtime inputs: unknown voices fall back to
  pluck; unknown mood modes fall back to matched; unknown houses fall back to
  `house_chamber`.

## Edge Cases

- Unknown or `sw_`-prefixed voice names normalize through the existing voice
  fallback behavior.
- Expressive mode must never return the same space profile as the normalized
  sounding voice.
- House-bound mode must return the same house space for every voice in a
  scene, including unknown voices after fallback.
- `active_house` aliases such as `garden` and `house_garden` normalize to the
  same house entry.
- The sounding synth in `/s_new` remains the requested normalized voice even
  when the selected FX bus belongs to another profile.
- No database schema, migration, dependency, provider secret, runtime state,
  HTTP route, or SuperCollider source change is required.
- Candidate startup hardening is out of scope for this resolver, but the
  existing identity-startup regression anchors must remain green.

## Acceptance Criteria

1. Matched resolver mode returns each voice's canonical space and bus.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_space_selection_resolver_matched_uses_voice_mood_mapping -q`

2. Expressive resolver mode returns deliberate mismatches with no self-matches.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_space_selection_resolver_expressive_uses_deliberate_mismatch_rule -q`

3. House-bound resolver mode forces every voice into the active house's mapped
   space, including supported house aliases.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_space_selection_resolver_house_bound_uses_active_house_space_for_all_voices -q`

4. OSC `/s_new` args keep the sounding synth voice while routing `fx_bus_id`
   through the resolved mood-space profile.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_voice_s_new_args_apply_mood_space_without_changing_sounding_voice -q`

5. Faithful MIDI scenes serialize `render_space` and metadata from the
   resolver for matched, expressive, and house-bound modes.
   VERIFY: `pytest tests/test_midi_scene.py::test_faithful_scene_render_space_follows_mood_mode_resolver -q`

6. Existing matched render and synthesis routing anchors remain green.
   VERIFY: `pytest tests/test_midi_scene.py tests/test_midi_faithful_render_contract.py tests/test_space_reverb_profiles.py -q`

7. Startup identity hardening anchors remain green even though this task does
   not change startup flow.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

8. Task documentation and status mention T-045b, the resolver mappings, no new
   dependencies, and no migration.
   VERIFY: `rg -n "T-045b|space-selection resolver|house_monastery|expressive|No new dependencies|No database" specs/t-045b-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

9. Required final validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
