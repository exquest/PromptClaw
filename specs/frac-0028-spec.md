# Task frac-0028 Specification: SynthDef Registry Depth 2

## Problem Statement

`my-claw/tools/senseweave/synthdef_registry.py` owns the verified sound
palette and SynthDef registry that downstream callers (cast planning,
duet composition, voice-alias resolution, sound-palette consistency
tests) treat as the single source of truth for every voice's synthesis
method, timbral tags, safe-role mapping, register range, macro controls,
spectral profile, and quarantine status. Existing exports
(`REQUIRED_METHODS`, `SYNTHDEF_REGISTRY`, `RegisterRange`, `MacroControl`,
`SpectralProfile`, `SynthDefEntry`, `get_entry`, `resolve_voice`,
`entries_by_method`, `live_voices`, `quarantined_voices`,
`voices_for_role`, `covered_methods`) are part of the deployed
contract.

The module currently classifies at fractal depth 1
(`7/9 trivial, 2 real`) because the public surface is dominated by
single-statement comprehension lookups (`entries_by_method`,
`live_voices`, `quarantined_voices`, `voices_for_role`,
`covered_methods`, `get_entry`) that outnumber the real
`resolve_voice` and `RegisterRange.octave_span` paths. This task
deepens the module to a simple depth-2 implementation by adding one
typed report path that turns the in-memory registry into stable
operator-readable shape diagnostics without changing any existing
field, lookup function, or quarantine resolution behavior.

The auto-generated hardening checks for `/healthz` + `/readyz`
endpoints and bearer-token auth headers target the `narrative/` HTTP
service, not this pure data-model module. The current narrative
service already exposes `/healthz` and `/readyz` with a bearer token
header and is covered by `tests/test_smoke_narrative_script.py`; this
task keeps that smoke test as a mandatory regression anchor.

## Technical Approach

Extend `senseweave.synthdef_registry` in place with stdlib-only, typed
helpers. No new dependencies, migrations, runtime state files, provider
secrets, database columns, or agent command strings are introduced.

- Preserve `REQUIRED_METHODS`, `SYNTHDEF_REGISTRY`, `_ENTRIES`,
  `RegisterRange`, `MacroControl`, `SpectralProfile`, `SynthDefEntry`,
  `get_entry`, `resolve_voice`, `entries_by_method`, `live_voices`,
  `quarantined_voices`, `voices_for_role`, and `covered_methods`
  exactly as they are today, so `tests/test_synthdef_registry.py` and
  every downstream caller remain unchanged.
- Add `register_band(min_hz)` returning a stable named band:
  - `min_hz < 130.8` -> `"low"` (below C3)
  - `130.8 <= min_hz < 523.3` -> `"mid"` (C3 through below C5)
  - `min_hz >= 523.3` -> `"high"` (C5 and above)
- Add `fundamental_band(weight)` returning a stable named band:
  - `weight < 0.4` -> `"weak"`
  - `0.4 <= weight <= 0.7` -> `"balanced"`
  - `weight > 0.7` -> `"strong"`
- Add `noise_band(noise_floor)` returning a stable named band:
  - `noise_floor < 0.1` -> `"clean"`
  - `0.1 <= noise_floor <= 0.3` -> `"textured"`
  - `noise_floor > 0.3` -> `"noisy"`
- Add `rolloff_band(harmonic_rolloff_db)` returning a stable named
  band, where the rolloff value is in dB per octave (negative or zero):
  - `harmonic_rolloff_db > -3.0` -> `"gentle"`
  - `-6.0 <= harmonic_rolloff_db <= -3.0` -> `"moderate"`
  - `harmonic_rolloff_db < -6.0` -> `"steep"`
- Add frozen dataclass `VoiceShape` containing one voice's resolved
  diagnostic view: `voice_name`, `synthdef_name`, `synthesis_method`,
  `timbral_tags`, `safe_roles`, `register_min_hz`, `register_max_hz`,
  `octave_span` (rounded to 4 decimals), `register_band` (named band
  for `register_min_hz`), `bandwidth`, `fundamental_weight`,
  `fundamental_band`, `noise_floor`, `noise_band`,
  `harmonic_rolloff_db`, `rolloff_band`, `macro_control_count`,
  `macro_control_names` (the macro control names in declaration
  order), `quarantined`, `quarantine_reason`, `safe_substitute`, and
  `runtime_voice_name` (the voice name returned by
  `resolve_voice(voice_name).voice_name`).
- Add frozen dataclass `SynthDefRegistryReport` containing the
  registry-level view: `total_count`, `live_count`,
  `quarantined_count`, `methods` (ordered tuple of canonical methods
  in `REQUIRED_METHODS` order: `subtractive`, `additive`, `fm`,
  `wavetable`, `physical_model`, `granular`),
  `method_counts` (ordered mapping of every canonical method to its
  total entry count, including zeros), `live_method_counts` (ordered
  mapping of every canonical method to its non-quarantined entry
  count, including zeros), `roles` (ordered tuple of roles
  surfaced by any live voice, in first-seen entry order),
  `role_live_voices` (ordered mapping of role to ordered tuple of
  live `voice_name` values for that role), `register_band_counts`
  (ordered mapping of `low`, `mid`, `high` to entry counts, including
  zeros), `lowest_register_voice` (the voice name with the smallest
  `register.min_hz`, ties broken by entry order),
  `highest_register_voice` (the voice name with the largest
  `register.max_hz`, ties broken by entry order),
  `quarantine_reasons` (ordered tuple of distinct quarantine reasons
  in entry order), `runtime_voice_map` (ordered mapping of every
  quarantined voice name to the resolved live `runtime_voice_name`,
  in entry order), `missing_required_methods` (sorted tuple of
  canonical methods that have zero entries), and `voices` (ordered
  tuple of `VoiceShape` entries, one per `_ENTRIES`).
