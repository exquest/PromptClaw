# Task frac-0038 Specification: Trust Manager Depth 2

## Problem Statement

`promptclaw/coherence/trust.py` owns the per-agent `TrustScore` and
`TrustManager` used by `CoherenceEngine` to track trust deltas across hard
violations, soft violations, and compliant actions. Existing tests verify the
current penalty/reward values, clamping, restriction threshold, and per-agent
isolation.

The module currently classifies at fractal depth 1 (`5/9 trivial, 4 real`)
because most public methods are short single-path mutations. This task
deepens the module to a simple depth-2 implementation by adding one typed
canonical-plan path that turns the implicit penalty/reward table into
inspectable typed data and produces an operator-readable trust summary, while
preserving the current TrustManager surface and constants used by
`CoherenceEngine`.

## Technical Approach

Extend `promptclaw/coherence/trust.py` in place with stdlib-only helpers.

- Add a frozen `TrustEventPlan` dataclass describing one canonical trust event
  with `name`, `delta`, `counter_field`, and `description`.
- Add `trust_event_plans()` returning the canonical three-event tuple
  (`hard_violation`, `soft_violation`, `compliant_action`) sourced from the
  existing `TrustManager` constants.
- Add `TrustManager.apply_event(agent, plan)` that routes any plan through one
  shared mutation path: clamp the score, increment the named counter, touch
  the timestamp, and return the new score.
- Route `apply_hard_violation`, `apply_soft_violation`, and
  `apply_compliant_action` through `apply_event` using the canonical plans so
  existing penalty/reward semantics are preserved.
- Add `TrustManager.fleet_summary()` returning a JSON-safe operator summary
  with the configured constants, restriction threshold, per-agent score
  table sorted by agent name, and the count of restricted agents.
- Do not add dependencies, runtime files, provider secrets, database tables,
  agent command strings, or new public constants beyond the canonical plan.

## Edge Cases

- Existing penalty/reward values (`HARD_PENALTY`, `SOFT_PENALTY`,
  `COMPLIANT_REWARD`) and the `RESTRICTION_THRESHOLD` must remain unchanged
  so that `CoherenceEngine` callers continue to read the same constants.
- Score clamping to `[0.0, 1.0]` must remain in place when applying a plan.
- Counter increments must hit the field named on the plan even if a future
  plan introduces an unknown counter — unknown counter names must raise
  `ValueError` with the offending name so the canonical table stays the
  single source of truth.
- `fleet_summary()` on an empty manager must return zero restricted agents
  and an empty score table, not raise.
- `fleet_summary()` must list agents in deterministic alphabetical order so
  operator surfaces and logs stay diff-stable.
- The summary is diagnostic only; trust authority remains the
  `TrustManager.apply_*` methods consulted by `CoherenceEngine`.
- Startup identity hardening is not changed by this task; existing tests
  verify first-boot persistence and bootstrap-before-announcer ordering.

## Acceptance Criteria

1. Existing `TrustManager` and `TrustScore` behavior remains unchanged for
   penalty values, clamping, restriction threshold, multi-agent isolation,
   and counter increments.
   VERIFY: `pytest tests/test_trust.py -q`

2. The trust module exposes a typed canonical plan for the three trust
   events sourced from existing constants.
   VERIFY: `pytest tests/test_trust_depth.py::test_trust_event_plans_describe_canonical_events -q`

3. `TrustManager.apply_event` routes any canonical plan through one shared
   mutation path that clamps, increments the named counter, and returns the
   new score.
   VERIFY: `pytest tests/test_trust_depth.py::test_apply_event_routes_through_canonical_plan -q`

4. `apply_hard_violation`, `apply_soft_violation`, and `apply_compliant_action`
   are routed through `apply_event` and remain behaviorally identical.
   VERIFY: `pytest tests/test_trust_depth.py::test_legacy_apply_methods_route_through_apply_event -q`

5. `fleet_summary()` returns a JSON-safe operator summary with the
   configured constants, restriction threshold, restricted agent count, and
   alphabetically-ordered per-agent score rows.
   VERIFY: `pytest tests/test_trust_depth.py::test_fleet_summary_is_json_safe_and_sorted -q`

6. Unknown counter names on a plan raise `ValueError` so the canonical table
   stays the single source of truth.
   VERIFY: `pytest tests/test_trust_depth.py::test_apply_event_rejects_unknown_counter_field -q`

7. Fractal depth for `promptclaw/coherence/trust.py` reaches at least
   depth 2.
   VERIFY: `pytest tests/test_trust_depth.py::test_trust_module_reaches_depth_two -q`

8. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
