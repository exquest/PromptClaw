# Task frac-0065 Specification: test_coherence_engine Depth 2

## Problem Statement

`tests/test_coherence_engine.py` owns the compact regression coverage for
`promptclaw/coherence/engine.py`, the orchestrator-facing facade for the
PromptClaw coherence engine. The current test file classifies as fractal
**depth 1** (`10/16 trivial, 6 real`): most tests are 1–3 statement assertions
that confirm a hook returned an approved verdict, while only a handful of
methods exercise multi-step real logic (event replay, sequence increment,
multi-hook emission). The coherence facade itself is mature — `pre_routing`,
`pre_lead`, `pre_verify` already inject decision and constitutional context;
`post_routing`, `post_lead`, `post_verify` already evaluate the constitution,
update trust, and decide on blocking; `finalize` already steps the graduation
manager — but the test file's existing assertions only confirm the no-rule
default path. This task lifts `tests/test_coherence_engine.py` to fractal
**depth ≥ 2** by appending a new end-to-end class that drives the existing
public facade through a complete run lifecycle and exercises the documented
real-logic paths (constitution-driven blocking, trust deltas, decision
injection, graduation step) without changing any production behavior.

## Technical Approach

- Preserve `promptclaw/coherence/engine.py` behavior. The source already
  provides meaningful end-to-end output and needs no planned production
  change. All new coverage drives the existing public surface.
- Add a dedicated test-file depth gate at
  `tests/test_test_coherence_engine_depth.py`. The gate parses
  `tests/test_coherence_engine.py` with `ast` and asserts that the new
  `TestCoherenceEngineEndToEnd` class is present and that
  `classify_depth("tests/test_coherence_engine.py").depth >= 2`. This pins the
  red-phase signal even after the depth shifts past 1.
- Append `TestCoherenceEngineEndToEnd` to `tests/test_coherence_engine.py`.
  All new methods use looped or table-driven assertions with control flow so
  the fractal classifier records them as real logic rather than trivial
  one-call checks.
- Drive simple end-to-end paths through the existing public API:
  - Walk every hook in canonical order
    (`pre_routing → post_routing → pre_lead → post_lead → pre_verify
    → post_verify → finalize`) and verify that the recorded event sequence
    spans the full lifecycle, has monotonically increasing
    `sequence_number`s, carries the documented `phase`/`agent` metadata, and
    persists across an `engine` rebuild (replay returns the same events from
    SQLite).
  - Drive the constitution-violation path end-to-end: write a
    `constitution.json` containing one HARD and one SOFT keyword rule, build
    a fresh engine in `EnforcementMode.FULL`, and confirm
    `post_routing`/`post_lead`/`post_verify` return non-approved verdicts
    with the matching `Violation.rule_id`s, that `trust_delta` becomes
    negative on offending agents, and that the bypassed approval flips to
    `True` in `EnforcementMode.MONITOR`.
  - Drive the decision-injection path end-to-end: record two architectural
    decisions through `record_decision`, then call `pre_routing` /
    `pre_lead` / `pre_verify` with task text that overlaps each decision's
    title or context and confirm the verdict's `injected_context` includes
    the decision title and the formatted constitutional preamble when both
    are present.
  - Drive the graduation/finalize path: run several finalize calls and
    confirm `record_graduation_observation` plus `finalize` step the
    graduation manager's run counter, leaving the engine's enforcement mode
    deterministic across calls.
  - Round-trip a replayed event payload through `json.dumps` to confirm the
    event store output is JSON-safe.
- Exercise `NullCoherenceEngine` end-to-end via a loop that invokes every
  hook with multiple run ids and confirms the verdict shape stays in the
  approved/empty-context state and `replay` stays empty for any id.
- Keep the change stdlib-only. No new dependencies, migrations, runtime
  state files, database columns, HTTP routes, auth changes, or environment
  variables are required.
- Treat the generated startup hardening bullets as mandatory verification
  anchors. Existing startup identity tests cover `bootstrap_identity()`
  persistence, standalone/federated reuse, CLI startup invocation,
  bootstrap-before-`FirstBootAnnouncer` ordering, and ASGI app import
  persistence; those tests are re-run as part of this task's verification.

## Edge Cases

- The depth gate asserts `depth >= 2` rather than an exact depth or reason
  so later test improvements remain compatible.
- Existing tests and assertions in `tests/test_coherence_engine.py` remain
  unchanged; the new coverage is appended in a separate
  `TestCoherenceEngineEndToEnd` class.
- Constitution evaluation depends on either the optional `yaml` package or
  a `.json` extension. The new tests write a `.json` constitution file so
  the path remains stable in environments without PyYAML.
- The trust manager mutates internal state on every call, so each scenario
  builds its own fresh engine and temp directory to avoid cross-test
  contamination.
- The decision store uses a SQLite connection per engine instance; the new
  tests close the engine's stores between rebuilds to avoid Windows-style
  file locks (no-op on Darwin/Linux but defensive for CI).
- The graduation/finalize path stays deterministic: thresholds are not
  crossed in the test, so enforcement mode does not flip.
- No startup identity source changes are expected because the existing tree
  already has dedicated regression anchors for the generated hardening
  items.

## Acceptance Criteria

1. Existing coherence-engine behavioral tests remain unchanged and green.
   VERIFY: `pytest tests/test_coherence_engine.py -q`

2. The new red-phase depth gate confirms `tests/test_coherence_engine.py`
   reaches at least depth 2 and contains the new end-to-end class.
   VERIFY: `pytest tests/test_test_coherence_engine_depth.py -q`

3. The new end-to-end class drives the full hook lifecycle, constitutional
   blocking and trust deltas, decision-injection prompts, graduation/finalize
   stepping, JSON-safe replay, and a `NullCoherenceEngine` smoke loop from
   the existing public API.
   VERIFY: `pytest tests/test_coherence_engine.py::TestCoherenceEngineEndToEnd -q`

4. The production coherence-engine source remains unchanged in behavior and
   still works through the public API.
   VERIFY: `python -c "import shutil, tempfile; from pathlib import Path; from promptclaw.coherence.engine import CoherenceEngine; from promptclaw.coherence.models import CoherenceConfig; tmp=Path(tempfile.mkdtemp(prefix='frac-0065-smoke-')); (tmp/'.promptclaw').mkdir(); engine=CoherenceEngine(CoherenceConfig(), tmp); engine.pre_routing('run-1','task','memory'); engine.post_routing('run-1', {'lead_agent':'claude'}); engine.pre_lead('run-1','claude','task'); engine.post_lead('run-1','claude','output'); engine.pre_verify('run-1','codex','lead'); engine.post_verify('run-1','codex','PASS'); engine.finalize('run-1'); events=engine.replay('run-1'); assert len(events)==7 and [e.sequence_number for e in events]==list(range(7)); shutil.rmtree(tmp); print('OK', len(events))"`

5. Startup identity hardening remains covered for first-run identity
   persistence, standalone/federated reuse, CLI startup invocation,
   bootstrap-before-announcer ordering, and ASGI app import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing progress and changelog notes mention the depth-2
   coherence-engine test coverage.
   VERIFY: `grep -n "frac-0065" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
