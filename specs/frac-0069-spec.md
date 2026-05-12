# Task frac-0069 Specification: test_counterpoint_rules Depth 2

## Problem Statement

`tests/test_counterpoint_rules.py` is the regression suite for the
SenseWeave counterpoint relationship registry and depth-2 helpers in
`my-claw/tools/senseweave/counterpoint_rules.py`. The production module
already implements the one-path runtime contract: a six-rule registry
keyed on relationship id, leader/follower role queries, phase-affinity
selection, fallback resolution, dissonance metadata, voice-leading
smoothness, motion classification, and counterpoint-fit ranking with a
stable diagnostic summary.

The requested affected surface is the test file itself. This task
deepens the rules test from depth 1 to depth 2 by appending an
end-to-end class that drives the existing public registry surface
through complete scoring + recommendation paths and pins the file at
fractal depth >= 2 with a dedicated red-phase depth gate.

## Technical Approach

- Preserve every existing test class and assertion in
  `tests/test_counterpoint_rules.py`. No production code change is
  required and `my-claw/tools/senseweave/counterpoint_rules.py` source
  stays unchanged.
- Add a dedicated red-phase depth gate at
  `tests/test_test_counterpoint_rules_depth.py` that requires
  `tests/test_counterpoint_rules.py` to classify at depth >= 2 and to
  contain the new `CounterpointRulesEndToEndTests` class. This mirrors
  the depth-gate pattern introduced for `tests/test_constitution.py`
  and `tests/test_contact_mic_calibration_runtime.py`.
- Append `CounterpointRulesEndToEndTests` to
  `tests/test_counterpoint_rules.py` using pytest style. The new class
  drives the public registry API end-to-end through scenarios covering:
  - per-phase best-rule resolution against the documented expectations
    for every required arc phase, with affinity bounded in [0, 1];
  - leader/follower voice-pair queries, intersection with
    `rules_for_voice_pair`, and unknown-role empty-result handling;
  - `resolve_rule` fallback chains for known, alias, and unknown ids,
    confirming every fallback target is itself a registered rule;
  - dissonance + resolution analysis on a realistic
    melody/bass excerpt, asserting annotation count, sharp-dissonance
    counts, resolution rate, and JSON-safe annotation payloads;
  - motion classification for contrary, parallel, oblique, static and
    mixed sequences with stepwise-rate verification;
  - `score_counterpoint_fit` and `rank_counterpoint_rules` over a
    contrary-motion voice pair confirming `contrary` ranks first, the
    score is in [0, 1], `passed` is true, and `recommend_counterpoint_rule`
    returns the same fit as the top of the ranking;
  - `counterpoint_pair_summary` payload shape, key set, JSON
    round-trip, and consistency with the underlying
    `CounterpointFit` fields;
  - registry coverage equality with `REQUIRED_RELATIONSHIPS` and
    `REQUIRED_PHASES` across every rule.
- Each new scenario method exercises load → analyze → recommend through
  the production API with at least four statements (or a control-flow
  construct) so the fractal classifier counts it as real-logic, keeping
  the file at depth >= 2.
- All changes remain stdlib-only. No migrations, dependencies, runtime
  state files, secrets, HTTP routes, or auth behavior are introduced.
- Treat the auto-generated startup identity hardening bullets as
  regression anchors: bootstrap-before-`FirstBootAnnouncer` ordering,
  standalone/federated identity persistence, CLI startup invocation,
  and ASGI app import persistence are already covered. Re-run those
  anchors to confirm no regression.

## Edge Cases

- The depth gate asserts `depth >= 2` rather than an exact reason, so
  future improvements (real test discovery boosting depth further)
  remain compatible.
- Existing `TestRegistryCompleteness`, `TestEntryFields`,
  `TestArcPhaseAffinity`, `TestVoicePairQueries`, `TestLookups`,
  `TestIntervalConstraints`, `TestImmutability`,
  `TestVerificationAndScoring`, and `TestDissonanceMetadata` classes
  remain untouched; new coverage is appended in a separate class so the
  locked assertions are not modified.
- Unknown roles and unknown relationship ids must not raise; the
  production module returns empty results or the parallel fallback,
  and the new tests pin that behavior.
- Sequences with mismatched lengths and single notes are exercised
  through `motion_profile` and `analyze_dissonance` to confirm both
  branches return safe defaults.
- The `counterpoint_pair_summary` payload is asserted to be JSON-safe
  via a `json.dumps` round-trip so future regressions cannot pass by
  returning non-serializable Python objects.

## Acceptance Criteria

1. Existing counterpoint_rules tests remain unchanged and green.
   VERIFY: `pytest tests/test_counterpoint_rules.py::TestRegistryCompleteness tests/test_counterpoint_rules.py::TestEntryFields tests/test_counterpoint_rules.py::TestArcPhaseAffinity tests/test_counterpoint_rules.py::TestVoicePairQueries tests/test_counterpoint_rules.py::TestLookups tests/test_counterpoint_rules.py::TestIntervalConstraints tests/test_counterpoint_rules.py::TestImmutability tests/test_counterpoint_rules.py::TestVerificationAndScoring tests/test_counterpoint_rules.py::TestDissonanceMetadata -q`

2. The new depth gate confirms `tests/test_counterpoint_rules.py`
   reaches at least depth 2 and contains
   `CounterpointRulesEndToEndTests`.
   VERIFY: `pytest tests/test_test_counterpoint_rules_depth.py -q`

3. The new end-to-end class covers per-phase best-rule resolution,
   voice-pair queries, fallback chains, dissonance + resolution
   analysis, motion classification, `score_counterpoint_fit` /
   `rank_counterpoint_rules` / `recommend_counterpoint_rule`,
   `counterpoint_pair_summary` JSON round-trip, and registry coverage
   equality with `REQUIRED_RELATIONSHIPS` and `REQUIRED_PHASES`.
   VERIFY: `pytest tests/test_counterpoint_rules.py::CounterpointRulesEndToEndTests -q`

4. The counterpoint_rules production module remains
   behavior-compatible with downstream consumers.
   VERIFY: `pytest tests/test_counterpoint_rules.py tests/test_counterpoint_rules_depth.py tests/test_counterpoint_pipeline.py -q`

5. Startup identity hardening remains covered for first-run identity
   persistence, standalone/federated reuse, CLI startup invocation,
   bootstrap-before-announcer ordering, and ASGI app import
   persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing progress and changelog notes mention the depth-2
   counterpoint_rules test coverage.
   VERIFY: `grep -n "frac-0069" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
