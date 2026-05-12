# Task frac-0032 Specification: Voice Aliases Depth 2

## Problem Statement

`my-claw/tools/senseweave/voice_aliases.py` owns the runtime-safe voice
substitution table for CypherClaw playback. It exposes the
`RUNTIME_VOICE_ALIAS` mapping (`gong`, `sw_gong`, `bell`, `sw_bell`,
`sw_bell_warm`, `metal`, `sw_metal`, `grain`, `sw_grain`, `tabla_ge`,
`sw_tabla_ge`) and the single lookup helper `resolve_runtime_voice_name`
that maps a requested voice to the runtime-safe playback voice or
returns the original name when no alias is registered. Existing
callers and `tests/test_voice_aliases.py` rely on the eleven alias
entries, the canonical source/target pairs, and the dict-passthrough
behavior of `resolve_runtime_voice_name(voice_name)` for unaliased
inputs.

The module already works end-to-end for its one path: the live
runtime asks for a voice, the alias table either substitutes the
runtime-safe replacement or returns the original name, and playback
proceeds. It currently classifies at fractal depth 1
(`all functions return trivial values`) because the public surface is
the single one-line `dict.get` lookup. This task deepens the module
to a simple depth-2 implementation by adding a typed
diagnostic/report surface that delegates to the existing alias table
and produces stable operator-readable output without changing any
existing lookup behavior.

The generated startup hardening checks for `bootstrap_identity()`
and `FirstBootAnnouncer` target the daemon identity subsystem, not
this pure alias-table module. The current tree already calls
`bootstrap_identity()` before `FirstBootAnnouncer` in both daemon
startup paths and contains integration coverage for standalone and
federated identity persistence. This task keeps those tests as
mandatory regression anchors.

## Technical Approach

Extend `senseweave.voice_aliases` in place with stdlib-only, typed
helpers. No new dependencies, migrations, runtime state files,
provider secrets, database columns, or agent command strings are
introduced.

- Preserve `RUNTIME_VOICE_ALIAS` and `resolve_runtime_voice_name` so
  `tests/test_voice_aliases.py` remains unchanged.
- Add `voice_namespace(voice_name)` returning the namespace band:
  - voice starts with `"sw_"` -> `"senseweave"`
  - otherwise -> `"core"`
- Add `voice_alias_family(voice_name)` returning a stable family band
  derived from the canonical (sw-stripped) source name:
  - `"gong"`, `"bell"`, or `"bell_warm"` -> `"struck_tonal"`
  - `"metal"` -> `"metallic"`
  - `"grain"` -> `"granular"`
  - `"tabla_ge"` -> `"drum"`
  - any other source name -> `"other"`
- Add `is_aliased_voice(voice_name)` returning `True` when the voice
  name is a key of `RUNTIME_VOICE_ALIAS`.
- Add `iter_alias_pairs()` yielding `(source, target)` tuples in the
  declaration order of `RUNTIME_VOICE_ALIAS`.
- Add `aliases_for_target(target)` returning the tuple of source
  voice names whose alias resolves to `target`, in declaration order.
- Add `alias_chain(voice_name)`:
  - Start the chain with the requested voice name.
  - Follow each alias through `RUNTIME_VOICE_ALIAS` while the next
    name is registered.
  - Stop when the next alias is already in the chain (cycle guard).
  - Stop when the resolved name is not aliased.
  - Return the names in traversal order as a tuple.
- Add frozen dataclass `VoiceAliasEntry` containing one alias view:
  `source`, `target`, `namespace`, `family`, `is_senseweave_variant`,
  and `is_changed` (true when source differs from target).
- Add frozen dataclass `VoiceAliasReport` containing the
  table-level view: `total_aliases`, `source_voices`,
  `target_voices`, `namespace_counts`, `family_counts`,
  `senseweave_variant_count`, `core_alias_count`,
  `unique_target_count`, `target_to_sources`, `entries`.
