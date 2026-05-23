# T-028b Specification

## Problem Statement

T-028a replaced the `cypherclaw.holdenu.com` placeholder with a static stream
scaffold, but the page still treats the GlyphWeave backdrop as a placeholder
and relies only on a bare `<source>` tag for the live HLS stream. T-028b turns
that scaffold into the first rendered listening surface: a deep GlyphWeave-style
CSS/image backdrop layer behind the canvas stage, plus browser-side audio
playback wiring for `/api/cypherclaw/live.m3u8`.

This is still a static-page slice of PRD CC-024. Live canvas drawing, the
`/api/cypherclaw/live-features` SSE endpoint, archive feed rendering, and
end-to-end stream decode validation remain separate subtasks.

## Technical Approach

- Keep PromptClaw as the ADP source of truth for this spec, progress notes,
  changelog, and escalation records.
- Implement the public page change in the existing sibling Worker route:
  `/Users/anthony/Programming/catalog-explorer/worker/src/index.ts`.
- Preserve the existing `cypherclaw.holdenu.com` host gate, `GET /` and
  `HEAD /` behavior, response headers, cache TTL, and CORS headers.
- Replace the empty GlyphWeave placeholder with layered decorative elements
  inside `#glyphweave-backdrop`. Each layer is marked `aria-hidden="true"` and
  has a `data-glyphweave-layer` hook. The CSS uses `background-image` layers,
  blend modes, slow keyframe drift, and reduced-motion handling so the backdrop
  reads as rendered imagery without adding a new asset pipeline.
- Wire the live `<audio>` element with `data-stream-url="/api/cypherclaw/live.m3u8"`
  and an inline `initCypherClawAudio()` controller:
  - use native HLS when `HTMLAudioElement.canPlayType(...)` supports
    `application/vnd.apple.mpegurl`;
  - otherwise load hls.js from a public CDN and attach it to the audio element
    when `Hls.isSupported()`;
  - keep a direct fallback `src` assignment for browsers or tools that inspect
    the audio source without running the hls.js path;
  - never autoplay, surface listener counts, or send analytics.
- Keep tests dependency-free in the Worker's existing Node test runner by
  asserting the returned HTML, CSS, and playback bootstrap script.

## Edge Cases

- `HEAD /` must remain bodyless even though the HTML grows.
- Non-CypherClaw hostnames must continue to fall through to the existing 404
  route for `/`.
- Browser autoplay restrictions mean playback begins only through the native
  audio controls or an explicit user action.
- T-026 documented that the current `.opus` Ogg segments are not standard HLS
  media segments for hls.js/ffplay. T-028b wires the page playback controller;
  actual media decode remains dependent on a later segment-container fix.
- If hls.js fails to load or is unsupported, the page must still leave the
  audio element pointed at the playlist and remain usable in native-HLS
  browsers.
- The backdrop is decorative and must not make the canvas or audio controls
  inaccessible.
- No database columns, migrations, provider secrets, runtime state directories,
  or startup-flow rewiring are required.
- The generated startup identity hardening bullets target existing startup
  paths; T-028b verifies those anchors instead of broadening a static page task
  into identity subsystem work.

## Acceptance Criteria

1. T-028b has a written specification with problem statement, approach, edge
   cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-028b|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-028b-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "Phase 0 Explore|T-028b|GlyphWeave-style CSS/image|browser playback wiring" progress.md`

3. The `cypherclaw.holdenu.com` root HTML renders a non-empty GlyphWeave
   backdrop with image-backed layers, stable hooks, animation, and reduced
   motion handling.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

4. The root HTML wires the live audio element for native HLS and hls.js
   fallback without autoplaying or exposing listener telemetry.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

5. Existing host and `HEAD /` behavior remains intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

6. Worker tests and TypeScript checks pass.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test && npm run check`

7. Mandatory startup identity hardening remains covered for
   `bootstrap_identity()` persistence, standalone/federated reuse, and
   bootstrap-before-announcer ordering.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

8. Task bookkeeping documents T-028b scope, the hls.js runtime dependency, and
   the current HLS/Ogg playback caveat.
   - **VERIFY:** `rg -n "T-028b|hls.js|GlyphWeave-style|Ogg|opus|playback controller" CHANGELOG.md progress.md ESCALATIONS.md specs/t-028b-spec.md`

9. Full PromptClaw validation passes.
   - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
