# Task T-054a: Live MIDI WebSocket Room Bootstrap

## Problem Statement

T-053 begins publishing live MIDI events toward the holdenu Cloudflare Worker,
and T-054 requires a Durable Object backed `/api/cypherclaw/live-midi`
WebSocket for browser subscribers. The Worker currently has CypherClaw segment,
playlist, archive, landing-page, and SSE bootstrap routes, but no WebSocket
entry point and no Durable Object room class to hold live MIDI subscribers.

T-054a is the connection plumbing slice only. It adds the `LiveMidiRoom`
Durable Object class, accepts WebSocket clients into an in-memory set, removes
clients when sockets close or error, and wires the public route to the global
room through `idFromName("global")`. MIDI event ingestion and fan-out remain
out of scope for later T-054 subtasks.

## Technical Approach

- Keep PromptClaw as the ADP source of truth for this spec, progress notes,
  changelog, and escalation records.
- Implement the Worker changes in the sibling project:
  `/Users/anthony/Programming/catalog-explorer/worker`.
- Extend `worker/src/index.ts` in the existing single-file Worker style used by
  the CypherClaw segment, playlist, archive, landing, and SSE routes.
- Add `LIVE_MIDI_ROOM` to the Worker `Env` binding interface as a
  `DurableObjectNamespace`. The current Cloudflare Worker type package brands
  generic Durable Object namespace parameters for classes that extend
  `cloudflare:workers`' base `DurableObject`; this Worker keeps the existing
  zero-import CommonJS test build, so the binding uses the unparameterized
  namespace type while exporting the class for Wrangler.
- Export `LiveMidiRoom` from `worker/src/index.ts` so Wrangler can bind the
  class and tests can instantiate it.
- In `LiveMidiRoom.fetch`, require `Upgrade: websocket`, create a
  `WebSocketPair`, call `server.accept()`, add the accepted server socket to an
  in-memory `Set<WebSocket>`, and remove it on `close` and `error`.
- Return the client socket in a `101` response from the Durable Object.
- Add a Worker route for `GET /api/cypherclaw/live-midi` that rejects
  non-WebSocket GETs with `426` and forwards valid WebSocket upgrades to
  `env.LIVE_MIDI_ROOM.get(env.LIVE_MIDI_ROOM.idFromName("global")).fetch(req)`.
- Update `worker/wrangler.toml` with a Durable Object binding and Wrangler
  migration for the new `LiveMidiRoom` class. Cloudflare's Durable Object docs
  require both a binding and a migration for a new class, with
  `new_sqlite_classes` recommended for new Durable Objects.
- Add dependency-free Node tests under the existing Worker test runner. Tests
  use fake Durable Object namespace/stub objects for route forwarding and a
  fake WebSocket/Response shim for the room acceptance path.

## Edge Cases

- Non-WebSocket requests to `/api/cypherclaw/live-midi` must not reach the
  Durable Object and must return `426` with `Upgrade: websocket`.
- The route must use the stable global room name exactly: `idFromName("global")`.
- The route must preserve the existing host behavior, including the
  cypherclaw landing page, HLS playlist, segment serving, and SSE bootstrap.
- The room must not broadcast, transform, persist, or inspect MIDI payloads in
  T-054a.
- Socket `close` and `error` events must both remove the accepted socket from
  the in-memory client set.
- No database schema changes, D1 migrations, R2 layout changes, provider
  secrets, npm packages, runtime state directories, startup-flow rewiring, or
  SuperCollider behavior changes are required.
- Mandatory hardening: existing SuperCollider voice SynthDefs must continue
  declaring `fx_bus_id`, and `sw_sampler.scd` must continue using `fx_bus_id`
  instead of the legacy `fx_bus` control. This task does not touch those files,
  but the regression checks remain part of verification.

## Acceptance Criteria

1. T-054a has a written specification with problem statement, approach, edge
   cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-054a|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-054a-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "T-054a|Phase 0 Explore|LiveMidiRoom|live-midi" progress.md`

3. The Worker route rejects non-WebSocket GETs to
   `/api/cypherclaw/live-midi` with `426` and `Upgrade: websocket`.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi.test.js`

4. The Worker route forwards WebSocket upgrade requests to the
   `LIVE_MIDI_ROOM` Durable Object namespace via `idFromName("global")`.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi.test.js`

5. `LiveMidiRoom` accepts WebSocket upgrades, tracks accepted server sockets in
   memory, and removes clients on `close` and `error` events without adding
   fan-out logic.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi.test.js`

6. Wrangler configuration declares the `LIVE_MIDI_ROOM` binding and a migration
   for the new `LiveMidiRoom` Durable Object class.
   - **VERIFY:** `rg -n "LIVE_MIDI_ROOM|LiveMidiRoom|new_sqlite_classes" /Users/anthony/Programming/catalog-explorer/worker/wrangler.toml`

7. Existing CypherClaw Worker behavior remains intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test`

8. Worker TypeScript checks pass.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm run check`

9. Existing SuperCollider routing hardening remains green: all profiled voice
   SynthDefs declare `fx_bus_id`, and `sw_sampler.scd` routes through
   `fx_bus_id`.
   - **VERIFY:** `pytest tests/test_space_reverb_profiles.py::test_voice_synthdefs_declare_fx_bus_id_routing_contract tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_send_writes_to_fx_bus tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_bus_default_is_sampler_bus -q`

10. Task bookkeeping documents T-054a scope, assumptions, no new dependencies,
    no D1 database migration, the Wrangler Durable Object migration, and the
    hardening checks.
    - **VERIFY:** `rg -n "T-054a|LiveMidiRoom|live-midi|No new dependencies|No D1 database migration|new_sqlite_classes|fx_bus_id|sw_sampler" CHANGELOG.md progress.md ESCALATIONS.md specs/t-054a-spec.md`

11. Required final validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
