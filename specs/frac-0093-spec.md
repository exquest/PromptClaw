# Task frac-0093 Specification: test_narrative_api_entities Depth 2

## Problem Statement

`tests/test_narrative_api_entities.py` covers the CypherClaw narrative API
world-entity HTTP surface at focused endpoint level: listing, single-entity
fetching, creation, mutation, domain filtering, auth failures, validation
failures, and downstream store errors. The missing frac-0093 work is to make
the depth-2 contract explicit for this test module.

The affected production code in `src/cypherclaw/narrative_api/entities.py`,
`app.py`, and `schemas.py` already implements the simple one-path entity
contract required by the narrative HTTP PRD: a client can create a Deniable
entity, mutate its properties, fetch it by ID, and list it through the
domain/type filtered endpoint. This task therefore starts as test hardening:
add a deterministic depth gate plus a named end-to-end class that drives one
meaningful public lifecycle through the existing HTTP API.

The generated startup identity hardening bullets target the existing identity
startup subsystem. This checkout already documents and tests CLI startup,
daemon bootstrap-before-`FirstBootAnnouncer` ordering, standalone/federated
identity persistence, and narrative ASGI import persistence. This task keeps
those tests as mandatory regression anchors rather than modifying unrelated
startup code without a discovered gap.

## Technical Approach

- Add `tests/test_test_narrative_api_entities_depth.py` with a deterministic
  depth gate requiring `tests/test_narrative_api_entities.py` to contain
  `NarrativeApiEntitiesEndToEndTests` and classify at depth >= 2 through the
  repo-local `sdp.fractal.classify_depth`.
- Confirm the red phase by running the new depth gate before the end-to-end
  class exists.
- Append `NarrativeApiEntitiesEndToEndTests` to
  `tests/test_narrative_api_entities.py`.
- Drive one public HTTP lifecycle inside the class:
  - create a Deniable character entity through `POST /world/entities`;
  - patch that same entity through `PATCH /world/entities/{entity_id}` using
    set, increment, append, and nested set mutations;
  - fetch it back through `GET /world/entities/{entity_id}`;
  - list Deniable-visible characters through `GET /world/entities` and confirm
    shared plus deniable records are visible while unrelated domains/types are
    excluded;
  - serialize a combined diagnostic payload through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)` to prove the
    lifecycle output is JSON-safe.
- Preserve the existing focused assertions and production behavior unless the
  red test exposes a concrete gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path intentionally covers one simple happy path through the
  world-entity API, not every invalid field path, alternate store signature,
  auth failure, or downstream failure. Existing focused tests remain
  responsible for those branches.
- The domain list step verifies the intended Deniable view (`deniable` plus
  `shared`) while preserving type filtering.
- The diagnostic payload must stay JSON-safe without custom encoders so
  downstream reports can persist it.
- Startup identity hardening remains covered by the existing CLI, first-boot,
  daemon-ordering, and narrative ASGI tests.

## Acceptance Criteria

1. Existing narrative entity assertions remain green.
   VERIFY: `pytest tests/test_narrative_api_entities.py -q`

2. The depth gate confirms `tests/test_narrative_api_entities.py` reaches
   depth >= 2 and contains `NarrativeApiEntitiesEndToEndTests`.
   VERIFY: `pytest tests/test_test_narrative_api_entities_depth.py -q`

3. `NarrativeApiEntitiesEndToEndTests` drives one meaningful public lifecycle
   from create through patch, get, list, and JSON-safe diagnostics.
   VERIFY: `pytest tests/test_narrative_api_entities.py::NarrativeApiEntitiesEndToEndTests -q`

4. Existing narrative API memory, event, beat, health, and main-entry behavior
   remains green.
   VERIFY: `pytest tests/test_narrative_api_entities.py tests/test_narrative_api_events.py tests/test_narrative_api_memory.py tests/test_narrative_api_beats.py tests/test_narrative_api_health.py tests/test_narrative_api_main.py -q`

5. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing task notes mention the frac-0093 narrative entity test
   deepening.
   VERIFY: `grep -n "frac-0093" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
