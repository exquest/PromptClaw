# Task frac-0009 Specification: Counterpoint Rules Depth 2

## Problem Statement

`my-claw/tools/senseweave/counterpoint_rules.py` already has the core
relationship registry plus dissonance/resolution checks, but its public surface
is still mostly lookup wrappers and single-metric helpers. The fractal scanner
currently reports the module at depth 1 (`10/14 trivial, 4 real`): callers can
ask for a rule or a dissonance report, but they cannot get a complete,
operator-readable assessment that combines motion, role compatibility,
arc-phase affinity, preferred intervals, leap safety, and resolution quality.

The task is to deepen the module to a simple depth-2 implementation: one
straightforward analysis path that turns a two-voice MIDI pair into meaningful
motion metrics, rule-fit scores, a ranked recommendation, and a stable summary
dictionary. Existing registry behavior, dissonance APIs, and tracker metadata
wiring must keep working.

## Technical Approach

Extend `counterpoint_rules.py` in place with typed, pure helpers:

- `MotionProfile` frozen dataclass with transition counts for parallel,
  contrary, oblique, and static motion, plus `dominant_motion` and
  `stepwise_rate`.
- `CounterpointFit` frozen dataclass with the selected rule id, roles, phase,
  score, pass/fail flag, preferred-interval rate, leap-safety rate, motion-match
  rate, and embedded `MotionProfile` / `DissonanceReport` values.
- `motion_profile(leader_notes, follower_notes)` pairs the two sequences by
  min length and classifies each transition from MIDI deltas.
- `score_counterpoint_fit(relationship_id, leader_notes, follower_notes, *,
  leader_role, follower_role, phase)` resolves the rule and computes one
  weighted score from voice-pair compatibility, phase affinity, dominant motion,
  preferred vertical intervals, leap safety, and dissonance resolution.
- `rank_counterpoint_rules(leader_notes, follower_notes, *, leader_role,
  follower_role, phase)` scores valid rules for the voice pair and returns
  descending `CounterpointFit` rows.
- `recommend_counterpoint_rule(...)` returns the highest-ranked fit.
- `counterpoint_pair_summary(...)` returns a deterministic dictionary suitable
  for diagnostics and end-to-end tests.

The implementation uses only existing `interval_between`,
`analyze_dissonance`, `rules_for_voice_pair`, and registry data. No new
dependencies, migrations, runtime state, provider secrets, or agent commands
are introduced.

## Edge Cases

- Empty or one-note input has zero transitions, `dominant_motion="none"`, and
  `stepwise_rate=1.0`; the scoring path still returns a bounded score.
- Mismatched voice lengths use the already-established min-length pairing
  convention from `analyze_dissonance`.
- If a role pair has no registry match, ranking scores all rules and lets the
  voice-pair compatibility component reduce the score instead of returning no
  recommendation.
- Unknown relationship ids use `resolve_rule`, preserving the existing fallback
  behavior.
- The auto-generated startup identity hardening bullets target the daemon
  startup subsystem, not this pure counterpoint analysis module. Existing
  startup identity tests remain mandatory regression anchors for this task.

## Acceptance Criteria

1. `motion_profile` reports meaningful transition counts, dominant motion, and
   stepwise rate for a two-voice sequence.
   VERIFY: `pytest tests/test_counterpoint_rules_depth.py::test_motion_profile_counts_motion_types -q`

2. `score_counterpoint_fit` returns a `CounterpointFit` that combines the
   existing registry, interval, leap, motion, phase, and dissonance data into a
   bounded score and pass/fail flag.
   VERIFY: `pytest tests/test_counterpoint_rules_depth.py::test_score_counterpoint_fit_combines_registry_and_resolution_metrics -q`

3. `rank_counterpoint_rules` and `recommend_counterpoint_rule` produce a stable
   one-path recommendation for realistic MIDI pairs.
   VERIFY: `pytest tests/test_counterpoint_rules_depth.py::test_recommendation_prefers_contrary_for_contrary_motion_pair -q`

4. `counterpoint_pair_summary` emits a deterministic operator-readable summary
   with rule id, score, pass/fail, motion, resolution, and interval-fit fields.
   VERIFY: `pytest tests/test_counterpoint_rules_depth.py::test_counterpoint_pair_summary_is_stable_and_meaningful -q`

5. Existing counterpoint registry, dissonance, and tracker metadata tests still
   pass.
   VERIFY: `pytest tests/test_counterpoint_rules.py tests/test_counterpoint_pipeline.py -q`

6. Fractal depth for `my-claw/tools/senseweave/counterpoint_rules.py` reaches at
   least depth 2.
   VERIFY: `python - <<'PY'
import sys
sys.path.insert(0, "/Users/anthony/Programming/sdp-cli/src")
from sdp.fractal import classify_depth
result = classify_depth("my-claw/tools/senseweave/counterpoint_rules.py")
print(result.depth, result.reason)
assert result.depth >= 2
PY`

7. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

8. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
