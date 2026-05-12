# Task frac-0077 Specification: test_generation_composer_hook Depth 2

## Problem Statement

`tests/test_generation_composer_hook.py` covers the composer-hook gating
helpers (`_should_queue_now`, `build_generation_request`) and the integration
points on `duet_composer._post_song_generation_hook` through unit-level fakes,
but it does not yet prove the composer-hook surface works end-to-end as one
deterministic path: take a real `mode/mood/learning/clap_centroid/score`
context, exercise the gate decision, the deterministic request builder, the
queue handoff, and the JSON-safe payload that ends up enqueued. The production
module `my-claw/tools/senseweave/generation/composer_hook.py` already exposes
the surface needed for this end-to-end path:

- `_should_queue_now`
- `build_generation_request`
- `MIN_GENERATION_INTERVAL_SECONDS`
- `MIN_DAILY_BUDGET_REMAINING_USD`

The duet-composer integration `_post_song_generation_hook` already wires the
gate, request builder, and queue together. The gap is the locked test surface.

This task deepens the test surface to depth 2 by adding a deterministic
one-path end-to-end test class plus a depth gate. Existing helper assertions
remain unchanged.

## Technical Approach

- Preserve all existing assertions in `tests/test_generation_composer_hook.py`.
- Add a depth gate in `tests/test_test_generation_composer_hook_depth.py`
  requiring `tests/test_generation_composer_hook.py` to contain
  `GenerationComposerHookEndToEndTests` and classify at depth >= 2 via
  `sdp.fractal.classify_depth`.
- Append `GenerationComposerHookEndToEndTests` to the existing composer-hook
  tests. The new tests will drive the existing public API end-to-end through:
  - a happy-path gate -> build -> enqueue cycle that asserts the deterministic
    `request_hash`, `mode_name`, `arc_phase`, `seed`, JSON-safe payload, and
    enqueued idempotency key;
  - a budget/rate gate end-to-end where the gate denies enqueue (low daily
    budget, sampler_dominating antipattern, working_ambience low arc payoff,
    and rate-limited recent enqueue) and `_post_song_generation_hook`
    short-circuits with `None` and no queue traffic;
  - a deterministic-request determinism check across two equal calls and a
    non-equal call (different mode or arc phase) that confirms `request_hash`
    is content-addressed and stable;
  - a JSON-safe payload round-trip via `json.dumps(..., sort_keys=True)`
    of the built request;
  - a duet-composer integration cycle that wires real `_should_queue_now` plus
    the real `build_generation_request` (through a thin conditioner adapter)
    against a `_FakeQueue`, asserting the queue receives the same JSON-safe
    payload the builder produces and the idempotency key matches the request
    hash.
- No new production code is required; the existing composer-hook module
  already exposes the gate constants, gate function, and deterministic builder.
- Treat the generated startup identity hardening checks as regression anchors.
  Existing CLI, daemon, first-boot, and narrative ASGI tests already cover
  `bootstrap_identity()` before `FirstBootAnnouncer` and identity persistence
  across standalone/federated boots, so this task re-runs those anchors
  rather than changing unrelated startup code.

## Edge Cases

- This depth-2 pass intentionally exercises one deterministic happy path plus
  the matching denial paths rather than every invalid request shape.
- `working_ambience` mode under arc payoff `< 0.4` must remain blocked even
  when budget and rate gates allow.
- Sampler-dominating antipatterns surfaced through the `antipatterns` list
  must short-circuit the gate.
- Rate-limit gate uses `MIN_GENERATION_INTERVAL_SECONDS` against the most
  recent enqueue timestamp threaded through the learning payload.
- JSON diagnostics must use only JSON-safe primitives.
- No new dependencies, migrations, provider secrets, database columns,
  runtime state directories, HTTP routes, or auth behavior are introduced.

## Acceptance Criteria

1. Existing composer-hook helper assertions remain green.
   VERIFY: `pytest tests/test_generation_composer_hook.py -q`

2. The new depth gate confirms `tests/test_generation_composer_hook.py`
   reaches depth >= 2 and contains `GenerationComposerHookEndToEndTests`.
   VERIFY: `pytest tests/test_test_generation_composer_hook_depth.py -q`

3. `GenerationComposerHookEndToEndTests` drives the full gate -> build ->
   enqueue, denial paths, determinism, and JSON-safe round-trip cycle through
   the public API.
   VERIFY: `pytest tests/test_generation_composer_hook.py::GenerationComposerHookEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, standalone
   and federated identity persistence, daemon bootstrap-before-announcer
   ordering, and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing notes mention the frac-0077 generation composer-hook
   depth-2 work.
   VERIFY: `grep -n "frac-0077" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
