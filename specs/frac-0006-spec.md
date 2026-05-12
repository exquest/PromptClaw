# Task frac-0006 Specification: Character Registry Depth 2

## Problem Statement

`my-claw/tools/senseweave/character_registry.py` is the local source of truth
for organism character → voice metadata that the cast planner, duet composer,
and face-display sampler line all consume. The fractal scanner classifies it
at depth 1 (`4/6 trivial, 2 real`): only `_deepcopy_char` and `_copy_value`
contain real logic, and the public surface is limited to bare
`register` / `get` / `get_all` accessors. Callers that need per-mode gain,
merged voice params, or a registry-wide diagnostic view must reach into the
raw mapping shape themselves and re-derive defaults.

The task is to deepen the module to a simple depth-2 implementation: one
straightforward path that adds meaningful, pure helpers for projecting
voice metadata and summarizing the registry, while preserving the existing
`CharacterRegistry` API so `cast_planner` and the test suite keep working.

## Technical Approach

Extend `character_registry.py` in place with a small set of pure, typed
helpers operating on existing character/voice mappings:

- `voice_of(char)` — return the embedded `voice` mapping for a character,
  raising `ValueError` when the input is not a mapping or the voice dict is
  missing. Centralizes the `char["voice"]` projection that callers currently
  inline.
- `mode_gain_for(voice, mode, *, default=1.0)` — return the per-mode amplitude
  override for a voice, falling back to `default` when no override is set or
  the value cannot be coerced to `float`. Lets the cast planner and mix
  engine resolve gain without re-checking the override dict shape.
- `params_for(voice, overrides=None)` — return a fresh `dict[str, float]`
  merging the voice's default `params` with caller overrides. `None`-valued
  overrides are skipped so optional kwargs can pass through unchanged.
- `summarize_registry(registry)` — return `{character_count, character_ids,
  synth_counts, role_counts}` so operator diagnostics can render a stable
  snapshot of who is registered without exposing voice internals.
- `voices_by_role(registry)` — group registered character IDs by voice role,
  sorting each bucket so the output is deterministic for tests and logs.
- `find_voices_by_synth(registry, synth)` — return the sorted list of
  character IDs whose voice synth exactly matches `synth`.

The existing `CharacterRegistry` class, the `VOICE_SAMPLER_*` constants,
`SAMPLER_DEFAULT_PARAMS`, `SAMPLER_MODE_GAIN_OVERRIDES`, and the private
`_deepcopy_char` / `_copy_value` helpers keep their current behavior so
`tests/test_character_registry.py`, `cast_planner`, and `duet_composer`
continue to work without edits. No new dependencies, migrations, secrets, or
database columns are introduced.

## Edge Cases

- `voice_of` raises `ValueError` for non-mapping input and for mappings that
  lack a nested `voice` dict, so misuse is loud rather than silent.
- `mode_gain_for` returns `default` when the voice has no `mode_gain_overrides`
  mapping or when the requested mode is missing, and coerces stored values
  through `float()` so int overrides do not surprise downstream multipliers.
- `mode_gain_for` swallows `TypeError` / `ValueError` from non-numeric
  override values and falls back to `default` rather than raising, so a
  malformed registry entry cannot crash the audio path.
- `params_for` coerces every emitted value through `float()`, drops keys
  whose values cannot be coerced, and ignores `None` overrides so optional
  kwargs from `sampler_dispatch` callers pass through unchanged.
- `summarize_registry`, `voices_by_role`, and `find_voices_by_synth` ignore
  characters whose `voice` field is missing or not a mapping rather than
  raising, so partial registrations cannot break diagnostics.
- `voices_by_role` and `find_voices_by_synth` return deterministically
  sorted lists so logs and snapshot tests stay stable.
- Startup identity hardening remains a regression anchor. Existing tests
  cover `bootstrap_identity()` persistence and ordering before
  `FirstBootAnnouncer` for standalone and federated startup paths.

## Acceptance Criteria

1. `voice_of` returns the embedded voice mapping for a registered character
   and raises `ValueError` for malformed input.
   VERIFY: `pytest tests/test_character_registry_depth.py::test_voice_of_returns_voice_mapping tests/test_character_registry_depth.py::test_voice_of_rejects_malformed_input -q`

2. `mode_gain_for` returns the per-mode override when set and falls back to
   the default for unknown modes or malformed override tables.
   VERIFY: `pytest tests/test_character_registry_depth.py::test_mode_gain_for_returns_override tests/test_character_registry_depth.py::test_mode_gain_for_falls_back_to_default -q`

3. `params_for` merges voice defaults with caller overrides and skips
   `None`-valued overrides.
   VERIFY: `pytest tests/test_character_registry_depth.py::test_params_for_merges_defaults_with_overrides tests/test_character_registry_depth.py::test_params_for_skips_none_overrides -q`

4. `summarize_registry` reports character count, sorted character IDs, and
   stable synth/role histograms.
   VERIFY: `pytest tests/test_character_registry_depth.py::test_summarize_registry_reports_counts_and_histograms -q`

5. `voices_by_role` groups registered character IDs by role with sorted
   buckets, and `find_voices_by_synth` returns the sorted matching IDs.
   VERIFY: `pytest tests/test_character_registry_depth.py::test_voices_by_role_groups_sorted_ids tests/test_character_registry_depth.py::test_find_voices_by_synth_returns_sorted_matches -q`

6. Existing `tests/test_character_registry.py` semantics continue to pass
   without modification.
   VERIFY: `pytest tests/test_character_registry.py -q`

7. Fractal depth for `my-claw/tools/senseweave/character_registry.py`
   reaches at least depth 2.
   VERIFY: `python - <<'PY'
import sys
sys.path.insert(0, "/Users/anthony/Programming/sdp-cli/src")
from sdp.fractal import classify_depth
result = classify_depth("my-claw/tools/senseweave/character_registry.py")
print(result.depth, result.reason)
assert result.depth >= 2
PY`

8. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
