# Task frac-0094 Specification: test_narrative_api_health Depth 2

## Problem Statement

`tests/test_narrative_api_health.py` covers the CypherClaw narrative API
`/health` endpoint at focused level: it asserts the healthy "ok" response with
all subsystem statuses true and the world-store "list_events" probe call, plus
one degraded path where the world store raises and the ollama checker returns
false. The missing frac-0094 work is to make the depth-2 contract explicit for
this test module: a deterministic depth gate plus a named end-to-end class
that drives one meaningful public health-probe lifecycle through the existing
HTTP API.

The affected production code in `src/cypherclaw/narrative_api/app.py` already
implements the simple one-path health contract required by the narrative HTTP
PRD: a client can hit `/health` and receive a JSON body that combines a
top-level `status`, the three subsystem booleans, the app `version`, and a
monotonic `uptime_seconds`. This task therefore starts as test hardening: the
existing focused assertions already pass, so the new end-to-end class extends
coverage to a single realistic health-probe sequence (cold probe, repeated
probe with elapsed uptime, degraded probe with one failing subsystem) and a
JSON-safe diagnostic round trip.

The generated startup identity hardening bullets target the existing identity
startup subsystem. This checkout already documents and tests CLI startup,
daemon bootstrap-before-`FirstBootAnnouncer` ordering, standalone/federated
identity persistence, and narrative ASGI import persistence. This task keeps
those tests as mandatory regression anchors rather than modifying unrelated
startup code without a discovered gap.

## Technical Approach

- Add `tests/test_test_narrative_api_health_depth.py` with a deterministic
  depth gate requiring `tests/test_narrative_api_health.py` to contain
  `NarrativeApiHealthEndToEndTests` and classify at depth >= 2 through the
  repo-local `sdp.fractal.classify_depth`.
- Confirm the red phase by running the new depth gate before the end-to-end
  class exists.
- Append `NarrativeApiHealthEndToEndTests` to
  `tests/test_narrative_api_health.py`.
- Drive one public HTTP health-probe lifecycle inside the class:
  - hit `GET /health` with all subsystem checkers reporting healthy and an
    `auth_token` set (the route is intentionally open) and confirm the body
    returns `status="ok"`, all three subsystem booleans true, the
    `version="0.1.0"` constant, a non-negative `uptime_seconds`, and that the
    world-store probe ran exactly one `list_events` call with
    `since_event_id=None`, `domain_filter=None`, `limit=1`;
  - hit `GET /health` a second time after a short wait and confirm
    `uptime_seconds` is monotonic and a second world-store probe was issued;
  - hit `GET /health` against a degraded app where the world store raises and
    the ollama checker returns false, confirming `status="degraded"`,
    `world_db_reachable=False`, `ollama_reachable=False`, and
    `narrative_engine_importable=True`;
  - serialize the combined diagnostic payload through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)` to prove the
    health-probe lifecycle output is JSON-safe.
- Preserve the existing focused assertions and production behavior unless the
  red test exposes a concrete gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path intentionally covers one simple happy probe path plus a
  single degraded subsystem mix, not every failure-mode permutation, alternate
  health checker signature, or ollama-only outage. Existing focused tests
  remain responsible for those branches.
- The `auth_token` argument is included on the healthy app to confirm the
  `/health` route is intentionally open (no `X-Narrative-Auth` header sent).
- The `uptime_seconds` assertion is non-negative and monotonic between probes
  rather than a fixed value, so the test stays deterministic without freezing
  time.
- The diagnostic payload must stay JSON-safe without custom encoders so
  downstream reports can persist it.
- Startup identity hardening remains covered by the existing CLI, first-boot,
  daemon-ordering, and narrative ASGI tests.

## Acceptance Criteria

1. Existing narrative health assertions remain green.
   VERIFY: `pytest tests/test_narrative_api_health.py -q`

2. The depth gate confirms `tests/test_narrative_api_health.py` reaches
   depth >= 2 and contains `NarrativeApiHealthEndToEndTests`.
   VERIFY: `pytest tests/test_test_narrative_api_health_depth.py -q`

3. `NarrativeApiHealthEndToEndTests` drives one meaningful public
   health-probe lifecycle from healthy probe through repeated probe, degraded
   probe, and JSON-safe diagnostics.
   VERIFY: `pytest tests/test_narrative_api_health.py::NarrativeApiHealthEndToEndTests -q`

4. Existing narrative API memory, event, beat, entity, and main-entry behavior
   remains green.
   VERIFY: `pytest tests/test_narrative_api_entities.py tests/test_narrative_api_events.py tests/test_narrative_api_memory.py tests/test_narrative_api_beats.py tests/test_narrative_api_health.py tests/test_narrative_api_main.py -q`

5. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing task notes mention the frac-0094 narrative health test
   deepening.
   VERIFY: `grep -n "frac-0094" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
