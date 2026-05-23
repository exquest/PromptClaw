# T-028c Specification

## Problem Statement

T-028a and T-028b established the `cypherclaw.holdenu.com` live page with an
audio player, rendered GlyphWeave backdrop, and foreground canvas placeholder.
The canvas still does not draw, and the page does not open the
`/api/cypherclaw/live-features` Server-Sent Events feed described by PRD
CC-024.

T-028c implements the first active visualizer slice: a browser-side canvas draw
loop with a small audio-feature vocabulary, plus an SSE client that connects to
the live-features feed URL already carried on the canvas element.

## Technical Approach

- Keep PromptClaw as the ADP source of truth for the spec, progress notes,
  changelog, and escalation records.
- Implement the runtime page behavior in the sibling holdenu Worker route:
  `/Users/anthony/Programming/catalog-explorer/worker/src/index.ts`.
- Preserve the existing host gate, `GET /` and `HEAD /` behavior, CORS headers,
  cache TTL, hls.js playback wiring, and reduced-motion backdrop handling.
- Add a typed Worker constant for `/api/cypherclaw/live-features` and route
  public `GET` requests to a minimal SSE response with `text/event-stream`,
  no-cache headers, a retry hint, and an initial feature payload. This keeps the
  page's `EventSource` from targeting a 404 while leaving durable-object fanout
  and feature-update ingestion to a later task.
- Extend the inline page script with `initCypherClawVisualizer()`:
  - locate `#cypherclaw-visualizer` and its 2D context;
  - resize the canvas backing store for its displayed size and device pixel
    ratio;
  - run a `requestAnimationFrame` draw loop;
  - draw a stable ambient frame before live features arrive;
  - parse JSON feature events from both default `message` events and named
    `features` events;
  - map `rms`, `pitch_hz`, `centroid_hz`, `scene`, and `tuning` into simple
    foreground drawing state;
  - keep browser state on `data-visualizer-state` and `data-feed-state`
    attributes for tests and diagnostics;
  - degrade cleanly when canvas 2D context or `EventSource` is unavailable.
- Keep tests in the Worker's existing dependency-free Node test runner by
  asserting returned HTML/script structure and the public SSE response.

## Edge Cases

- `HEAD /` must remain bodyless even though the inline page script grows.
- The explorer host must not receive the CypherClaw root landing page.
- If `EventSource` is unavailable, the canvas draw loop still runs with ambient
  graphics and marks the feed state as unsupported.
- Invalid SSE JSON must not stop the draw loop.
- If the SSE stream errors or reconnects, the page should mark feed state for
  diagnostics while allowing the browser's EventSource retry behavior.
- The minimal SSE endpoint is intentionally not a durable fanout service; live
  feature ingestion and multi-client broadcast remain future work.
- The page must not expose listener counts, viewer counts, or analytics-driven
  composer inputs.
- No provider secrets, database migrations, runtime state directories, npm
  packages, database columns, or startup-flow rewiring are required.
- The generated startup identity hardening bullets target existing startup
  paths; T-028c verifies those anchors instead of broadening this public-page
  visualizer slice into identity subsystem work.

## Acceptance Criteria

1. T-028c has a written specification with problem statement, approach, edge
   cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-028c|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-028c-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "Phase 0 Explore|T-028c|canvas draw loop|SSE client|live-features" progress.md`

3. The `cypherclaw.holdenu.com` root HTML initializes an active canvas
   visualizer with a 2D context, device-pixel-ratio-aware backing store, and a
   `requestAnimationFrame` draw loop.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

4. The root HTML opens an `EventSource` against the canvas
   `data-live-features-url`, parses JSON feature events, and records feed state
   without surfacing listener or viewer telemetry.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

5. `GET /api/cypherclaw/live-features` returns an SSE-compatible response with
   no-cache headers, retry metadata, and an initial feature payload.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

6. Existing host, `HEAD /`, live audio, GlyphWeave backdrop, playlist, and
   segment behavior remains intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test`

7. Worker TypeScript checks pass.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm run check`

8. Mandatory startup identity hardening remains covered for
   `bootstrap_identity()` persistence, standalone/federated reuse, and
   bootstrap-before-announcer ordering.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

9. Task bookkeeping documents T-028c scope, the minimal SSE feed response, and
   verification results.
   - **VERIFY:** `rg -n "T-028c|canvas visualizer|SSE|live-features|draw loop" CHANGELOG.md progress.md ESCALATIONS.md specs/t-028c-spec.md`

10. Full PromptClaw validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
