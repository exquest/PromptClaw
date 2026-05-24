# Task T-055a: Canvas Visualizer Live MIDI Client

## Problem Statement

The holdenu Worker already exposes `/api/cypherclaw/live-midi` as a public
WebSocket backed by `LiveMidiRoom`, and the `cypherclaw.holdenu.com` landing
page already runs a browser canvas visualizer driven by the live-features SSE
bootstrap feed. The visualizer does not yet subscribe to the live MIDI
WebSocket, so note activity cannot be queued in browser memory for later visual
response slices.

T-055a adds the first browser-side MIDI client slice: the canvas visualizer opens
the live MIDI WebSocket, parses incoming JSON MIDI note-on and note-off events,
and stores normalized note events in a bounded in-memory queue.

## Technical Approach

- Keep PromptClaw as the ADP source of truth for the specification, progress,
  changelog, and escalation records.
- Implement the runtime page behavior in the sibling Worker project:
  `/Users/anthony/Programming/catalog-explorer/worker`.
- Preserve the existing single-file Worker style in `worker/src/index.ts` and
  the current host routing, HLS audio player, SSE feature feed, archive feed,
  Durable Object room, and Worker config.
- Add `data-live-midi-url="/api/cypherclaw/live-midi"` and MIDI diagnostic
  attributes to `#cypherclaw-visualizer`.
- Extend the inline browser runtime with a `connectCypherClawMidiFeed()` path
  that:
  - converts the relative live MIDI path into a `ws:` or `wss:` URL from the
    current page location;
  - opens a `WebSocket` to the existing `/api/cypherclaw/live-midi` feed;
  - records connection state in `data-midi-state`;
  - exposes the socket as `window.cypherclawLiveMidiSocket` for diagnostics.
- Add a small parser that accepts only the existing T-054 WebSocket JSON shape:
  `{ "status": number, "data1": number, "data2": number, "ts": number }`.
- Normalize MIDI note messages into queue entries with `type`, `status`,
  `note`, `velocity`, `channel`, `ts`, and `received_at_ms`.
- Treat `0x90` with velocity greater than zero as `note_on`; treat `0x80` and
  `0x90` with velocity zero as `note_off`; ignore other MIDI status classes.
- Keep the queue bounded at 128 entries to avoid unbounded memory growth during
  long-running installations.
- Expose the queue as both `window.cypherclawLiveMidiEvents` and
  `window.cypherclawVisualizerState.midiEvents` for tests and later visualizer
  slices.
- Add dependency-free Node tests before implementation, using the existing
  Worker test build and VM-based browser runtime harness.

## Edge Cases

- Browsers without `WebSocket` support must keep the canvas draw loop and SSE
  feature client running, while marking `data-midi-state="unsupported"`.
- Relative MIDI paths must resolve to `wss://` on HTTPS pages and `ws://` on
  HTTP pages.
- Malformed JSON, non-object payloads, missing fields, non-integer MIDI bytes,
  out-of-range note/velocity bytes, non-finite timestamps, control-change
  messages, pitch-bend messages, and other non-note statuses must be ignored
  without closing the socket.
- Note-on with velocity zero must be queued as note-off because many MIDI
  devices use that form instead of an explicit `0x80` note-off status.
- Queue overflow must drop oldest entries, not newest entries.
- WebSocket error and close events should update diagnostics without clearing
  the existing queue.
- The task must not add npm packages, provider secrets, database columns, D1
  migrations, Durable Object migrations, R2 layout changes, runtime state
  directories, startup-flow rewiring, agent commands, or SuperCollider changes.
- Mandatory startup identity hardening remains explicit: existing startup paths
  already invoke `bootstrap_identity()` before `FirstBootAnnouncer` and tests
  cover identity persistence across standalone and federated boots. T-055a
  re-runs those anchors rather than broadening this Worker visualizer slice into
  the identity subsystem.

## Acceptance Criteria

1. T-055a has a written specification with problem statement, technical
   approach, edge cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-055a|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-055a-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "T-055a|Phase 0 Explore|canvas visualizer|live MIDI WebSocket|catalog-explorer" progress.md`

3. The `cypherclaw.holdenu.com` root HTML gives the canvas a live MIDI
   WebSocket URL and wires a browser-side MIDI client into the inline visualizer
   runtime.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

4. The browser MIDI client resolves the live MIDI path to a `wss://` URL on the
   HTTPS landing page and opens one `WebSocket` subscription during visualizer
   initialization.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-visualizer-runtime.test.js`

5. Incoming live MIDI WebSocket messages are parsed into normalized note-on and
   note-off queue entries, including note-on velocity-zero as note-off, while
   malformed or non-note messages are ignored.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-visualizer-runtime.test.js`

6. The browser MIDI event queue is bounded at 128 events and drops oldest
   entries first.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-visualizer-runtime.test.js`

7. Existing live MIDI WebSocket routing, validation, fan-out, and Workers
   runtime latency coverage remain intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi.test.js tests/cypherclaw-live-midi-config.test.js && npm run test:workers -- tests/cypherclaw-live-midi-latency.vitest.ts`

8. Existing CypherClaw Worker behavior remains intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test`

9. Worker TypeScript checks pass.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm run check && npm run check:workers`

10. Startup identity hardening remains green: startup invokes
    `bootstrap_identity()` before `FirstBootAnnouncer`, first boot persists an
    identity, and standalone/federated modes reuse persisted identity between
    boots.
    - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

11. Task bookkeeping documents T-055a scope, assumptions, no new dependencies,
    no D1 or Durable Object migration, and startup identity hardening.
    - **VERIFY:** `rg -n "T-055a|live MIDI WebSocket|MIDI event queue|No new dependencies|No D1 database migration|No Durable Object migration|startup identity" CHANGELOG.md progress.md ESCALATIONS.md specs/t-055a-spec.md`

12. Required final validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
