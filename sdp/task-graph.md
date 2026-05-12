# Cypherclaw Narrative-Engine HTTP Service PRD (PromptClaw queue addendum) — Task Graph

**Generated:** 2026-05-02T00:13:47.318462+00:00
**Total tasks:** 16
**Estimated effort:** ~66 hours

---

## Sprint 1 — Versioning System

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 1 | T-001 | `POST /memory/search` — wraps `NarrativeMemory` semantic search; accepts `{query, k, domain_filter}`, returns ranked results | T2 | 4 | 6 | CN-010 | — | Query returns relevant memory hits ordered by similarity; honors domain filter |
| 2 | T-002 | `GET /events?since_event_id=…&domain=…` — paginated event log read; supports incremental tail-reading from a known event ID | T1 | 3 | 3 | CN-011 | — | Tailing from a checkpoint returns only newer events |
| 3 | T-003 | `POST /events` — append a narrative event to the world state event log; used by Deniable to record raid outcomes that should propagate via shared narrative state | T2 | 5 | 6 | CN-012 | — | Posting a "raid completed" event persists; readable via GET /events |
| 4 | T-004 | systemd user service `cypherclaw-narrative-api.service` enabled and started; survives reboot; logs to journal | T1 | 4 | 3 | CN-013 | — | After reboot, service restarts automatically; `systemctl --user status` shows active |
| 5 | T-005 | Pytest test suite covering each endpoint with at least: success path, auth failure (when enabled), bad input validation, downstream-engine error handling | T2 | 5 | 6 | CN-014 | — | `pytest cypherclaw/src/cypherclaw/narrative_api/tests/` has ≥1 test per endpoint; coverage ≥80% on `narrative_api/` module |
| 6 | T-006 | Update PromptClaw `ESCALATIONS.md` with operator action items: enable systemd user-service lingering (`loginctl enable-linger user`) so the service runs without an active SSH session; configure `NARRATIVE_AUTH_TOKEN` if defense-in-depth desired; document Deniable Mac's Tailscale IP in firewall allowlist (if any) | T1 | 7 | 3 | CN-015 | — | ESCALATIONS entries documented; operator can complete each action within 15 minutes |

**Sprint 1 total:** ~27 hrs

---

## Sprint 5 — Library & CRUD Polish

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 7 | T-007 | Domain-column migration: additive `ALTER TABLE entities ADD COLUMN domain TEXT DEFAULT 'shared'` and same on `events` table per `deniable_narrative_integration_v1.md` §3; non-breaking, existing rows default to 'shared'; runs as a `narrative/migrations/` Alembic step or equivalent | T1 | 7 | 3 | CN-001 | T-001 | Migration applies cleanly; existing rows still readable; new rows can carry domain values |
| 8 | T-008 | FastAPI scaffold at `~/cypherclaw/src/cypherclaw/narrative_api/` with Pydantic settings (binding address, port, auth token from .env), uvicorn entry point, structured logging via structlog | T1 | 6 | 3 | CN-002 | T-001 | `python -m cypherclaw.narrative_api` boots; binds configured Tailscale address; emits structured logs |
| 9 | T-009 | `GET /health` endpoint returning JSON `{status, narrative_engine_importable, world_db_reachable, ollama_reachable, version, uptime_seconds}` | T1 | 6 | 3 | CN-003 | T-001 | Endpoint returns 200 with all subsystem statuses; degraded status if any check fails |
| 10 | T-010 | Shared-secret auth: optional `X-Narrative-Auth` header validated against env-var token; if `NARRATIVE_AUTH_TOKEN` is unset, auth is disabled (warning logged); if set, mismatched/missing token returns 401 | T1 | 5 | 3 | CN-004 | T-001 | Without env var, requests without header succeed (warning in logs); with env var set, mismatched header returns 401 |
| 11 | T-011 | `POST /beats/next` — wraps `NarrativeEngine.next_beat()` per integration spec §6; accepts `{cycle_number, domain_filter, arc_position_target?, force_arc_event?}`, returns serialized `StoryBeat` JSON | T2 | 4 | 6 | CN-005 | T-001 | Calling endpoint with valid params returns a StoryBeat; matches the in-process call's output shape |
| 12 | T-012 | `GET /world/entities?domain=…&type=…` — returns entities filtered by domain (defaults to 'shared') and optional type; pagination via `limit + offset` | T1 | 5 | 3 | CN-006 | T-001 | Query with `domain=deniable` returns only Deniable + shared entities; pagination correct |
| 13 | T-013 | `GET /world/entities/{entity_id}` — returns single entity with full properties JSON; 404 if not found | T1 | 4 | 3 | CN-007 | T-001 | Returns expected entity for known ID; 404 for unknown |
| 14 | T-014 | `POST /world/entities` — create new entity with `{type, name, domain, properties}`; validates domain in `{shared, cypherclaw, deniable}`; returns created entity with assigned ID | T2 | 5 | 6 | CN-008 | T-001 | New Deniable squad-member entity creates successfully; returned ID can be re-fetched |
| 15 | T-015 | `PATCH /world/entities/{entity_id}` — apply state mutations to entity per integration spec `StateMutation` shape (set/increment/decrement/append/remove on field path); returns updated entity | T2 | 4 | 6 | CN-009 | T-001 | Mutating a fighter's `current_state` from "healthy" to "wounded" persists correctly |

**Sprint 5 total:** ~36 hrs

---

## Sprint 6 — Stretch Goals

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 16 | T-016 | Smoke test from Deniable: a small CLI script (`scripts/smoke_narrative.py` in the cypherclaw repo) that calls each endpoint and confirms reachability; documented in README so the Deniable operator can validate from the Mac after Tailscale connection | T1 | 6 | 3 | CN-016 | — | Script run from cypherclaw machine prints OK for every endpoint; Deniable operator can copy script and run from Mac with Tailscale-reachable URL |

**Sprint 6 total:** ~3 hrs

---

## Summary

- **Sprint 1 (Versioning System):** 6 tasks, ~27 hrs
- **Sprint 5 (Library & CRUD Polish):** 9 tasks, ~36 hrs
- **Sprint 6 (Stretch Goals):** 1 tasks, ~3 hrs

**Total: 16 tasks, ~66 hours**