- Add `build_voice_alias_entry(source, target)`:
  - Compute namespace via `voice_namespace`.
  - Compute family from the canonical source via
    `voice_alias_family` after stripping any `"sw_"` prefix.
  - Set `is_senseweave_variant = source.startswith("sw_")`.
  - Set `is_changed = source != target`.
- Add `build_voice_alias_report()`:
  - Iterate `RUNTIME_VOICE_ALIAS.items()` in declaration order.
  - Build entries via `build_voice_alias_entry`.
  - Compute namespace/family counts, senseweave variant count, core
    alias count, unique target count, and the
    target-to-sources mapping (each target maps to its sources in
    declaration order).
- Add `summarize_voice_alias_report(report)`:
  - Return a JSON-safe dictionary mirroring the report fields, with
    tuple values converted to lists and entry records expanded into
    primitive dictionaries.
- Keep implementation one-path: the report helpers read the existing
  alias table and use the existing lookup helpers instead of
  introducing a second alias-resolution algorithm.

## Edge Cases

- `voice_namespace` treats the literal prefix `"sw_"` as the
  senseweave marker; any other name (including `""`) is `"core"`.
- `voice_alias_family` strips a single `"sw_"` prefix before family
  lookup, so `sw_gong` resolves to `"struck_tonal"` and unknown
  names resolve to `"other"`.
- `is_aliased_voice` returns `False` for unknown names without
  raising.
- `aliases_for_target` returns an empty tuple when no source resolves
  to the target.
- `alias_chain` starts with the requested voice name. For an unknown
  name the chain is a single-element tuple `(voice_name,)`. For a
  registered cycle the chain stops on the first repeated name so
  current alias data does not loop.
- `summarize_voice_alias_report` returns only primitives, lists, and
  dictionaries of primitives so `json.dumps(...)` can serialize it
  directly.
- Startup identity hardening is owned by the daemon identity
  subsystem and remains a regression anchor through
  `tests/test_first_boot.py::TestStartupIdentityPersistence` and
  `tests/test_governor_integration.py::TestStartupIdentityWiring`.

## Acceptance Criteria

1. Existing voice alias lookup behavior remains unchanged.
   VERIFY: `pytest tests/test_voice_aliases.py -q`

2. Namespace, family, `is_aliased_voice`, `iter_alias_pairs`,
   `aliases_for_target`, and `alias_chain` helpers map alias-table
   inputs to the documented deterministic outputs.
   VERIFY: `pytest tests/test_voice_aliases_depth.py::test_voice_alias_helpers_are_stable -q`

3. `build_voice_alias_entry` returns a frozen `VoiceAliasEntry`
   whose fields mirror the underlying alias mapping.
   VERIFY: `pytest tests/test_voice_aliases_depth.py::test_build_voice_alias_entry_resolves_alias_diagnostics -q`

4. `build_voice_alias_report` returns a frozen `VoiceAliasReport`
   with ordered source/target voices, namespace and family counts,
   target-to-sources mapping, and per-alias entries.
   VERIFY: `pytest tests/test_voice_aliases_depth.py::test_build_voice_alias_report_resolves_full_table -q`

5. `summarize_voice_alias_report` returns a stable JSON-safe
   operator summary that round-trips through `json.dumps`.
   VERIFY: `pytest tests/test_voice_aliases_depth.py::test_summarize_voice_alias_report_returns_json_safe_summary -q`

6. The new report path agrees with `resolve_runtime_voice_name`,
   `is_aliased_voice`, `iter_alias_pairs`, `aliases_for_target`, and
   `alias_chain` end-to-end.
   VERIFY: `pytest tests/test_voice_aliases_depth.py::test_voice_alias_report_agrees_with_existing_lookups -q`

7. Fractal depth for `my-claw/tools/senseweave/voice_aliases.py`
   reaches at least depth 2.
   VERIFY: `pytest tests/test_voice_aliases_depth.py::test_voice_aliases_reaches_depth_two -q`

8. Startup identity hardening remains covered for first-boot
   persistence and startup wiring in both daemon entrypoints.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
