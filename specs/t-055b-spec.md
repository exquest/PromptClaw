# Task T-055b: Canvas MIDI Note Shapes

## Problem Statement

T-055a connected the `cypherclaw.holdenu.com` canvas visualizer to the live MIDI
WebSocket and stores normalized note-on/note-off events in a bounded browser
queue. The draw loop still ignores those discrete note events, so the page only
reacts to continuous audio-feature state.

T-055b renders each live MIDI note-on as a discrete canvas shape. Pitch maps to
vertical position, velocity maps to shape size, and each shape fades out over a
short lifetime while the existing audio-feature visualizer continues to draw.

## Technical Approach

- Keep PromptClaw as the ADP source of truth for the specification, progress,
  changelog, and escalation records.
- Implement the browser runtime in the sibling Worker project:
  `/Users/anthony/Programming/catalog-explorer/worker`.
- Preserve the existing single-file Worker style in `worker/src/index.ts`, the
  T-055a live MIDI WebSocket client, the SSE feature client, HLS audio playback,
  archive feed, Durable Object room, Worker config, and public route behavior.
- Add a small event-to-shape mapper for normalized T-055a MIDI events:
  - only `note_on` events spawn visual shapes;
  - MIDI note `0..127` maps to a normalized Y position, low notes near the
    bottom and high notes near the top;
  - velocity `1..127` maps to a stable pixel radius range;
  - channel and sequence provide deterministic X/hue variation without changing
    the live MIDI protocol.
- Store active shapes in `window.cypherclawVisualizerState.midiShapes` and
  expose them as `window.cypherclawLiveMidiShapes` for diagnostics and tests.
- Keep active shapes bounded by the same 128-entry MIDI limit and prune expired
  shapes inside the draw loop.
- Draw MIDI shapes over the continuous audio-feature field with opacity that
  decays linearly across a short fixed lifetime.
- Add dependency-free Node tests before implementation using the existing VM
  runtime harness.

## Edge Cases

- Note-off messages and note-on velocity zero must remain queued as MIDI events
  but must not spawn a new shape.
- Malformed and non-note WebSocket messages are still ignored by the T-055a MIDI
  parser and therefore cannot create shapes.
- Very low and very high MIDI notes must clamp inside the canvas bounds.
- Very soft velocities must remain visible at the minimum radius; maximum
  velocities must not create oversized shapes.
- Shape expiration must remove old shapes from state and diagnostics so a long
  installation does not accumulate stale draw work.
- Existing SSE feature drawing must continue to run before, during, and after
  MIDI shape expiration.
- The task must not add npm packages, Python packages, provider secrets,
  database columns, D1 database migrations, Durable Object migrations, R2 layout
  changes, runtime state directories, startup-flow rewiring, agent commands, or
  SuperCollider source changes.
- Mandatory SuperCollider hardening is a verification anchor only: existing
  profiled voice SynthDefs must still declare `fx_bus_id`, and
  `sw_sampler.scd` must still use `fx_bus_id` rather than the legacy `fx_bus`
  control. T-055b does not change `.scd` files.

## Acceptance Criteria

1. T-055b has a written specification with problem statement, technical
   approach, edge cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-055b|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-055b-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "T-055b|Phase 0 Explore|MIDI note shapes|pitch-to-position|velocity-to-size|catalog-explorer" progress.md`

3. The `cypherclaw.holdenu.com` root HTML exposes MIDI shape diagnostics and
   wires the shape mapper/draw pass into the inline visualizer runtime.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-landing.test.js`

4. Live MIDI note-on events spawn diagnostic shape objects with pitch-to-Y
   position mapping and velocity-to-size mapping.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-visualizer-runtime.test.js`

5. Note-off events do not spawn shapes, and active MIDI shapes are drawn during
   animation frames without interrupting the existing audio-feature drawing.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-visualizer-runtime.test.js`

6. MIDI shapes decay over their configured lifetime and are pruned from
   browser state and `data-midi-shapes` diagnostics after expiration.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-visualizer-runtime.test.js`

7. Existing live MIDI WebSocket routing, validation, fan-out, and Workers
   runtime latency coverage remain intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi.test.js tests/cypherclaw-live-midi-config.test.js && npm run test:workers -- tests/cypherclaw-live-midi-latency.vitest.ts`

8. Existing CypherClaw Worker behavior remains intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test`

9. Worker TypeScript checks pass.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm run check && npm run check:workers`

10. SuperCollider routing hardening remains green for voice `fx_bus_id`
    declarations and `sw_sampler.scd` `fx_bus_id` routing.
    - **VERIFY:** `pytest tests/test_space_reverb_profiles.py::test_voice_synthdefs_declare_fx_bus_id_routing_contract tests/test_space_reverb_profiles.py::test_voice_synthdef_fx_bus_ids_are_pairwise_unique tests/test_sw_sampler.py::SwSamplerEndToEndTests::test_sw_sampler_source_and_runtime_harness_round_trip_json_diagnostic -q`

11. Task bookkeeping documents T-055b scope, assumptions, no new dependencies,
    no D1 or Durable Object migration, and SuperCollider hardening.
    - **VERIFY:** `rg -n "T-055b|MIDI note shapes|pitch-to-position|velocity-to-size|No new dependencies|No D1 database migration|No Durable Object migration|fx_bus_id" CHANGELOG.md progress.md ESCALATIONS.md specs/t-055b-spec.md`

12. Required final validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
