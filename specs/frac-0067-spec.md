# Task frac-0067 Specification: test_constitution Depth 2

## Problem Statement

`tests/test_constitution.py` is the regression suite for the coherence
engine's constitutional rule loader and evaluator
(`promptclaw/coherence/constitution.py`). The production module already
classifies at depth 3 — it loads JSON/YAML rules, filters by phase and
agent, evaluates text via regex and keyword matching, exposes
hard/soft/phase accessors, and decides blocking under the three
`EnforcementMode` values.

The gap is the requested affected surface itself:
`sdp.fractal.classify_depth("tests/test_constitution.py")` reports depth 1
(`28/31 trivial, 3 real`) because the existing tests are short
single-method smoke checks. This task deepens the test file to a simple
depth-2 end-to-end suite without changing any existing assertions or
production behavior.

## Technical Approach

- Preserve every existing test class and assertion in
  `tests/test_constitution.py`. No production code change is required.
- Add a dedicated red-phase depth gate at
  `tests/test_test_constitution_depth.py` that requires
  `tests/test_constitution.py` to classify at depth >= 2 and to contain
  the new `ConstitutionEndToEndTests` class. This mirrors the
  depth-gate pattern introduced for `tests/test_config.py`.
- Append `ConstitutionEndToEndTests` to `tests/test_constitution.py`
  using the existing `unittest` style. The new class drives the public
  `Constitution` API end-to-end through scenario tests covering: JSON
  rule loading, missing/None path fallback, malformed payload tolerance,
  unknown-suffix JSON fallback, regex matching, keyword matching with
  case-insensitive comparison, combined pattern + keywords on a single
  rule, phase and agent filtering (active and inactive), phase- and
  agent-agnostic rule fan-out, message vs description fallback,
  `hard_rules` / `soft_rules` / `rules_for_phase` filtering, and the
  full evaluate → should_block pipeline under each `EnforcementMode`.
- Each new scenario method exercises load → evaluate → block-decision
  through the production API with at least four statements (or a
  control-flow construct) so the fractal classifier counts it as
  real-logic, flipping the file from `trivial > real` to `real >=
  trivial` and reaching depth >= 2.
- All changes remain stdlib-only. No migrations, dependencies, runtime
  state files, secrets, or orchestration changes are introduced.
- Treat the auto-generated startup identity hardening bullets as
  regression anchors: bootstrap-before-`FirstBootAnnouncer` ordering,
  standalone/federated identity persistence, CLI startup invocation,
  and ASGI app import persistence are already covered. Re-run those
  anchors to confirm no regression.

## Edge Cases

- The depth gate asserts `depth >= 2` rather than an exact reason, so
  future improvements (e.g., real test discovery boosting depth further)
  remain compatible.
- Existing `TestConstitutionLoading`, `TestConstitutionEvaluate`,
  `TestConstitutionHelpers`, and `TestShouldBlock` classes are left
  untouched; new coverage is appended in a separate class so the locked
  assertions are not modified.
- Malformed JSON and unknown suffixes must not raise; the production
  module returns an empty rule set, and the new tests pin that
  behavior.
- Rules with empty `applies_to_phases` / `applies_to_agents` must
  match every phase and agent, including the empty defaults used when
  callers do not pass those arguments.
- The `evaluate` path is exercised both with and without phase/agent
  arguments to confirm both branches of the filter remain green.

## Acceptance Criteria

1. Existing constitution tests remain unchanged and green.
   VERIFY: `pytest tests/test_constitution.py::TestConstitutionLoading tests/test_constitution.py::TestConstitutionEvaluate tests/test_constitution.py::TestConstitutionHelpers tests/test_constitution.py::TestShouldBlock -q`

2. The new depth gate confirms `tests/test_constitution.py` reaches at
   least depth 2 and contains `ConstitutionEndToEndTests`.
   VERIFY: `pytest tests/test_test_constitution_depth.py -q`

3. The new end-to-end class covers JSON load, missing/None fallback,
   malformed/unknown-suffix tolerance, regex and keyword matching
   (including case-insensitive), phase/agent filtering, message vs
   description fallback, `hard_rules` / `soft_rules` /
   `rules_for_phase`, and the full evaluate → should_block pipeline
   under each `EnforcementMode`.
   VERIFY: `pytest tests/test_constitution.py::ConstitutionEndToEndTests -q`

4. The constitution production module remains behavior-compatible with
   downstream consumers.
   VERIFY: `pytest tests/test_constitution.py tests/test_coherence_engine.py tests/test_coherence_integration.py -q`

5. Startup identity hardening remains covered for first-run identity
   persistence, standalone/federated reuse, CLI startup invocation,
   bootstrap-before-announcer ordering, and ASGI app import
   persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing progress and changelog notes mention the depth-2
   constitution test coverage.
   VERIFY: `grep -n "frac-0067" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
