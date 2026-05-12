# Task frac-0026 Specification: EMSD Runtime Depth 2

## Problem Statement

`my-claw/tools/senseweave/emsd_runtime.py` builds the live EMSD context that
the CypherClaw composition pipeline hands to the composer/state layer for
every song. It exposes the frozen `EMSDLiveContext` dataclass plus
`build_live_emsd_context(...)` (which folds arc + capstone phase + density
bias) and `composer_emsd_extras(context)` (which flattens the context into a
composer-state payload). `tests/test_emsd_runtime.py` covers those
behaviors and the wider EMSD/Theramini/mix integration tests depend on the
existing field names.

The module currently classifies at fractal depth 1
(`3/4 trivial, 1 real`) because the only function with real logic is
`build_live_emsd_context`; `_clamp`, the `EMSDLiveContext.identity`
property, and `composer_emsd_extras` are short return-only helpers that
outnumber it. This task deepens the module to a simple depth-2
implementation by adding one typed snapshot/report surface that turns one
or more `EMSDLiveContext` instances into stable operator-readable
diagnostics without changing existing field names, builder behavior, or
composer-extras output.

The narrative HTTP hardening checks (`/healthz`, `/readyz`, bearer-token
auth header) are already implemented in the narrative service and exercised
by `tests/test_smoke_narrative_script.py`; this task keeps that smoke test
as a mandatory regression anchor rather than touching unrelated narrative
code. Startup identity hardening is likewise already implemented; the
existing first-boot anchor tests stay as regression coverage.

## Technical Approach

Extend `senseweave.emsd_runtime` in place with stdlib-only, typed helpers.
No new dependencies, migrations, runtime state files, provider secrets,
database columns, or agent command strings are introduced.

- Add module-level constant `CANONICAL_ARC_PHASES: tuple[str, ...]` mirroring
  `procedural_arc.ARC_PHASES`, in the same order: `"Divination"`,
  `"Emergence"`, `"Conversation"`, `"Convergence"`, `"Crystallization"`.
- Add module-level constant `CANONICAL_DENSITY_BANDS: tuple[str, ...]`
  with the names `"calm"`, `"neutral"`, `"intense"` in that order.
- Add frozen dataclass `EMSDPhaseSnapshot` containing one live context's
  resolved diagnostics: `arc_phase`, `arc_phase_index`, `arc_phase_band`,
  `family_name`, `patch_name`, `sample_source`, `arc_density_target`,
  `arc_max_active_roles`, `mix_target_lufs`, `density_bias`,
  `density_band`, `artistic_identity`.
- Add frozen dataclass `EMSDRuntimeReport` containing one runtime
  trajectory's summary: `snapshots`, `snapshot_count`,
  `arc_phase_history`, `phase_counts`, `band_counts`,
  `distinct_families`, `distinct_patches`, `distinct_sample_sources`,
  `transitions`, `mean_density_bias`, `max_density_bias`,
  `min_density_bias`.
- Add `arc_phase_index(phase_name)`:
  - Return the zero-based index of `phase_name` in `CANONICAL_ARC_PHASES`;
    return `-1` for unknown names (including `""`).
- Add `arc_phase_band(phase_name)`:
  - Map an arc phase name to one of `"opening"`, `"dialogue"`, or
    `"resolution"` using the canonical ordering. `"Divination"` and
    `"Emergence"` map to `"opening"`; `"Conversation"` maps to
    `"dialogue"`; `"Convergence"` and `"Crystallization"` map to
    `"resolution"`. Unknown names return `"unclassified"`.
- Add `density_pressure_band(density_bias)`:
  - Map a density bias value to one of the `CANONICAL_DENSITY_BANDS`
    using the cutpoints `density_bias <= -0.05` -> `"calm"`,
    `density_bias >= 0.05` -> `"intense"`, otherwise `"neutral"`.
- Add `build_phase_snapshot(context)`:
  - Build an `EMSDPhaseSnapshot` from one `EMSDLiveContext`.
  - Resolve `arc_phase`, `arc_phase_index`, and `arc_phase_band` from
    the context's arc phase name, `family_name`/`patch_name` from the
    capstone phase plan, `sample_source` from
    `context.phase_plan.sampling.source.name`, mix LUFS from
    `context.phase_plan.mix.target_lufs`, `density_bias` /
    `density_band` from the context bias, `arc_density_target` and
    `arc_max_active_roles` from the arc directive, and
    `artistic_identity` from `context.identity.statement`.
- Add `build_runtime_report(snapshots)`:
  - Build one `EMSDRuntimeReport` from a sequence of
    `EMSDPhaseSnapshot` entries, preserving order.
  - `phase_counts` covers every `CANONICAL_ARC_PHASES` entry (zero when
    absent); snapshots whose `arc_phase` is not canonical are excluded
    from `phase_counts`.
  - `band_counts` covers every `CANONICAL_DENSITY_BANDS` entry (zero
    when absent).
  - `distinct_families`, `distinct_patches`, and
    `distinct_sample_sources` preserve first-seen order across the
    snapshots.
  - `transitions` is the ordered tuple of `(prev_phase, next_phase)`
    pairs across consecutive snapshots whose `arc_phase` differs.
  - `mean_density_bias`, `max_density_bias`, and `min_density_bias`
    are rounded to 4 decimal places.
