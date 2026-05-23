# Task T-043: Per-Voice Reverb Space Tuning

## Problem Statement

CypherClaw v2 defines seven matched default spaces in
`sdp/cypherclaw-v2-design-statement-2026-05-22.md` §4, but the current audio
surface only carries compact render-space metadata and a generic sampler FX
SynthDef. T-043 needs explicit, reviewable algorithmic reverb parameters for
each voice's dedicated FX bus so later routing tasks can instantiate the
correct per-voice space without rediscovering CypherClaw's aesthetic intent.

## Technical Approach

- Add a typed `cypherclaw.space_reverb` module that declares one frozen profile
  per §4 voice: `pluck`, `breath`, `choir`, `kotekan`, `pad`, `bowed`, and
  `tabla_tin`.
- Keep the bus ids aligned with the existing faithful-render contract:
  `pluck=16`, `breath=17`, `choir=18`, `kotekan=19`, `pad=20`, `bowed=21`,
  `tabla_tin=22`.
- Encode algorithmic Path A parameters only: wet mix, room size, damping,
  predelay, decay, early-reflection level, and flutter/echo feedback. Do not
  add convolution IRs, new dependencies, or provider/cost-bearing behavior.
- Add one `.scd` documentation/source file per space under
  `my-claw/tools/senseweave/synthesis/spaces/`. Each file must document:
  voice, space id, FX bus id, all profile parameters, and a one-line rationale
  citing CypherClaw's §4 space description.
- Wire `src/cypherclaw/midi_scene.py` to derive `VOICE_SPACES` from the shared
  profile module so faithful MIDI render metadata and the documented per-space
  parameters cannot drift.
- Keep runtime routing out of scope; T-044 owns sending each voice into its
  matching FX bus. This task produces the tuned profiles and reviewable space
  sources those routing tasks consume.

## Edge Cases

- Unknown voices still fall back to `pluck` / `small_wooden_room`.
- `sw_`-prefixed voices normalize before space lookup.
- Each profile must use a unique FX bus id and a unique space id.
- Parameter values must remain in stable algorithmic bounds:
  `mix`, `room`, `damp`, `early_reflection_level`, and `flutter_feedback` in
  `[0.0, 1.0]`; `predelay_ms` in `[0.0, 80.0]`; `decay_s` in `[0.2, 8.0]`.
- Space files must be ASCII Markdown/SuperCollider source comments plus simple
  SynthDef stubs; no binary IR assets are introduced.
- The generated startup hardening bullets target the existing identity startup
  subsystem. This audio-profile task does not change startup flow; existing
  standalone/federated identity tests remain mandatory regression anchors.

## Acceptance Criteria

1. All seven CypherClaw §4 voices expose typed reverb profiles with unique
   space ids, unique FX bus ids, bounded parameters, and JSON-safe summaries.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_profiles_cover_all_cypherclaw_space_voices_with_unique_buses -q`
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_profile_parameters_are_bounded_and_json_safe -q`

2. Each reverb profile is documented in `spaces/` with a one-line rationale
   citing CypherClaw's space description.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_each_profile_has_space_source_file_with_rationale_and_parameters -q`

3. Faithful MIDI render metadata uses the shared reverb profiles for
   `render_space.reverb_profile` and preserves existing voice, synth, space id,
   and FX bus behavior.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_faithful_render_space_metadata_uses_shared_reverb_profiles -q`
   VERIFY: `pytest tests/test_midi_scene.py tests/test_midi_faithful_render_contract.py -q`

4. The space source directory contains exactly one algorithmic `.scd` space
   file per profile and no convolution IR/binary assets.
   VERIFY: `find my-claw/tools/senseweave/synthesis/spaces -maxdepth 1 -type f -print | sort`
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_spaces_directory_contains_only_expected_algorithmic_sources -q`

5. Product-facing progress, changelog, and escalations describe the per-voice
   reverb tuning without claiming mood-driven routing or convolution IR support.
   VERIFY: `rg -n "T-043|per-voice reverb|space reverb|CypherClaw.*space" CHANGELOG.md progress.md ESCALATIONS.md specs/t-043-spec.md`

6. Startup hardening anchors remain green, and no new dependencies, migrations,
   provider secrets, database columns, or runtime state directories are added.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`
   VERIFY: `git diff -- pyproject.toml promptclaw/coherence/migrations`

7. Required final validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`

## Assumptions

- The in-scope "spaces/" directory is the PRD-specified
  `my-claw/tools/senseweave/synthesis/spaces/` directory.
- T-043 tunes and documents algorithmic reverb profiles; T-044/T-045 own
  live routing/hot reload and T-046 owns mood-driven selection.
- The existing faithful render bus ids (`16..22`) are the source of truth for
  this task because they already match the seven §4 design voices.
