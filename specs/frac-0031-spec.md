# Task frac-0031 Specification: Synthesis Architecture Registry Depth 2

## Problem Statement

`my-claw/tools/senseweave/synthesis_architecture_registry.py` owns the
canonical synthesis-family strategy registry for SenseWeave production
planning. Existing callers and `tests/test_synthesis_architecture_registry.py`
depend on the six architecture entries (`subtractive`, `fm`, `additive`,
`granular`, `physical_model`, `spectral`), their labels/summaries, role tags,
safe macro-control ranges, arc-phase affinity table, fallbacks, and lookup
helpers (`get_strategy`, `strategies_for_role`, `architectures_for_phase`,
`best_architecture_for_phase`, `resolve_architecture`, and
`covered_architectures`).

The module already works end-to-end for its one path: procedural-arc and
production-course data name a synthesis architecture, and the registry resolves
that architecture or ranks candidates by role/arc phase. It currently
classifies at fractal depth 1 (`5/6 trivial, 1 real`) because the public lookup
surface is mostly one-line return helpers. This task deepens the module to
depth 2 by adding one typed diagnostic/report path that produces meaningful
operator-readable output from the existing registry without changing any
existing lookup behavior.

The generated startup hardening checks for `bootstrap_identity()` and
`FirstBootAnnouncer` target the daemon identity subsystem, not this pure
strategy-registry module. The current tree already calls `bootstrap_identity()`
before `FirstBootAnnouncer` in both daemon startup paths and contains
integration coverage for standalone and federated identity persistence. This
task keeps those tests as mandatory regression anchors.

## Technical Approach

Extend `senseweave.synthesis_architecture_registry` in place with stdlib-only,
typed helpers. No new dependencies, migrations, runtime state files, provider
secrets, database columns, or agent command strings are introduced.

- Preserve every existing architecture entry and existing public lookup helper
  so `tests/test_synthesis_architecture_registry.py`, procedural-arc
  consistency checks, and production-course consistency checks remain
  unchanged.
- Add `affinity_band(value)` returning a stable named band:
  - `value < 0.4` -> `"low"`
  - `0.4 <= value < 0.7` -> `"medium"`
  - `value >= 0.7` -> `"high"`
- Add `control_span_band(control)` returning a stable named band from the
  control's safe range width:
  - `width <= 0.5` -> `"narrow"`
  - `0.5 < width <= 1.0` -> `"standard"`
  - `width > 1.0` -> `"wide"`
- Add `fallback_chain(architecture_id)`:
  - Start with `resolve_architecture(architecture_id)`.
  - Follow each strategy's `fallback` while it names a registered architecture.
  - Stop when the next fallback is already in the chain.
  - Return architecture IDs in traversal order.
- Add frozen dataclass `ArchitectureProfile` containing one strategy's resolved
  diagnostic view: `architecture_id`, `label`, `summary`, `role_tags`,
  `macro_control_count`, `macro_control_names`, `default_controls`,
  `control_span_bands`, `best_phase`, `best_phase_affinity`,
  `high_affinity_phases`, `affinity_bands`, `fallback`,
  `fallback_chain`, and `role_count`.
- Add frozen dataclass `ArchitectureRegistryReport` containing the
  registry-level view: `total_count`, `architecture_ids`, `phases`,
  `phase_winners`, `phase_architectures`, `roles`, `role_architectures`,
  `fallback_map`, `missing_required_architectures`,
  `missing_required_phases`, `macro_control_counts`, and `profiles`.
- Add `build_architecture_profile(strategy)`:
  - Compute macro-control names/defaults/span bands from existing
    `macro_controls`.
  - Compute best phase, high-affinity phases, and named affinity bands from
    existing `arc_affinity`.
  - Compute fallback chain through `fallback_chain(...)`.
- Add `build_architecture_registry_report()`:
  - Iterate `_STRATEGIES` in declaration order.
  - Build profiles, phase winners, phase-ranked architecture IDs, ordered
    roles, role-to-architecture map, fallback map, macro-control counts, and
    missing required architecture/phase diagnostics.
- Add `summarize_architecture_registry_report(report)`:
  - Return a JSON-safe dictionary mirroring the report fields, with tuple
    values converted to lists and profile records expanded into primitive
    dictionaries.
- Keep implementation one-path: the report helpers read the existing registry
  and use the existing lookup/ranking behavior instead of introducing a second
  architecture-selection algorithm.

## Edge Cases

- Band helper cutpoints follow the inclusive/exclusive boundaries documented
  above.
- Unknown architecture IDs entering `fallback_chain(...)` first resolve through
  the existing `resolve_architecture(...)` fallback behavior, so the chain
  starts with `subtractive` today.
- Fallback-chain traversal stops on cycles so current two-node fallback loops
  (`subtractive` -> `additive` -> `fm` -> `subtractive`, or
  `granular` -> `spectral` -> `granular`) are reported once per architecture
  without infinite recursion.
- `missing_required_architectures` reports any literal architecture ID that is
  absent from the registry. Today it is empty.
- `missing_required_phases` reports required arc phases absent from any
  strategy's affinity map. Today it is empty because existing tests require
  every strategy to cover every phase.
- `summarize_architecture_registry_report` returns only primitives, lists, and
  dictionaries of primitives so `json.dumps(...)` can serialize it directly.
- Startup identity hardening is owned by the daemon identity subsystem and
  remains a regression anchor through
  `tests/test_first_boot.py::TestStartupIdentityPersistence` and
  `tests/test_governor_integration.py::TestStartupIdentityWiring`.

## Acceptance Criteria

1. Existing synthesis architecture registry behavior remains unchanged.
   VERIFY: `pytest tests/test_synthesis_architecture_registry.py -q`

2. Band and fallback helpers map affinity values, macro-control spans, and
   fallback chains to the documented deterministic outputs.
   VERIFY: `pytest tests/test_synthesis_architecture_registry_depth.py::test_architecture_helper_bands_and_fallback_chain_are_stable -q`

3. `build_architecture_profile` returns a frozen `ArchitectureProfile` whose
   fields mirror the underlying `ArchitectureStrategy`.
   VERIFY: `pytest tests/test_synthesis_architecture_registry_depth.py::test_build_architecture_profile_resolves_strategy_diagnostics -q`

4. `build_architecture_registry_report` returns a frozen
   `ArchitectureRegistryReport` with ordered architecture IDs, phases, phase
   winners, role mappings, fallback map, missing-coverage diagnostics, macro
   counts, and per-architecture profiles.
   VERIFY: `pytest tests/test_synthesis_architecture_registry_depth.py::test_build_architecture_registry_report_resolves_full_registry -q`

5. `summarize_architecture_registry_report` returns a stable JSON-safe
   operator summary that round-trips through `json.dumps`.
   VERIFY: `pytest tests/test_synthesis_architecture_registry_depth.py::test_summarize_architecture_registry_report_returns_json_safe_summary -q`

6. The new report path agrees with `best_architecture_for_phase`,
   `architectures_for_phase`, `strategies_for_role`, `resolve_architecture`,
   and `covered_architectures` end-to-end.
   VERIFY: `pytest tests/test_synthesis_architecture_registry_depth.py::test_architecture_registry_report_agrees_with_existing_lookups -q`

7. Fractal depth for
   `my-claw/tools/senseweave/synthesis_architecture_registry.py` reaches at
   least depth 2.
   VERIFY: `pytest tests/test_synthesis_architecture_registry_depth.py::test_synthesis_architecture_registry_reaches_depth_two -q`

8. Startup identity hardening remains covered for first-boot persistence and
   startup wiring in both daemon entrypoints.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
