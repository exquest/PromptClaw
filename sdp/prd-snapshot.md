# PRD Snapshot - Cypherclaw Narrative-Engine HTTP Service PRD (PromptClaw queue addendum)
**Source:** `prd-cypherclaw-narrative-http-service.md`
**SHA-256:** `d8af751270fc008eec76c9fc7709e7ccf87558a1e088f1a1f3c29b73c3ea3063`
**Captured:** 2026-05-02T00:13:47.318983+00:00

---
# Cypherclaw Narrative-Engine HTTP Service PRD (PromptClaw queue addendum)

**Project:** This PRD imports into the PromptClaw queue (`~/Programming/PromptClaw/`) — PromptClaw is the SDP project that drives cypherclaw-side work.
**Version:** 1.0
**Date:** 2026-05-01
**SDP Protocol:** v1.0
**Downstream consumer:** Deniable (`~/Programming/Deniable/prd-deniable.md`) — its `narrative/world_bridge.py` calls the service this PRD builds.
**Upstream substrate:** Existing GlyphWeave Narrative Engine at `~/cypherclaw/src/cypherclaw/narrative/` on the cypherclaw machine — fully built, in-process Python module today.

---

## Overview

Cypherclaw hosts a complete narrative engine (`engine.py`, `world.py`, `beat.py`, `characters.py`, `structures.py`, `symbols.py`, `tone.py`, `evaluator.py`, `memory.py`, `translator.py`, `migrations/`, `data/`). It's used in-process today by `cypherclaw/src/cypherclaw/art_cycle.py` for art generation. There is no HTTP API — all calls go through Python imports.

