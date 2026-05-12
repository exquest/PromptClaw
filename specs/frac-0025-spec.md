# Task frac-0025 Specification: Motif Lifecycle Depth 2

## Problem Statement

`my-claw/tools/senseweave/motif_lifecycle.py` owns the deterministic
leitmotif state machine used by the CypherClaw composition pipeline.
Motifs move through the canonical lifecycle:

`statement -> variation -> contrast -> recall -> answer -> liquidation -> residue`

The existing module already works end-to-end: it exposes the canonical
transition graph, transformation helpers for each state, guarded
`advance(...)`, `MotifLifecycleManager`, and repertoire-shape recall.
`tests/test_motif_lifecycle.py` covers those behaviors, and
`RepertoireMemory` persists motif contours for later recall. The module
currently classifies at fractal depth 1 (`10/18 trivial, 8 real`) because
simple accessors, dataclass setup, and transition helpers outnumber deeper
logic. This task deepens the module to a simple depth-2 implementation by
adding one typed lifecycle path/report surface that produces stable,
operator-readable output without changing existing transformations,
transition validity, manager behavior, or repertoire-memory contracts.

The generated startup hardening checks for first-boot identity persistence
are already implemented outside this module: both daemon startup paths call
`bootstrap_identity()` before `FirstBootAnnouncer`, and the existing startup
anchor tests pass before implementation. This task keeps those tests as
mandatory regression anchors rather than changing unrelated startup code.

## Technical Approach

Extend `senseweave.motif_lifecycle` in place with stdlib-only, typed
helpers. No new dependencies, migrations, runtime state files, provider
secrets, database columns, or agent command strings are introduced.

- Add frozen dataclass `MotifLifecycleStep` containing one motif snapshot's
  resolved diagnostics: `motif_id`, `state`, `state_index`, `state_band`,
  `contour`, `rhythm`, `contour_span`, `rhythm_total`, and
  `material_units`.
- Add frozen dataclass `MotifLifecycleReport` containing one lifecycle
  path's summary: `origin_motif_id`, `current_motif_id`, `current_state`,
  `terminal_state`, `terminal`, `history`, `next_states`, `step_count`,
  `state_counts`, `contour_span_delta`, `rhythm_total_delta`,
  `material_ratio`, and `steps`.
- Add `lifecycle_state_index(state)`:
  - Return the zero-based index of `state` in `MOTIF_LIFECYCLE_STATES`;
    return `-1` for unknown states.
- Add `build_lifecycle_step(motif)`:
  - Build a `MotifLifecycleStep` from one `MotifNode`.
  - Use the existing canonical lifecycle bands from `score_tree`.
  - Compute `contour_span` from `max(contour) - min(contour)`,
    `rhythm_total` from the sum of rhythm values, and
    `material_units` from the larger of contour/rhythm lengths.
- Add `canonical_lifecycle_path(motif)`:
  - Starting at `motif.lifecycle_state`, advance through the remaining
    canonical lifecycle states one state at a time using the existing
    `advance(...)` function.
  - Return a tuple containing the original motif plus every transformed
    motif through `residue`.
- Add `build_lifecycle_report(motifs)`:
  - Build one `MotifLifecycleStep` per supplied motif, preserve path order,
    compute ordered state counts for every canonical lifecycle state,
    expose the current state's valid next states through
    `valid_next_states(...)`, mark terminal reports when no next states are
    available, and compute contour/rhythm/material deltas from the first
    step to the final step.
- Add `summarize_lifecycle_report(report)`:
  - Return a JSON-safe dictionary containing the report identity, current
    state, history, next-state information, aggregate deltas/counts, and a
    list of step dictionaries.
- Preserve all existing public transformation, `advance(...)`,
  `MotifLifecycleManager`, and `recall_shape_from_summary(...)` semantics so
  `tests/test_motif_lifecycle.py` remains unchanged.

## Edge Cases

- `lifecycle_state_index` returns `-1` for unknown state strings.
- `build_lifecycle_step` uses `0` for `contour_span` when the motif has no
  contour and uses `0.0` for `rhythm_total` when the rhythm is empty.
- `canonical_lifecycle_path` raises `ValueError` for an unknown starting
  lifecycle state via the same "unknown lifecycle state" wording used by
  `advance(...)`.
- `build_lifecycle_report` raises `ValueError` when called with an empty
  sequence because there is no origin/current motif to summarize.
- `material_ratio` is `0.0` when the origin step has zero material units.
- Startup identity hardening remains a regression anchor only: the daemon
  identity subsystem already covers first-run persistence and ordering for
  standalone and federated modes.

## Acceptance Criteria

1. Existing motif lifecycle transitions, transformations, manager behavior,
   and repertoire recall remain unchanged.
   VERIFY: `pytest tests/test_motif_lifecycle.py -q`

2. `lifecycle_state_index` maps canonical lifecycle states to their
   zero-based order and returns `-1` for unknown states.
   VERIFY: `pytest tests/test_motif_lifecycle_depth.py::test_lifecycle_state_index_maps_canonical_order -q`

3. `build_lifecycle_step` returns a frozen `MotifLifecycleStep` with stable
   state metadata and meaningful contour/rhythm/material diagnostics.
   VERIFY: `pytest tests/test_motif_lifecycle_depth.py::test_build_lifecycle_step_reports_material_shape -q`

4. `canonical_lifecycle_path` advances a motif through the one canonical
   path from statement to residue, producing one transformed motif per
   lifecycle state.
   VERIFY: `pytest tests/test_motif_lifecycle_depth.py::test_canonical_lifecycle_path_advances_statement_to_residue -q`

5. `build_lifecycle_report` returns a frozen `MotifLifecycleReport` with
   ordered history, canonical state counts, terminal-state metadata, and
   aggregate deltas for a full lifecycle path.
   VERIFY: `pytest tests/test_motif_lifecycle_depth.py::test_build_lifecycle_report_summarizes_full_path -q`

6. `summarize_lifecycle_report` returns a stable JSON-safe operator summary
   that round-trips through `json.dumps`.
   VERIFY: `pytest tests/test_motif_lifecycle_depth.py::test_summarize_lifecycle_report_returns_json_safe_summary -q`

7. The new path/report helpers work end-to-end with
   `MotifLifecycleManager.advance(...)` so manager history and the generated
   summary agree on the terminal state.
   VERIFY: `pytest tests/test_motif_lifecycle_depth.py::test_lifecycle_report_matches_manager_end_to_end_path -q`

8. Fractal depth for `my-claw/tools/senseweave/motif_lifecycle.py` reaches
   at least depth 2.
   VERIFY: `pytest tests/test_motif_lifecycle_depth.py::test_motif_lifecycle_reaches_depth_two -q`

9. Startup identity hardening remains covered for persisted standalone and
   federated first boots, and both daemon startup paths keep
   `bootstrap_identity()` before `FirstBootAnnouncer`.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

10. Full project validation remains clean.
    VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