- Add `summarize_runtime_report(report)`:
  - Return a JSON-safe dictionary covering `snapshot_count`,
    `arc_phase_history`, `phase_counts`, `band_counts`,
    `distinct_families`, `distinct_patches`, `distinct_sample_sources`,
    `transitions` (each `[prev, next]`), aggregate density statistics,
    and a `snapshots` list whose entries mirror each snapshot's fields.
    All values must be primitives, lists, or dictionaries of primitives.
- Preserve all existing public `EMSDLiveContext` fields,
  `build_live_emsd_context(...)` semantics, and
  `composer_emsd_extras(...)` output so `tests/test_emsd_runtime.py`
  remains unchanged and downstream EMSD/composer integration tests
  continue to pass.

## Edge Cases

- `arc_phase_index` returns `-1` for unknown phase names and the empty
  string.
- `arc_phase_band` returns `"unclassified"` for any string that is not
  in `CANONICAL_ARC_PHASES`.
- `density_pressure_band` treats `-0.05` exactly as `"calm"` and `0.05`
  exactly as `"intense"`; values strictly between are `"neutral"`.
- `build_runtime_report` raises `ValueError` when called with an empty
  sequence because there is no snapshot to summarize.
- `build_runtime_report` keeps `phase_counts` keyed by every canonical
  arc phase even when the trajectory only visits a subset; snapshots
  whose `arc_phase` is unknown still appear in `arc_phase_history` and
  `transitions` but not in `phase_counts`.
- `transitions` is empty for a single-snapshot report and skips
  consecutive snapshots that stay in the same arc phase.
- Narrative HTTP hardening (`/healthz`, `/readyz`, bearer-token auth
  header) is owned by the narrative service and remains a regression
  anchor through `tests/test_smoke_narrative_script.py`.
- Startup identity hardening is owned by the daemon identity subsystem
  and remains a regression anchor through
  `tests/test_first_boot.py::TestStartupIdentityPersistence` and
  `tests/test_governor_integration.py::TestStartupIdentityWiring`.

## Acceptance Criteria

1. Existing live EMSD context, density-bias, arc-phase wiring, and
   composer extras behavior remains unchanged.
   VERIFY: `pytest tests/test_emsd_runtime.py -q`

2. `arc_phase_index` maps canonical arc phases to their zero-based order
   and returns `-1` for unknown names.
   VERIFY: `pytest tests/test_emsd_runtime_depth.py::test_arc_phase_index_maps_canonical_order -q`

3. `arc_phase_band` maps canonical arc phases to bands and falls back to
   `"unclassified"` for unknown inputs.
   VERIFY: `pytest tests/test_emsd_runtime_depth.py::test_arc_phase_band_maps_phases_to_bands -q`

4. `density_pressure_band` maps density bias values to the canonical
   density bands at the documented cutpoints.
   VERIFY: `pytest tests/test_emsd_runtime_depth.py::test_density_pressure_band_maps_values_to_bands -q`

5. `build_phase_snapshot` returns a frozen `EMSDPhaseSnapshot` with
   stable arc/family/patch/sample/mix diagnostics derived from one
   `EMSDLiveContext`.
   VERIFY: `pytest tests/test_emsd_runtime_depth.py::test_build_phase_snapshot_resolves_live_context -q`

6. `build_runtime_report` returns a frozen `EMSDRuntimeReport` with
   ordered phase history, canonical phase/band counts (including zeros
   for absent canonical entries), ordered distinct family/patch/source
   tuples, transitions, and aggregate density statistics.
   VERIFY: `pytest tests/test_emsd_runtime_depth.py::test_build_runtime_report_summarizes_trajectory -q`

7. `summarize_runtime_report` returns a stable JSON-safe operator
   summary that round-trips through `json.dumps`.
   VERIFY: `pytest tests/test_emsd_runtime_depth.py::test_summarize_runtime_report_returns_json_safe_summary -q`

8. The new snapshot/report helpers work end-to-end with
   `build_live_emsd_context(...)` so a sequence of live contexts
   produces a stable phase history that matches the snapshots' arc
   phases.
   VERIFY: `pytest tests/test_emsd_runtime_depth.py::test_runtime_report_matches_live_contexts_end_to_end -q`

9. Fractal depth for `my-claw/tools/senseweave/emsd_runtime.py` reaches
   at least depth 2.
   VERIFY: `pytest tests/test_emsd_runtime_depth.py::test_emsd_runtime_reaches_depth_two -q`

10. Narrative HTTP service smoke regression remains covered (hardening
    anchor for `/healthz`, `/readyz`, and the bearer-token auth header).
    VERIFY: `pytest tests/test_smoke_narrative_script.py -q`

11. Startup identity hardening remains covered for first-boot
    persistence and ordering.
    VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

12. Full project validation remains clean.
    VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
