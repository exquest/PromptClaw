# Task T-054d: Live MIDI Workers Vitest Fan-Out Latency

## Problem Statement

T-054a through T-054c added the `/api/cypherclaw/live-midi` WebSocket route,
the `LiveMidiRoom` Durable Object, event validation, fan-out, and Wrangler
binding coverage in the sibling
`/Users/anthony/Programming/catalog-explorer/worker` project. Existing coverage
uses dependency-free Node tests with fake WebSocket shims. That proves the
in-process logic but does not exercise the route, Durable Object binding, and
WebSocket upgrade behavior inside the Cloudflare Workers runtime.

T-054d adds a real Workers Vitest integration test using
`@cloudflare/vitest-pool-workers`. The test opens two WebSocket clients against
`/api/cypherclaw/live-midi`, sends a valid MIDI event from client A, and asserts
client B receives the exact event within 1000 ms, pinning sub-second fan-out
latency through the actual Worker/Durable Object path.

## Technical Approach

- Keep PromptClaw as the ADP source of truth for the spec, progress,
  changelog, and escalation records.
- Implement the Worker test harness in
  `/Users/anthony/Programming/catalog-explorer/worker`.
- Add Vitest and `@cloudflare/vitest-pool-workers` as Worker dev dependencies,
  following Cloudflare's current Workers Vitest guidance.
- Add a Worker Vitest config that points at `worker/wrangler.toml` so the test
  uses the real `LIVE_MIDI_ROOM` Durable Object binding and schema setup config.
- Add a TypeScript Vitest file under `worker/tests/` that imports `SELF` from
  `cloudflare:test`, performs WebSocket upgrade fetches to
  `https://cypherclaw.holdenu.com/api/cypherclaw/live-midi`, accepts the two
  client sockets, and times client B's first `message` event with
  `performance.now()`.
- Keep the test focused on one observable behavior: valid MIDI event fan-out
  from client A to client B within 1000 ms. The test asserts exact payload
  preservation and closes both sockets in cleanup.
- Preserve the existing dependency-free Node test suite and scripts; add a
  separate Worker Vitest script so `npm test` remains the broad existing Worker
  regression suite.
- No Worker route behavior, MIDI payload shape, D1 schema, R2 layout, provider
  secrets, runtime state directories, startup-flow rewiring, agent commands, or
  SuperCollider source changes are required unless the new runtime test exposes
  a concrete gap.

## Edge Cases

- Client B must be connected and accepted before client A sends, avoiding a
  race that could make the latency assertion meaningless.
- The received payload must be the exact JSON string sent by client A; no
  transformation, persistence, or reserialization is expected.
- The timeout must reject after 1000 ms so a fan-out hang fails quickly.
- Cleanup must close both WebSocket clients even when the assertion fails.
- The existing Node tests remain the validation layer for invalid payloads,
  dead-recipient removal, non-WebSocket `426` responses, and Wrangler
  environment config.
- Mandatory startup identity hardening remains explicit but out of scope for the
  Worker runtime test. Existing PromptClaw startup tests cover
  `bootstrap_identity()` before `FirstBootAnnouncer` and identity persistence
  across standalone/federated boots.

## Acceptance Criteria

1. T-054d has a written specification with problem statement, technical
   approach, edge cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-054d|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-054d-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "T-054d|Phase 0 Explore|vitest-pool-workers|sub-second fan-out|catalog-explorer" progress.md`

3. Worker dev dependencies include Vitest and the Cloudflare Workers Vitest
   pool, and the new dependency decision is logged.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && node -e "const p=require('./package.json'); if(!p.devDependencies.vitest || !p.devDependencies['@cloudflare/vitest-pool-workers']) process.exit(1); console.log(p.devDependencies.vitest, p.devDependencies['@cloudflare/vitest-pool-workers'])" && rg -n "T-054d|vitest|@cloudflare/vitest-pool-workers|new dependencies" /Users/anthony/Programming/PromptClaw/ESCALATIONS.md`

4. A Workers Vitest integration test connects two WebSocket clients to
   `/api/cypherclaw/live-midi`, sends a valid MIDI event from client A, and
   asserts client B receives the exact payload within 1000 ms.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm run test:workers -- tests/cypherclaw-live-midi-latency.vitest.ts`

5. Existing live MIDI WebSocket routing, validation, fan-out, and config tests
   remain intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi.test.js tests/cypherclaw-live-midi-config.test.js`

6. Existing CypherClaw Worker behavior remains intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test`

7. Worker TypeScript checks pass.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm run check && npm run check:workers`

8. Startup identity hardening remains green, including bootstrap before
   announcement and identity persistence across standalone/federated boots.
   - **VERIFY:** `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

9. Task bookkeeping documents T-054d scope, assumptions, new Worker dev
   dependencies, no D1 database schema modification, no Durable Object schema modification,
   and the startup identity hardening checks.
   - **VERIFY:** `rg -n "T-054d|sub-second fan-out|vitest-pool-workers|New Worker dev dependencies|No D1 database schema modification|No Durable Object schema modification|startup identity" CHANGELOG.md progress.md ESCALATIONS.md specs/t-054d-spec.md`

10. Required final validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
