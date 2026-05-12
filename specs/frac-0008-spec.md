# Task frac-0008 Specification: Commission Context Depth 2

## Problem Statement

`my-claw/tools/senseweave/commission_context.py` derives the
`(day_phase, weekly_phase)` pair that the duet composer feeds into
`commission_piece`. Today the module is a single trivial helper that
or-chains `getattr` calls into one return. The fractal scanner therefore
classifies it at depth 1 (`1/1 trivial, 0 real`): callers cannot ask the
module for normalized attention/pressure values or for a stable bundle of
the inputs the score-tree commission actually needs, so the same `getattr`
plumbing is duplicated in `duet_composer._build_score_tree_piece`.

The task is to deepen the module to a simple depth-2 implementation: one
straightforward path that adds typed, pure helpers for projecting the
commission inputs and summarizing them while preserving the existing
`commission_context_from_tracker_plan` behavior so `duet_composer` and the
existing test suite keep working.

## Technical Approach

Extend `commission_context.py` in place with a small set of pure, typed
helpers around the existing `(tracker_plan, world)` inputs:

- `commission_context_from_tracker_plan(tracker_plan, world)` — keep its
  public `(day_phase, weekly_phase)` contract but rewrite the body to walk
  candidate sources in order, strip whitespace, and only fall back to the
  `"day"` default for `day_phase` (weekly_phase keeps `""` when both
  sources are empty, matching today's behavior).
- `attention_pressure_from_world(world)` — return
  `(attention_score, narrative_pressure)` pulled from `world.attention_score`
  and `world.experimentation_bias`, each clamped to `[0.0, 1.0]` and
  defaulting to `0.0` when the source is missing or non-numeric. This
  centralizes the inline `float(world.attention_score or 0.0)` plumbing
  used by `duet_composer`.
- `CommissionInputs` — a frozen dataclass of the fields
  `commission_piece` actually consumes: `cadence_state`, `occupancy_state`,
  `day_phase`, `weekly_phase`, `attention_score`, `narrative_pressure`,
  `song_num`, `hour`. Constructed via
  `commission_inputs_from_tracker_plan(tracker_plan, world, song_num, hour)`.
- `summarize_commission_context(inputs)` — return a stable diagnostic
  dictionary (`cadence`, `occupancy`, `day_phase`, `weekly_phase`,
  `song_num`, `hour`, `attention` bucket label, `narrative_pressure`)
  so operator logs can render a snapshot without exposing dataclass
  internals or runtime objects.

The existing public `commission_context_from_tracker_plan` keyword-only
signature and return type are preserved, so `duet_composer` and
`tests/test_commission_context.py` keep working without modification. No
new dependencies, migrations, secrets, provider commands, or database
columns are introduced.

## Edge Cases

- `commission_context_from_tracker_plan` strips whitespace from candidate
  values, so a tracker plan with `day_phase="  "` falls through to the
  world before defaulting to `"day"`.
- `commission_context_from_tracker_plan` keeps the empty-string fallback
  for `weekly_phase` to preserve today's behavior (callers may pass `""`
  through to `commission_piece` unchanged).
- `attention_pressure_from_world` clamps non-numeric or `None` inputs to
  `0.0`, swallowing `TypeError`/`ValueError` from `float()` so a stale
  world snapshot cannot crash the score-tree path.
- `attention_pressure_from_world` clamps values above `1.0` down to `1.0`
  and values below `0.0` up to `0.0`, so unexpected sensor spikes do not
  propagate raw into commission scoring.
- `commission_inputs_from_tracker_plan` coerces `song_num`/`hour` through
  `int()` and supplies `"uncertain"` as the default occupancy label when
  the tracker plan omits one, matching `tracker_cadence._occupancy_state`.
- `summarize_commission_context` buckets `attention_score` into `"low"`
  (`< 0.33`), `"moderate"` (`< 0.66`), and `"high"` (`>= 0.66`) so logs
  stay stable across small sensor jitters.
- Startup identity hardening remains a regression anchor. Existing tests
  cover `bootstrap_identity()` persistence and ordering before
  `FirstBootAnnouncer` for standalone and federated startup paths.

## Acceptance Criteria

1. `commission_context_from_tracker_plan` still falls back from tracker
   plan to world to the `"day"` default and preserves the existing
   weekly_phase contract.
   VERIFY: `pytest tests/test_commission_context.py tests/test_commission_context_depth.py::test_commission_context_prefers_tracker_then_world_then_default -q`

2. `attention_pressure_from_world` clamps attention score and narrative
   pressure into `[0.0, 1.0]` and treats malformed inputs as `0.0`.
   VERIFY: `pytest tests/test_commission_context_depth.py::test_attention_pressure_clamps_to_unit_interval tests/test_commission_context_depth.py::test_attention_pressure_handles_malformed_inputs -q`

3. `commission_inputs_from_tracker_plan` returns a `CommissionInputs`
   bundle with cadence, occupancy, phase, attention, pressure, song_num,
   and hour fields populated from the tracker plan and world.
   VERIFY: `pytest tests/test_commission_context_depth.py::test_commission_inputs_bundle_populates_all_fields -q`

4. `summarize_commission_context` emits a stable, operator-readable dict
   with bucketed attention and rounded narrative pressure.
   VERIFY: `pytest tests/test_commission_context_depth.py::test_summarize_commission_context_emits_stable_snapshot -q`

5. Fractal depth for `my-claw/tools/senseweave/commission_context.py`
   reaches at least depth 2.
   VERIFY: `python - <<'PY'
import sys
sys.path.insert(0, "/Users/anthony/Programming/sdp-cli/src")
from sdp.fractal import classify_depth
result = classify_depth("my-claw/tools/senseweave/commission_context.py")
print(result.depth, result.reason)
assert result.depth >= 2
PY`

6. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
