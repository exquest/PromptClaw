# T-028d Specification

## Problem Statement

T-028c introduced a minimal `/api/cypherclaw/live-features` SSE response and a
browser-side canvas loop, but the visualizer still treats feed messages as a
single flat JSON object. The live CypherClaw feature contract can include
glyph-facing visual fields (`brightness`, `motion`, `texture`, `density`,
`salience`), audio analysis fields (`rms`, `pitch_hz`,
`spectral_centroid_hz`, `onset_rate_hz`), scene/arc metadata, and future fanout
envelopes that group those fields under `audio`, `visual`, `scene`, and
`tuning`.

T-028d drives the canvas visualizer from those SSE feed events end to end:
parse supported event shapes, normalize them into stable visualizer state, use
that state during canvas drawing, and verify rendering with a browser-runtime
simulation.

## Technical Approach

- Keep PromptClaw as the ADP source of truth for this spec, progress notes,
  changelog, and escalation records.
- Implement the runtime page behavior in the sibling holdenu Worker route:
  `/Users/anthony/Programming/catalog-explorer/worker/src/index.ts`.
- Preserve the existing host gate, `GET /` and `HEAD /` behavior, CORS
  headers, cache TTL, hls.js playback wiring, GlyphWeave backdrop, HLS
  playlist/segment routes, and SSE endpoint path.
- Add browser-side feature normalization for both current flat payloads and
  envelope payloads:
  - flat keys from `/tmp/glyph_audio_features.json` such as `rms`, `pitch_hz`,
    `spectral_centroid_hz`, `onset_rate_hz`, `brightness`, `motion`,
    `texture`, `density`, `salience`, `arc_phase`, `scene`, and `tuning`;
  - nested `audio`, `visual`, `scene`, and `tuning` objects from a future
    durable fanout service;
  - alternate names already used by the page (`centroid_hz`, `pitchHz`,
    `amplitude`) without dropping existing compatibility.
- Update the visualizer state with normalized fields, event counters, last
  message timestamps, and diagnostic `data-*` attributes that make live state
  inspectable without exposing listener or viewer counts.
- Extend drawing to respond to audio and visual fields: RMS/amplitude affects
  radius, pitch affects vertical position, spectral centroid/brightness affects
  color, motion/onset changes sweep speed, and density changes the rendered
  line field.
- Keep tests dependency-free in the Worker's existing Node test runner by
  evaluating the returned inline page script with fake DOM, canvas, and
  `EventSource` objects. This gives an end-to-end rendering check from Worker
  HTML response through SSE dispatch to canvas draw calls.

## Edge Cases

- Invalid JSON in an SSE event must mark `data-feed-state="bad-message"` and
  must not stop the animation loop.
- Unknown, missing, or non-finite numeric fields must fall back to the previous
  value or the ambient default.
- Nested scene/tuning objects may expose either `name`, `current`, or
  `system`; string values must also work.
- EventSource errors must leave the draw loop running while marking the feed
  state for diagnostics.
- `HEAD /` remains bodyless even as the inline script changes.
- The minimal Worker SSE route is still not a durable fanout service; live
  feature ingestion and multi-client broadcast remain separate backend work.
- The page and composer must not expose listener counts, viewer counts, or
  analytics-driven composer inputs.
- No provider secrets, database migrations, database columns, runtime state
  directories, npm packages, or startup-flow rewiring are required.
- The generated startup identity hardening bullets target existing startup
  paths; T-028d verifies those anchors instead of broadening this visualizer
  slice into identity subsystem work.

## Acceptance Criteria

1. T-028d has a written specification with problem statement, approach, edge
   cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-028d|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-028d-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "Phase 0 Explore|T-028d|SSE event normalization|canvas rendering" progress.md`

3. The browser visualizer normalizes flat and nested SSE feature payloads into
   stable state fields for audio, visual, scene, tuning, and timing metadata.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-visualizer-runtime.test.js`

4. Dispatching a live `features` event updates visualizer diagnostics and drives
   canvas drawing with the normalized feed values.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-visualizer-runtime.test.js`

5. The public SSE bootstrap response includes the expanded visual/audio feature
   vocabulary and still avoids listener, viewer, or analytics telemetry.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

6. Existing CypherClaw landing, audio, GlyphWeave, playlist, segment, host, and
   `HEAD /` behavior remains intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test`

7. Worker TypeScript checks pass.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm run check`

8. Mandatory startup identity hardening remains covered for
   `bootstrap_identity()` persistence, standalone/federated reuse, and
   bootstrap-before-announcer ordering.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

9. Task bookkeeping documents T-028d scope, assumptions, and verification
   results.
   - **VERIFY:** `rg -n "T-028d|SSE event normalization|canvas rendering|visualizer runtime" CHANGELOG.md progress.md ESCALATIONS.md specs/t-028d-spec.md`

10. Full PromptClaw validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
