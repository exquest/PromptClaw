# Task T-054b: Live MIDI Event Ingest and Fan-Out

## Problem Statement

T-054a added the public `/api/cypherclaw/live-midi` WebSocket route and the
`LiveMidiRoom` Durable Object connection room in the sibling
`catalog-explorer/worker` project, but the room only accepts and tracks sockets.
The next slice must let a connected sender publish live JSON MIDI events to the
room and relay valid events to all other connected sockets so browser clients can
observe the live performance stream.

The accepted wire shape is a JSON object with exactly the MIDI event fields used
by the live emitter:

```json
{"status":144,"data1":60,"data2":100,"ts":1779568086.25}
```

## Technical Approach

- Keep PromptClaw as the ADP source of truth for the spec, progress notes,
  changelog, and escalation records.
- Implement Worker runtime changes in
  `/Users/anthony/Programming/catalog-explorer/worker/src/index.ts`, following
  the existing single-file Worker pattern and the `LiveMidiRoom` class added by
  T-054a.
- Extend `LiveMidiRoom.fetch` to register a `message` listener on the accepted
  server socket. For each incoming message, parse only string payloads as JSON,
  validate the event shape, and broadcast the original JSON text to every socket
  in the room except the sender.
- Validate shape strictly enough for the live MIDI contract:
  `status`, `data1`, and `data2` must be integers in `[0, 255]`; `ts` must be a
  finite number; the payload must be a non-array object; and no extra keys are
  accepted.
- Invalid or unsupported messages are ignored without closing the sender or
  broadcasting anything. The room does not send protocol error messages in this
  slice.
- When a recipient throws during `send`, remove that recipient from the room so
  later broadcasts do not keep hitting dead sockets.
- Preserve T-054a behavior: non-WebSocket requests still receive `426`, accepted
  sockets are tracked in memory, and `close`/`error` remove clients.
- Add dependency-free Node tests to
  `/Users/anthony/Programming/catalog-explorer/worker/tests/cypherclaw-live-midi.test.js`
  before implementation. Assertions are locked after the red phase.
- No D1 schema changes, R2 layout changes, Durable Object migration changes, new
  npm packages, provider secrets, runtime state directories, startup-flow
  rewiring, or SuperCollider changes are required.

## Edge Cases

- The sender must not receive its own valid event.
- Multiple other connected sockets must each receive the same JSON message.
- Malformed JSON, arrays, nulls, missing keys, extra keys, nonnumeric channel
  bytes, non-integer channel bytes, out-of-range channel bytes, and non-finite
  timestamps must be dropped silently.
- Binary/non-string WebSocket payloads must be dropped silently.
- A send failure to one recipient must remove only that failed recipient while
  allowing the same event to reach other live recipients.
- A failed recipient should not receive later broadcasts after removal.
- Broadcast does not persist events, reorder them, transform JSON, or route
  through D1/R2.
- The auto-generated startup identity hardening target is unrelated to the
  Worker MIDI room, but it remains a mandatory regression anchor. Existing tests
  already cover `bootstrap_identity()` before `FirstBootAnnouncer` and identity
  persistence across standalone/federated boots.

## Acceptance Criteria

1. T-054b has a written specification with problem statement, approach, edge
   cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-054b|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-054b-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "T-054b|Phase 0 Explore|LiveMidiRoom|fan-out|catalog-explorer" progress.md`

3. `LiveMidiRoom` broadcasts valid JSON MIDI events to every connected socket
   except the sender.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi.test.js`

4. `LiveMidiRoom` drops malformed, unsupported, or contract-invalid messages
   without broadcasting or disconnecting the sender.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi.test.js`

5. `LiveMidiRoom` removes dead recipient sockets when `send()` fails and
   continues broadcasting to remaining live sockets.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi.test.js`

6. Existing T-054a WebSocket routing and acceptance behavior remains intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi.test.js`

7. Existing CypherClaw Worker behavior remains intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test`

8. Worker TypeScript checks pass.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm run check`

9. Startup identity hardening remains green, including bootstrap before
   announcement and identity persistence across standalone/federated boots.
   - **VERIFY:** `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

10. Task bookkeeping documents T-054b scope, assumptions, no new dependencies,
    no D1 database migration, no Durable Object migration change, and the
    startup identity hardening checks.
    - **VERIFY:** `rg -n "T-054b|LiveMidiRoom|fan-out|No new dependencies|No D1 database migration|No Durable Object migration|startup identity" CHANGELOG.md progress.md ESCALATIONS.md specs/t-054b-spec.md`

11. Required final validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
