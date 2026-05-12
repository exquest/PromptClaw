# Requirements Register — Cypherclaw Narrative-Engine HTTP Service PRD (PromptClaw queue addendum)

**Extracted:** 2026-05-02T00:13:47.318942+00:00
**Total requirements:** 16

| ID | Description | Priority | Tier | Section |
|----|-------------|----------|------|---------|
| CN-001 | Domain-column migration: additive `ALTER TABLE entities ADD COLUMN domain TEXT DEFAULT 'shared'` and same on `events` table per `deniable_narrative_integration_v1.md` §3; non-breaking, existing rows default to 'shared'; runs as a `narrative/migrations/` Alembic step or equivalent | MUST | T1 |  |
| CN-002 | FastAPI scaffold at `~/cypherclaw/src/cypherclaw/narrative_api/` with Pydantic settings (binding address, port, auth token from .env), uvicorn entry point, structured logging via structlog | MUST | T1 |  |
| CN-003 | `GET /health` endpoint returning JSON `{status, narrative_engine_importable, world_db_reachable, ollama_reachable, version, uptime_seconds}` | MUST | T1 |  |
| CN-004 | Shared-secret auth: optional `X-Narrative-Auth` header validated against env-var token; if `NARRATIVE_AUTH_TOKEN` is unset, auth is disabled (warning logged); if set, mismatched/missing token returns 401 | MUST | T1 |  |
| CN-005 | `POST /beats/next` — wraps `NarrativeEngine.next_beat()` per integration spec §6; accepts `{cycle_number, domain_filter, arc_position_target?, force_arc_event?}`, returns serialized `StoryBeat` JSON | MUST | T2 |  |
| CN-006 | `GET /world/entities?domain=…&type=…` — returns entities filtered by domain (defaults to 'shared') and optional type; pagination via `limit + offset` | MUST | T1 |  |
| CN-007 | `GET /world/entities/{entity_id}` — returns single entity with full properties JSON; 404 if not found | MUST | T1 |  |
| CN-008 | `POST /world/entities` — create new entity with `{type, name, domain, properties}`; validates domain in `{shared, cypherclaw, deniable}`; returns created entity with assigned ID | MUST | T2 |  |
| CN-009 | `PATCH /world/entities/{entity_id}` — apply state mutations to entity per integration spec `StateMutation` shape (set/increment/decrement/append/remove on field path); returns updated entity | MUST | T2 |  |
| CN-010 | `POST /memory/search` — wraps `NarrativeMemory` semantic search; accepts `{query, k, domain_filter}`, returns ranked results | MUST | T2 |  |
| CN-011 | `GET /events?since_event_id=…&domain=…` — paginated event log read; supports incremental tail-reading from a known event ID | MUST | T1 |  |
| CN-012 | `POST /events` — append a narrative event to the world state event log; used by Deniable to record raid outcomes that should propagate via shared narrative state | MUST | T2 |  |
| CN-013 | systemd user service `cypherclaw-narrative-api.service` enabled and started; survives reboot; logs to journal | MUST | T1 |  |
| CN-014 | Pytest test suite covering each endpoint with at least: success path, auth failure (when enabled), bad input validation, downstream-engine error handling | MUST | T2 |  |
| CN-015 | Update PromptClaw `ESCALATIONS.md` with operator action items: enable systemd user-service lingering (`loginctl enable-linger user`) so the service runs without an active SSH session; configure `NARRATIVE_AUTH_TOKEN` if defense-in-depth desired; document Deniable Mac's Tailscale IP in firewall allowlist (if any) | MUST | T1 |  |
| CN-016 | Smoke test from Deniable: a small CLI script (`scripts/smoke_narrative.py` in the cypherclaw repo) that calls each endpoint and confirms reachability; documented in README so the Deniable operator can validate from the Mac after Tailscale connection | SHOULD | T1 |  |