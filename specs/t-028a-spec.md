# T-028a Specification

## Problem Statement

The `cypherclaw.holdenu.com` root route currently serves a minimal placeholder
landing page from the holdenu Cloudflare Worker. T-028a replaces that placeholder
with the first static public stream scaffold: a root HTML document with a live
audio element, a GlyphWeave backdrop container, and a foreground canvas
visualizer placeholder.

This is the scaffold slice of PRD CC-024 / Sprint 1 T-012. It does not implement
live canvas drawing, hls.js playback fallback, archive feed rendering, or the
SSE Durable Object itself. Later T-028 subtasks own those behaviors.

## Technical Approach

- Update the existing host-gated Worker root route in
  `/Users/anthony/Programming/catalog-explorer/worker/src/index.ts`.
- Keep `GET /` and `HEAD /` limited to `cypherclaw.holdenu.com`; the explorer
  host must continue returning 404 for `/`.
- Return one static HTML document with inline CSS and no new dependencies.
- Include:
  - `<audio id="cypherclaw-live-audio" controls preload="none">` with a source
    for `/api/cypherclaw/live.m3u8`.
  - `<section id="glyphweave-backdrop">` as the future GlyphWeave image layer.
  - `<canvas id="cypherclaw-visualizer">` with stable dimensions and a
    `data-live-features-url="/api/cypherclaw/live-features"` hook for later
    SSE-driven rendering.
- Preserve existing response headers: `text/html; charset=utf-8`,
  `Content-Length`, CORS headers, and short cache TTL.
- Document PromptClaw-side task state in `progress.md`, `ESCALATIONS.md`, and
  `CHANGELOG.md` because this repository is the ADP source of truth while the
  Worker implementation lives in the sibling `catalog-explorer` repository.

## Edge Cases

- `HEAD /` must return the same headers as `GET /` with no response body.
- `GET /` on non-CypherClaw hostnames must not accidentally serve the live page.
- The page must not expose listener counts or analytics-driven composer inputs.
- The HLS segment container compatibility issue from T-026 remains out of scope;
  this page only points at the established playlist endpoint.
- No provider secrets, database migrations, runtime state directories, or new
  dependencies are required.
- Startup identity hardening is unrelated to this page scaffold, but the
  existing startup regression anchors remain mandatory verification.

## Acceptance Criteria

1. T-028a has a written specification with problem statement, approach, edge
   cases, and verifyable acceptance criteria.
   - **VERIFY:** `rg -n "T-028a|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-028a-spec.md`

2. `GET /` on `cypherclaw.holdenu.com` returns a 200 HTML stream scaffold, not
   the old placeholder copy.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

3. The root HTML includes an accessible live-stream audio element wired to
   `/api/cypherclaw/live.m3u8`.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

4. The root HTML includes stable placeholder containers for the GlyphWeave
   backdrop and canvas visualizer, including a live-features data hook.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

5. Existing host and HEAD behavior remains intact: only the CypherClaw host gets
   the root page, and `HEAD /` returns no body.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

6. Worker quality checks pass for the changed public route.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test && npm run check`

7. Mandatory startup identity hardening remains covered for bootstrap-before-
   announcer ordering and standalone/federated persistence.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

8. Task bookkeeping documents T-028a scope, assumptions, and validation.
   - **VERIFY:** `rg -n "T-028a|static public stream scaffold|GlyphWeave backdrop|canvas visualizer" specs/t-028a-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

9. Full PromptClaw validation passes.
   - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