Deniable runs on a different machine (the developer's Mac) and needs to call the engine over Tailscale. SQLite-over-network is unsafe (locking + latency); the right pattern is a thin HTTP service on cypherclaw that wraps the in-process engine and exposes the methods Deniable needs.

This PRD specifies that service:

- Small FastAPI app at `~/cypherclaw/src/cypherclaw/narrative_api/`
- Binds Tailscale interface (not 0.0.0.0); never publicly reachable
- Exposes the methods Deniable's `world_bridge.py` consumes (~6-8 endpoints)
- Apply the additive `domain` column migration on the world-state SQLite (per `deniable_narrative_integration_v1.md` §3)
- Systemd unit so the service survives reboots
- Health endpoint, structured logs, optional shared-secret header for defense-in-depth

This is **~10-15 atomic reqs**. ~1-2 days of agent work. Depends on existing PromptClaw infrastructure (engine code is stable; this PRD just wraps it).

---

## Technology Stack

| Component | Choice | Notes |
|---|---|---|
| HTTP framework | **FastAPI** | Matches Deniable; lightweight |
| ASGI server | **uvicorn** | Standard |
| Models / serialization | **Pydantic v2** | Match Deniable's bridge schemas |
| Auth (optional) | **Shared secret header** | `X-Narrative-Auth: <token>` from .env |
| Logging | **structlog** | JSON logs; matches PromptClaw / Deniable convention |
| Process supervision | **systemd unit** | Auto-restart, survives reboots |
| Network binding | **Tailscale interface only** | Never bind 0.0.0.0 |
| LLM runtime (already deployed) | **Local Ollama on cypherclaw** | Existing; `qwen3.5:9b`, `nomic-embed-text` |
| Test runner | **pytest** | SDP default |

---

## Project Structure

This work edits the existing cypherclaw repo; no new repo created.

```
~/cypherclaw/src/cypherclaw/
├── narrative/                # existing — unchanged
│   ├── engine.py
│   ├── world.py
│   ├── beat.py
│   ├── characters.py
│   ├── structures.py
│   ├── symbols.py
│   ├── tone.py
│   ├── evaluator.py
│   ├── memory.py
│   ├── translator.py
│   ├── migrations/
│   └── data/
├── narrative_api/            # NEW — this PRD's deliverable
│   ├── __init__.py
│   ├── main.py               # FastAPI app + uvicorn entry
│   ├── routes/
│   │   ├── beats.py          # /beats endpoints
│   │   ├── world.py          # /world entity CRUD
│   │   ├── memory.py         # /memory search
│   │   └── health.py
│   ├── schemas.py            # Pydantic models matching Deniable's bridge
│   ├── deps.py               # auth, DB session
│   └── tests/
├── ...
```

Plus systemd unit at `~/.config/systemd/user/cypherclaw-narrative-api.service` (or system-level if cypherclaw is configured that way).

---

## Requirements

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CN-001 | Domain-column migration: additive `ALTER TABLE entities ADD COLUMN domain TEXT DEFAULT 'shared'` and same on `events` table per `deniable_narrative_integration_v1.md` §3; non-breaking, existing rows default to 'shared'; runs as a `narrative/migrations/` Alembic step or equivalent | MUST | T1 | Migration applies cleanly; existing rows still readable; new rows can carry domain values |
| CN-002 | FastAPI scaffold at `~/cypherclaw/src/cypherclaw/narrative_api/` with Pydantic settings (binding address, port, auth token from .env), uvicorn entry point, structured logging via structlog | MUST | T1 | `python -m cypherclaw.narrative_api` boots; binds configured Tailscale address; emits structured logs |
| CN-003 | `GET /health` endpoint returning JSON `{status, narrative_engine_importable, world_db_reachable, ollama_reachable, version, uptime_seconds}` | MUST | T1 | Endpoint returns 200 with all subsystem statuses; degraded status if any check fails |
| CN-004 | Shared-secret auth: optional `X-Narrative-Auth` header validated against env-var token; if `NARRATIVE_AUTH_TOKEN` is unset, auth is disabled (warning logged); if set, mismatched/missing token returns 401 | MUST | T1 | Without env var, requests without header succeed (warning in logs); with env var set, mismatched header returns 401 |
| CN-005 | `POST /beats/next` — wraps `NarrativeEngine.next_beat()` per integration spec §6; accepts `{cycle_number, domain_filter, arc_position_target?, force_arc_event?}`, returns serialized `StoryBeat` JSON | MUST | T2 | Calling endpoint with valid params returns a StoryBeat; matches the in-process call's output shape |
| CN-006 | `GET /world/entities?domain=…&type=…` — returns entities filtered by domain (defaults to 'shared') and optional type; pagination via `limit + offset` | MUST | T1 | Query with `domain=deniable` returns only Deniable + shared entities; pagination correct |
| CN-007 | `GET /world/entities/{entity_id}` — returns single entity with full properties JSON; 404 if not found | MUST | T1 | Returns expected entity for known ID; 404 for unknown |
| CN-008 | `POST /world/entities` — create new entity with `{type, name, domain, properties}`; validates domain in `{shared, cypherclaw, deniable}`; returns created entity with assigned ID | MUST | T2 | New Deniable squad-member entity creates successfully; returned ID can be re-fetched |
| CN-009 | `PATCH /world/entities/{entity_id}` — apply state mutations to entity per integration spec `StateMutation` shape (set/increment/decrement/append/remove on field path); returns updated entity | MUST | T2 | Mutating a fighter's `current_state` from "healthy" to "wounded" persists correctly |
| CN-010 | `POST /memory/search` — wraps `NarrativeMemory` semantic search; accepts `{query, k, domain_filter}`, returns ranked results | MUST | T2 | Query returns relevant memory hits ordered by similarity; honors domain filter |
| CN-011 | `GET /events?since_event_id=…&domain=…` — paginated event log read; supports incremental tail-reading from a known event ID | MUST | T1 | Tailing from a checkpoint returns only newer events |
| CN-012 | `POST /events` — append a narrative event to the world state event log; used by Deniable to record raid outcomes that should propagate via shared narrative state | MUST | T2 | Posting a "raid completed" event persists; readable via GET /events |
| CN-013 | systemd user service `cypherclaw-narrative-api.service` enabled and started; survives reboot; logs to journal | MUST | T1 | After reboot, service restarts automatically; `systemctl --user status` shows active |
| CN-014 | Pytest test suite covering each endpoint with at least: success path, auth failure (when enabled), bad input validation, downstream-engine error handling | MUST | T2 | `pytest cypherclaw/src/cypherclaw/narrative_api/tests/` has ≥1 test per endpoint; coverage ≥80% on `narrative_api/` module |
| CN-015 | Update PromptClaw `ESCALATIONS.md` with operator action items: enable systemd user-service lingering (`loginctl enable-linger user`) so the service runs without an active SSH session; configure `NARRATIVE_AUTH_TOKEN` if defense-in-depth desired; document Deniable Mac's Tailscale IP in firewall allowlist (if any) | MUST | T1 | ESCALATIONS entries documented; operator can complete each action within 15 minutes |
| CN-016 | Smoke test from Deniable: a small CLI script (`scripts/smoke_narrative.py` in the cypherclaw repo) that calls each endpoint and confirms reachability; documented in README so the Deniable operator can validate from the Mac after Tailscale connection | SHOULD | T1 | Script run from cypherclaw machine prints OK for every endpoint; Deniable operator can copy script and run from Mac with Tailscale-reachable URL |

---

## Architecture Notes

### Why a thin wrapper, not a rewrite?

The engine is stable. This PRD's job is exposing existing methods over HTTP, not changing engine behavior. Each endpoint is roughly: parse Pydantic request → call into existing `cypherclaw.narrative.*` module → serialize result → return. New surface area is small.

### Why no JWT / OAuth?

Single-user. Tailscale provides network-level access control. Shared-secret header is a defense-in-depth gesture against accidental misconfiguration (e.g., binding to wrong interface), not a real auth system. If multi-user ever happens, swap to proper auth.

### Why systemd user service?

Cypherclaw runs as a user-level setup. `systemctl --user` keeps service ownership clean and matches existing patterns (PromptClaw's other long-running processes). `enable-linger` is a one-time operator action.

### Why MessagePack-compatible JSON, not pure binary protocol?

JSON is fine over Tailscale at the volumes we're talking about (1-3 narrative events per cycle, infrequent triggers). Pydantic + JSON is way more debuggable than custom binary; if perf becomes an issue, swap to MessagePack (or gRPC) later.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Engine in-process method signatures don't match endpoint expectations | Medium | Medium | Each endpoint test includes a real engine call; signature mismatch caught at test time |
| Domain-column migration breaks something cypherclaw uses | Low | Medium | Migration is additive (default 'shared'); existing rows unchanged |
| Tailscale latency makes per-call slow enough to be annoying | Low | Low | Narrative cycles fire at hideout transitions, not in-raid; latency budget is 5-15s per spec; Tailscale adds 5-50ms one-way — negligible |
| Service crash during a Deniable cycle | Medium | Low | Deniable bridge degrades gracefully ("INTERFERENCE" placeholder); systemd auto-restarts the service |
| API key / shared secret leakage | Low | Low | Single-user; secret in .env; not committed |

---

## Assumptions Log

1. **Cypherclaw machine is on the same tailnet as the developer's Mac.**
2. **The narrative engine code at `~/cypherclaw/src/cypherclaw/narrative/` is stable** — no breaking changes expected during this PRD's execution.
3. **Cypherclaw has Python 3.12+** with FastAPI installable into its existing venv.
4. **systemd user services are supported** on cypherclaw (it's a Linux box per ssh inspection).
5. **The migration to add `domain` columns is safe** to apply to the live world-state DB; cypherclaw's existing art_cycle continues to function with `domain='shared'` defaults.

---

## Resolved Clarifications

- **Service location: cypherclaw machine.** Confirmed.
- **PRD location: imported into PromptClaw queue.** Confirmed by operator 2026-05-01 ("I have been using the PromptClaw project for building cypherclaw stuff").
- **Auth: shared-secret header optional.** No JWT / OAuth.
- **Process supervision: systemd user service.** No Docker.
- **Endpoints: ~6-8 covering beats / world / memory / events.** Confirmed via spec inspection.

---

## Project History

- v1.0 — 2026-05-01 — Initial PRD: 16 atomic reqs covering HTTP service implementation + migration + systemd + smoke test.

---

*Downstream consumer: `~/Programming/Deniable/prd-deniable.md` (its `narrative/world_bridge.py` calls this service). Engine reference: `~/Programming/Deniable/deniable_narrative_integration_v1.md` (the integration spec).*
