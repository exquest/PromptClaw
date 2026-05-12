# Cypherclaw Narrative-Engine HTTP Service PRD (PromptClaw queue addendum) — Implementation Plan

**Generated:** 2026-05-02T00:13:47.318462+00:00
**Source:** PRD v1.0
**Total tasks:** 16
**Estimated effort:** ~66 hours

---

## Execution Order

Sprints are sequential. Tasks within a sprint can run in parallel unless a dependency is noted.

### Sprint 1: Versioning System

**Depends on:** Sprint 0 (Versioning System)

- **T-001** [T2] `POST /memory/search` — wraps `NarrativeMemory` semantic search; accepts `{query, k, domain_filter}`, returns ranked results (~6h)
- **T-002** [T1] `GET /events?since_event_id=…&domain=…` — paginated event log read; supports incremental tail-reading from a known event ID (~3h)
- **T-003** [T2] `POST /events` — append a narrative event to the world state event log; used by Deniable to record raid outcomes that should propagate via shared narrative state (~6h)
- **T-004** [T1] systemd user service `cypherclaw-narrative-api.service` enabled and started; survives reboot; logs to journal (~3h)
- **T-005** [T2] Pytest test suite covering each endpoint with at least: success path, auth failure (when enabled), bad input validation, downstream-engine error handling (~6h)
- **T-006** [T1] Update PromptClaw `ESCALATIONS.md` with operator action items: enable systemd user-service lingering (`loginctl enable-linger user`) so the service runs without an active SSH session; configure `NARRATIVE_AUTH_TOKEN` if defense-in-depth desired; document Deniable Mac's Tailscale IP in firewall allowlist (if any) (~3h)

*Subtotal: ~27 hours*

### Sprint 5: Library & CRUD Polish

**Depends on:** Sprint 0 (Versioning System), Sprint 1 (Library & CRUD Polish)

- **T-007** [T1] Domain-column migration: additive `ALTER TABLE entities ADD COLUMN domain TEXT DEFAULT 'shared'` and same on `events` table per `deniable_narrative_integration_v1.md` §3; non-breaking, existing rows default to 'shared'; runs as a `narrative/migrations/` Alembic step or equivalent (~3h) → deps: T-001
- **T-008** [T1] FastAPI scaffold at `~/cypherclaw/src/cypherclaw/narrative_api/` with Pydantic settings (binding address, port, auth token from .env), uvicorn entry point, structured logging via structlog (~3h) → deps: T-001
- **T-009** [T1] `GET /health` endpoint returning JSON `{status, narrative_engine_importable, world_db_reachable, ollama_reachable, version, uptime_seconds}` (~3h) → deps: T-001
- **T-010** [T1] Shared-secret auth: optional `X-Narrative-Auth` header validated against env-var token; if `NARRATIVE_AUTH_TOKEN` is unset, auth is disabled (warning logged); if set, mismatched/missing token returns 401 (~3h) → deps: T-001
- **T-011** [T2] `POST /beats/next` — wraps `NarrativeEngine.next_beat()` per integration spec §6; accepts `{cycle_number, domain_filter, arc_position_target?, force_arc_event?}`, returns serialized `StoryBeat` JSON (~6h) → deps: T-001
- **T-012** [T1] `GET /world/entities?domain=…&type=…` — returns entities filtered by domain (defaults to 'shared') and optional type; pagination via `limit + offset` (~3h) → deps: T-001
- **T-013** [T1] `GET /world/entities/{entity_id}` — returns single entity with full properties JSON; 404 if not found (~3h) → deps: T-001
- **T-014** [T2] `POST /world/entities` — create new entity with `{type, name, domain, properties}`; validates domain in `{shared, cypherclaw, deniable}`; returns created entity with assigned ID (~6h) → deps: T-001
- **T-015** [T2] `PATCH /world/entities/{entity_id}` — apply state mutations to entity per integration spec `StateMutation` shape (set/increment/decrement/append/remove on field path); returns updated entity (~6h) → deps: T-001

*Subtotal: ~36 hours*

### Sprint 6: Stretch Goals

**Depends on:** Sprint 0 (Versioning System)

- **T-016** [T1] Smoke test from Deniable: a small CLI script (`scripts/smoke_narrative.py` in the cypherclaw repo) that calls each endpoint and confirms reachability; documented in README so the Deniable operator can validate from the Mac after Tailscale connection (~3h)

*Subtotal: ~3 hours*

---

## Requirements Coverage

- **MUST requirements:** 15/15 covered
- **SHOULD requirements:** 1 included as stretch

**✓ All MUST requirements covered.**

---

## Critical Path

The critical path runs through: Sprint 0 (Infrastructure) → Sprint 1 (Versioning) → Sprint 2 (Scoring) → Sprint 3 (Improvement) → Sprint 4 (API). Sprint 5 (Polish) can overlap with Sprints 2–4. Sprint 6 (Stretch) is fully deferrable.
