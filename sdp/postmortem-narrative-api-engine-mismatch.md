# Post-mortem: narrative_api wrapper shipped against fictional engine API

**Date:** 2026-05-03
**Severity:** Service-degraded — every endpoint except `/health` returned 503/500
**Discovered:** During post-deploy smoke test (2026-05-03 ~16:00 PDT)
**Resolved:** Same session via Path 2 rewrite (`engine_container.py` adapter)

## What happened

The Cypherclaw Narrative-Engine HTTP Service PRD had **16 tasks (T-001 through T-015)**, all marked PASS by the SDP runner, all with verification reports. The wrapper was deployed to cypherclaw and started cleanly. But every meaningful endpoint failed:

- `/world/entities`, `/events`: `cypherclaw.narrative.events.NarrativeEventStore is not importable`
- `/memory/search`: `NarrativeMemory.__init__() missing 1 required positional argument: 'world'`
- `/memory/search` (after first fix): `NarrativeMemory exposes no semantic_search, search, or query method`

The wrapper imported and called classes / methods that don't exist in the live `cypherclaw.narrative` engine:

| Wrapper expected | Engine actually has |
|---|---|
| `cypherclaw.narrative.events.NarrativeEventStore` | nothing — no `events` submodule |
| `NarrativeMemory()` (no args) | `NarrativeMemory(world, ollama_url=..., embed_model=..., timeout=30.0)` |
| `memory.semantic_search` / `search` / `query` | `memory.retrieve_similar_beats(query, top_k=5)` |
| `store.create_entity` | `WorldState.upsert_entity(entity_id, entity_type, name, data)` |
| `store.list_events` | `WorldState.get_recent_events(limit)` |

## Why every test passed

The SDP plan's **Risk Register** (PRD line 131) explicitly anticipated this:

> "Engine in-process method signatures don't match endpoint expectations | Medium | Medium | Each endpoint test includes a real engine call; signature mismatch caught at test time"

But the test suite that the runner produced **mocked the engine** — every test injected a `Mock()` standing in for `NarrativeEventStore` / `NarrativeMemory`, so every test green-lit a fictional API surface. The mitigation listed in the risk register (real engine calls in tests) was never enforced by the verifier.

`pytest cypherclaw/src/cypherclaw/narrative_api/tests/` ran clean against the mocks. The wrapper's `build_default_event_store()` / `build_default_memory()` / `build_default_narrative_engine()` were defensive enough to lazy-import — so even import errors only surfaced at first request, not at start-up. The systemd unit's `Type=simple` plus `Restart=on-failure` meant a healthy-looking service was reachable. Operator (me) declared the deploy done because the boxes were green.

## What we changed

1. **`engine_container.py`** — singleton `WorldState` + `NarrativeEngine` + `NarrativeMemory(world=...)` builders, plus `WorldStateAdapter` and `NarrativeMemoryAdapter` exposing the duck-typed names the wrapper looks for.
2. **`build_default_event_store()`**, **`build_default_memory()`**, **`build_default_narrative_engine()`** rewritten to delegate to the container.
3. **CN-001 migration** applied to live DB (additive `domain` column on `events` and `entities` tables — was specced and marked PASS but never ran on `/home/user/.promptclaw/narrative.db`).
4. **Resource-limits dropin** added (MemoryHigh=1G, MemoryMax=1.5G, TasksMax=200).
5. **Integration smoke test** added (`tests/test_narrative_api_smoke.py`) that hits the real running service over Tailscale with a real bearer token — fails loudly if the engine surface drifts again.

## Lessons

1. **A mock-only test suite for a wrapper service is a CN-014 anti-pattern.** Wrappers exist precisely because of an API boundary; the test suite must exercise the real boundary or the boundary is unverified. Add a non-mocked "engine surface contract" test class in any future wrapper SDP plan.

2. **CN-001 migration verification was rubber-stamped.** T-007 marked PASS without anyone running `PRAGMA table_info(events)` against the live database. Add to verifier checklist: "for any task that touches schema, the verifier must read the live schema and confirm the change."

3. **Lazy-imports hide deploy-time bugs.** The wrapper's `importlib.import_module(...)` inside `build_default_*` was defensive design — it prevented service start-up from blowing up. But it also delayed the failure to first-request, which made the service look healthy until traffic hit it. Add a startup self-check that calls each `build_default_*` and logs a warning (or failure) if the underlying engine isn't usable.

4. **The "wraps existing engine" PRD pattern is high-risk for stale-engine-reference bugs.** The PRD said "the engine is stable" (line 142). It was *stable* but its surface had drifted from the assumed-by-spec shape. For any future wrapper PRD, the spec must include a captured snapshot of the engine surface (current method signatures) — and the verifier must confirm those signatures still match before approving each task.

## Action items

- [x] Path-2 rewrite landed (`engine_container.py`)
- [x] CN-001 migration applied
- [x] Memory limit dropin
- [x] Integration smoke test (`tests/test_narrative_api_smoke.py`)
- [ ] Update SDP fractal/template for "wrapper" tasks to enforce the integration-test pattern (future SDP work; not blocking)
- [ ] Add a capture-engine-surface helper to the SDP setup phase that snapshots `inspect.signature` on the target classes into the spec doc (future SDP infra; not blocking)