- Add `build_voice_shape(entry)`:
  - Compute the band classifications through the new helpers.
  - Round `octave_span` to 4 decimals.
  - Resolve `runtime_voice_name` via `resolve_voice(entry.voice_name)`.
  - Capture `macro_control_names` from `entry.macro_controls` in
    declaration order.
- Add `build_synthdef_registry_report()`:
  - Iterate `_ENTRIES` in declaration order, building one
    `VoiceShape` per entry.
  - Aggregate counts, ordered roles, role-to-voice map (live voices
    only), register-band counts, lowest/highest register voices,
    distinct quarantine reasons, runtime voice map, and missing
    required methods.
- Add `summarize_synthdef_registry_report(report)`:
  - Return a JSON-safe dictionary mirroring the report fields, with
    a `voices` list whose entries mirror each `VoiceShape` field. All
    values must be primitives, lists, or dictionaries of primitives.
- Add a module-level docstring sentence noting the new diagnostic
  surface so the polished depth criterion (docstring coverage) keeps
  passing for all public functions; every new public callable must
  carry a one-line docstring.

## Edge Cases

- Band cutpoints follow the inclusive boundaries documented above.
- `register_band` keys off `min_hz` only, so a voice whose minimum is
  below C3 reports `"low"` even if its maximum extends well into the
  high register. This is intentional for the depth-2 surface.
- `octave_span` is rounded to 4 decimals to keep the JSON summary
  stable under floating-point arithmetic.
- `build_synthdef_registry_report` raises no errors — the registry
  is always populated; an empty registry would produce zero counts
  and empty tuples.
- `lowest_register_voice` and `highest_register_voice` break ties by
  declaration order in `_ENTRIES`.
- `methods` always lists the six canonical methods in
  `REQUIRED_METHODS` order. `missing_required_methods` reports any
  canonical method whose entry count is zero; today the registry
  covers all six, so this tuple is empty.
- `runtime_voice_map` contains exactly the quarantined voices, in
  declaration order, mapped to their resolved live voice via
  `resolve_voice`.
- `roles` and `role_live_voices` exclude quarantined voices, matching
  the behavior of `voices_for_role`.
- The hardening checks for narrative HTTP endpoints (`/healthz`,
  `/readyz`, bearer-token auth header) target `narrative/` HTTP
  services, not the SynthDef registry data model. The current
  narrative service already exposes those endpoints with a bearer
  token header and is covered by `tests/test_smoke_narrative_script.py`;
  this task keeps that smoke test as a mandatory regression anchor.

## Acceptance Criteria

1. Existing SynthDef registry behavior remains unchanged.
   VERIFY: `pytest tests/test_synthdef_registry.py -q`

2. Band helpers map register, fundamental, noise, and rolloff values
   to the documented named bands at their cutpoints.
   VERIFY: `pytest tests/test_synthdef_registry_depth.py::test_synthdef_registry_band_helpers_map_values_to_named_bands -q`

3. `build_voice_shape` returns a frozen `VoiceShape` whose diagnostic
   fields match the underlying `SynthDefEntry`, including resolved
   `runtime_voice_name` for both live and quarantined voices.
   VERIFY: `pytest tests/test_synthdef_registry_depth.py::test_build_voice_shape_resolves_entry_diagnostics -q`

4. `build_synthdef_registry_report` returns a frozen
   `SynthDefRegistryReport` with per-voice shapes, ordered method and
   register-band counts (including zeros for absent register bands),
   ordered roles excluding quarantined voices, ordered quarantine
   reasons, and an ordered runtime-voice map for every quarantined
   entry.
   VERIFY: `pytest tests/test_synthdef_registry_depth.py::test_build_synthdef_registry_report_resolves_full_registry -q`

5. `summarize_synthdef_registry_report` returns a stable JSON-safe
   operator summary that round-trips through `json.dumps`.
   VERIFY: `pytest tests/test_synthdef_registry_depth.py::test_summarize_synthdef_registry_report_returns_json_safe_summary -q`

6. The new report path agrees with `resolve_voice`, `live_voices`,
   `quarantined_voices`, `voices_for_role`, and `covered_methods`
   end-to-end (no method is missing, runtime voices for quarantined
   entries match `resolve_voice`, and live role coverage matches
   `voices_for_role`).
   VERIFY: `pytest tests/test_synthdef_registry_depth.py::test_synthdef_registry_report_agrees_with_existing_lookups -q`

7. Fractal depth for `my-claw/tools/senseweave/synthdef_registry.py`
   reaches at least depth 2.
   VERIFY: `pytest tests/test_synthdef_registry_depth.py::test_synthdef_registry_reaches_depth_two -q`

8. Narrative HTTP service smoke regression remains covered (hardening
   anchor for `/healthz`, `/readyz`, and the bearer-token auth header).
   VERIFY: `pytest tests/test_smoke_narrative_script.py -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
