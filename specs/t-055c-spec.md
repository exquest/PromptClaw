# Task T-055c: Canvas MIDI/Audio Layer Compositing

## Problem Statement

T-055a connected the `cypherclaw.holdenu.com` canvas visualizer to the live
MIDI WebSocket, and T-055b maps live note-on events into decaying MIDI shapes.
The runtime draws those shapes after the continuous audio-feature reaction, but
the compositing contract is still implicit: there is no explicit foreground MIDI
layer, no pinned blend mode, and no regression test proving MIDI shapes share
the same display coordinate space without leaving the canvas context in a state
that can corrupt later audio-feature frames.

T-055c makes the layer contract explicit in the same existing canvas: continuous
audio-feature reactions render first, MIDI note shapes render as the foreground
layer in the same display coordinate space, MIDI uses a bounded additive blend,
and the draw pass restores normal canvas compositing before the next frame.

## Technical Approach

- Keep PromptClaw as the ADP source of truth for the specification, progress,
  changelog, and escalation records.
- Implement the browser runtime in the sibling Worker project:
  `/Users/anthony/Programming/catalog-explorer/worker`.
- Preserve the single-file Worker style in `worker/src/index.ts`, the existing
  SSE live-feature state, T-055a MIDI queue, T-055b MIDI shape mapper, HLS audio
  playback, archive feed, Durable Object live-MIDI route, Worker config, and
  public route behavior.
- Add dependency-free Node tests before implementation using the existing VM
  runtime harness.
- Make the draw order observable and stable:
  - clear the canvas and draw the continuous audio-feature reaction layer first;
  - draw MIDI shapes second as the foreground layer;
  - set a MIDI-specific blend mode only for the MIDI pass;
  - restore `source-over` after the MIDI pass so future audio-feature drawing is
    unaffected.
- Use the already-normalized display dimensions returned by
  `resizeVisualizerCanvas(...)` for both audio-feature primitives and MIDI
  shapes, while leaving the backing-store/device-pixel-ratio scaling unchanged.
- Add small diagnostics for the layer contract so the live page can be inspected
  without exposing listener counts, viewer counts, or analytics.

## Edge Cases

- Audio-feature drawing must still run when there are no active MIDI shapes.
- Expired MIDI shapes must be pruned without skipping audio-feature drawing or
  leaving the canvas in the MIDI blend mode.
- Very low/high MIDI notes and very small/large velocities must continue to
  clamp inside the display-space canvas bounds from T-055b.
- Malformed MIDI WebSocket messages and note-off events must not create shapes
  or affect the audio-feature layer.
- Canvas backing-store resizing for device pixel ratio must remain unchanged;
  shared coordinate space means both layers use the same display `dims`, not raw
  backing-store pixels.
- The task must not add npm packages, Python packages, provider secrets,
  database columns, D1 database migrations, Durable Object migrations, R2 layout
  changes, runtime state directories, startup-flow rewiring, agent commands, or
  SuperCollider source changes.
- The generated startup identity hardening bullets target the existing
  PromptClaw startup subsystem. T-055c keeps them as mandatory regression
  anchors rather than broadening this Worker visualizer task into identity
  startup rewiring.

## Acceptance Criteria

1. T-055c has a written specification with problem statement, technical
   approach, edge cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-055c|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-055c-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "T-055c|Phase 0 Explore|shared coordinate space|MIDI/audio compositing|catalog-explorer" progress.md`

3. The `cypherclaw.holdenu.com` root HTML exposes the MIDI/audio compositing
   layer contract and keeps the MIDI draw pass wired into the inline visualizer
   runtime.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

4. Runtime tests prove continuous audio-feature drawing happens before the MIDI
   foreground layer, MIDI uses the expected blend mode, and the canvas context
   is restored to normal compositing afterward.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-visualizer-runtime.test.js`

5. Runtime tests prove MIDI shapes use the same display coordinate space as the
   audio-feature layer, including clamping inside display bounds instead of raw
   backing-store pixels.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-visualizer-runtime.test.js`

6. Existing live MIDI WebSocket routing, validation, fan-out, and Workers
   runtime latency coverage remain intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi.test.js tests/cypherclaw-live-midi-config.test.js && npm run test:workers -- tests/cypherclaw-live-midi-latency.vitest.ts`

7. Existing CypherClaw Worker behavior remains intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test`

8. Worker TypeScript checks pass.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm run check && npm run check:workers`

9. Startup identity hardening remains green: startup invokes
   `bootstrap_identity()` before `FirstBootAnnouncer`, first boot persists an
   identity, and standalone/federated modes reuse persisted identity between
   boots.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

10. Task bookkeeping documents T-055c scope, assumptions, no new dependencies,
    no D1 or Durable Object migration, and startup identity hardening.
    - **VERIFY:** `rg -n "T-055c|MIDI/audio compositing|shared coordinate space|No new dependencies|No D1 database migration|No Durable Object migration|startup identity" CHANGELOG.md progress.md ESCALATIONS.md specs/t-055c-spec.md`

11. Required final validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
