# Task frac-0012 Specification: Genre Literacy Depth 2

## Problem Statement

`my-claw/tools/senseweave/genre_literacy.py` already ships the ten-genre
`GenreStrategy` library plus `select_genre`, but its public surface beyond the
selector is mostly trivial registry lookups (`strategy_for_genre`,
`all_strategies`, `genre_arc_affinity`). The fractal scanner classifies the
module at depth 1 (`3/5 trivial, 2 real (test boosted)`): callers can pick a
genre, but they cannot describe a genre to operators, compare two genres for
mix-aware crossfade decisions, blend numeric hints when crossfading between
traditions, or plan a phase-by-phase genre rotation that respects fatigue.

The task is to deepen the module to a simple depth-2 implementation: one
straightforward analysis path that turns a `GenreStrategy` into a stable
operator-readable summary, computes a bounded compatibility score between two
genre traditions, blends their numeric hint values into a weighted hybrid, and
plans a fatigue-aware genre sequence across an arc. Existing
`GenreStrategy`/`REQUIRED_GENRES` data, `strategy_for_genre`, `all_strategies`,
`genre_arc_affinity`, `best_genres_for_phase`, and `select_genre` semantics
must keep working.

## Technical Approach

Extend `genre_literacy.py` in place with typed, pure helpers:

- `GenreSummary` frozen dataclass with `genre_id`, `label`, `tempo_range`,
  `texture_density`, `chromatic_tolerance`, `voice_count_range`,
  `dominant_grooves` (top-2 groove types), `top_arc_phases` (top-2 phases by
  affinity), `mood_signature` (one of `"calm"`, `"balanced"`, `"intense"`).
- `GenreBlend` frozen dataclass with `left_id`, `right_id`, `weight`,
  `tempo_range`, `texture_density`, `chromatic_tolerance`, `rubato_tolerance`,
  `repetition_tolerance`, `spatial_width`, and `shared_modes` (sorted tuple of
  modal preferences appearing in both strategies).
- `summarize_strategy(genre_id)` returns a `GenreSummary` derived from the
  strategy's numeric and tuple fields. `mood_signature` buckets by texture
  density: `"calm"` for `<0.4`, `"intense"` for `>=0.6`, otherwise
  `"balanced"`. `dominant_grooves` and `top_arc_phases` use stable
  alphabetical / score-then-name ordering on ties.
- `genre_compatibility(left_id, right_id)` returns a bounded `[0.0, 1.0]`
  score that combines: average arc-affinity cosine across the five canonical
  phases, shared modal preferences ratio, shared groove type ratio, and the
  inverse normalized distance between texture density and chromatic tolerance.
  Identical genre ids return `1.0`; the score is symmetric in the two ids.
- `blend_genre_strategies(left_id, right_id, *, weight=0.5)` returns a
  `GenreBlend` with each numeric field linearly interpolated between the two
  strategies (`weight=0.0` matches `left`, `weight=1.0` matches `right`).
  Tempo range interpolates each endpoint independently. `weight` is clamped
  into `[0.0, 1.0]`. `shared_modes` uses set intersection on the modal
  preference tuples, sorted alphabetically.
- `recommend_genre_sequence(arc_phases, *, recent_genres=(), avoid_repeat=True)`
  walks the supplied phases, calls the existing `select_genre` per phase using
  `cadence_state="occupied_day"` and `groove_identity="pulse"` defaults, and
  appends each chosen genre into a rolling fatigue window so back-to-back
  duplicates are penalized. `avoid_repeat=True` re-runs `select_genre` with
  the chosen genre force-pushed into recent history to bias the next pick.

The implementation only consumes the existing `_GENRE_STRATEGIES`,
`REQUIRED_GENRES`, and `select_genre` data. No new dependencies, migrations,
runtime state, provider secrets, or agent commands are introduced.

## Edge Cases

- Unknown genre ids in any depth-2 helper raise `KeyError` so callers get the
  same failure mode as `strategy_for_genre`.
- `genre_compatibility(g, g)` returns exactly `1.0` for any known genre id.
- `blend_genre_strategies` clamps `weight` so callers can pass un-validated
  fractions without crashing the blend.
- `recommend_genre_sequence([])` returns an empty list and never calls
  `select_genre`.
- An empty `tempo_range` is impossible per the existing strategy data; the
  helpers therefore assume both endpoints are present and ordered.
- The startup identity hardening bullets target the daemon startup subsystem,
  not this pure literacy module. Existing startup identity tests remain
  mandatory regression anchors for this task.

## Acceptance Criteria

1. `summarize_strategy` returns a stable, operator-readable `GenreSummary`
   with mood bucketing and top-2 grooves / arc phases for every genre id.
   VERIFY: `pytest tests/test_genre_literacy_depth.py::test_summarize_strategy_is_stable_and_meaningful -q`

2. `genre_compatibility` returns `1.0` for identical genre ids, is symmetric
   in its two arguments, and stays inside `[0.0, 1.0]` for every pair.
   VERIFY: `pytest tests/test_genre_literacy_depth.py::test_genre_compatibility_is_bounded_and_symmetric -q`

3. `blend_genre_strategies` linearly interpolates numeric fields, clamps
   `weight` into `[0.0, 1.0]`, and reports the modal-preference intersection.
   VERIFY: `pytest tests/test_genre_literacy_depth.py::test_blend_genre_strategies_interpolates_and_intersects -q`

4. `recommend_genre_sequence` returns one genre per supplied arc phase, every
   choice belongs to `REQUIRED_GENRES`, and back-to-back duplicates are rare
   when `avoid_repeat=True`.
   VERIFY: `pytest tests/test_genre_literacy_depth.py::test_recommend_genre_sequence_picks_per_phase_and_avoids_repeats -q`

5. Existing genre literacy registry, selection, and arc-affinity tests still
   pass.
   VERIFY: `pytest tests/test_genre_literacy.py -q`

6. Fractal depth for `my-claw/tools/senseweave/genre_literacy.py` reaches at
   least depth 2.
   VERIFY: `python - <<'PY'
import sys
sys.path.insert(0, "/Users/anthony/Programming/sdp-cli/src")
from sdp.fractal import classify_depth
result = classify_depth("my-claw/tools/senseweave/genre_literacy.py")
print(result.depth, result.reason)
assert result.depth >= 2
PY`

7. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

8. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
