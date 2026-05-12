# Task frac-0004 Specification: Narrative Arc Depth 2

## Problem Statement

`my-claw/tools/inner_life/narrative_arc.py` defines CypherClaw's 30-minute
build/rise/climax/resolve/rest cycle. The fractal scanner currently classifies
it at depth 1 because three of its five public functions (`complete_cycle`,
`energy_for_phase`, `action_weight_for_phase`) are trivial single- or two-line
returns, leaving only `update_arc` and `start_new_cycle` with real logic
(`3/5 trivial, 2 real`). The module also lacks a public, typed surface for
querying the arc state without mutating an `InnerState` — every caller has to
either drive `update_arc` or replicate the phase boundary table inline.

The task is to deepen the module to a simple depth-2 implementation: one
straightforward path that adds meaningful, pure helpers for resolving and
summarizing the arc, while preserving the existing semantics that
`decision_engine` and `inner_life.main` already rely on.

## Technical Approach

Extend `narrative_arc.py` in place with a small set of pure, typed helpers:

- `phase_at(position)` — resolve the arc phase name for a clamped position in
  `[0, 1]`, using the same `PHASES` table as `update_arc`. Iterates the table
  with a real `for` loop and explicit fallback so it does not collapse to a
  trivial return.
- `phase_progress(inner)` — return a dict with `position`, `phase`,
  `phase_progress` (0–1 within the current phase), and `cycle_progress`
  (alias for position) so callers can render arc UI without re-deriving phase
  boundaries.
- `phase_profile(phase)` — return a dict with `phase`, `energy`,
  `action_weight`, and a stable string `label` ("gathering", "rising",
  "peaking", "resolving", "resting") that consolidates the existing
  `energy_for_phase` / `action_weight_for_phase` outputs into one operator
  surface. Uses an explicit phase→label mapping so unknown phases fall back
  to `"unknown"` with neutral defaults.
- `complete_cycle(inner)` is upgraded from a trivial dict literal to a real
  aggregation over `inner.today_events` and `inner.opinions_formed` so the
  returned summary includes `events_count`, `event_type_counts` (histogram),
  `opinions_count`, `final_phase`, `final_position`, plus the existing
  `cycle_id`, `duration_s`, `mood_at_end`, and `mode_at_end` keys.
- `arc_summary(inner)` — return a combined dict for diagnostics by composing
  `phase_progress(inner)` and `phase_profile(inner.arc_phase)`.

The existing public functions `update_arc`, `start_new_cycle`,
`energy_for_phase`, and `action_weight_for_phase` keep their current
signatures and observable semantics so existing callers
(`decision_engine.decide`, `inner_life.main`) continue to work without
edits. No new dependencies, migrations, secrets, or database columns are
introduced.

## Edge Cases

- Position values outside `[0, 1]` — `phase_at` clamps before the lookup so
  callers can pass raw cycle progress without pre-normalizing.
- Position at exactly `1.0` — `phase_at` returns `"rest"` (the inclusive
  upper-end phase) rather than falling through to `"unknown"`.
- Unknown phase names passed to `phase_profile` — return neutral defaults
  (`energy=0.5`, `action_weight=0.5`, `label="unknown"`) so missing data
  cannot crash diagnostics.
- `complete_cycle` on an `InnerState` with empty `today_events` /
  `opinions_formed` lists — return zero counts and an empty histogram
  without raising.
- `complete_cycle` on events with missing `type` keys — bucket them under
  `"unknown"` rather than raising `KeyError`.
- Existing `energy_for_phase("rest") < energy_for_phase("climax")` ordering
  is preserved so `tests/test_inner_life.py::TestNarrativeArc` does not
  regress.

## Acceptance Criteria

1. `phase_at` resolves the same phase boundaries as `update_arc` and clamps
   out-of-range input.
   VERIFY: `pytest tests/test_narrative_arc_depth.py::test_phase_at_resolves_table_boundaries tests/test_narrative_arc_depth.py::test_phase_at_clamps_out_of_range -q`

2. `phase_progress(inner)` returns position, phase, and within-phase
   progress derived from the same table.
   VERIFY: `pytest tests/test_narrative_arc_depth.py::test_phase_progress_reports_within_phase_fraction -q`

3. `phase_profile(phase)` combines energy and action-weight into a typed
   diagnostic dict and falls back cleanly on unknown phases.
   VERIFY: `pytest tests/test_narrative_arc_depth.py::test_phase_profile_combines_energy_and_action_weight tests/test_narrative_arc_depth.py::test_phase_profile_unknown_phase_uses_neutral_defaults -q`

4. `complete_cycle` returns a meaningful aggregate including event-type
   histogram, opinion count, and final arc state.
   VERIFY: `pytest tests/test_narrative_arc_depth.py::test_complete_cycle_aggregates_events_and_opinions tests/test_narrative_arc_depth.py::test_complete_cycle_handles_empty_history -q`

5. `arc_summary(inner)` composes `phase_progress` and `phase_profile` into a
   single diagnostic dict.
   VERIFY: `pytest tests/test_narrative_arc_depth.py::test_arc_summary_composes_progress_and_profile -q`

6. Existing `TestNarrativeArc` semantics in `tests/test_inner_life.py`
   continue to pass without modification.
   VERIFY: `pytest tests/test_inner_life.py::TestNarrativeArc -q`

7. Fractal depth for `my-claw/tools/inner_life/narrative_arc.py` reaches at
   least depth 2.
   VERIFY: `python - <<'PY'
import sys
sys.path.insert(0, "/Users/anthony/Programming/sdp-cli/src")
from sdp.fractal import classify_depth
result = classify_depth("my-claw/tools/inner_life/narrative_arc.py")
print(result.depth, result.reason)
assert result.depth >= 2
PY`
