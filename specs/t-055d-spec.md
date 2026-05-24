# Task T-055d: Live MIDI Visualizer End-to-End Verification

## Problem Statement

T-055a through T-055c added the local Worker runtime for
`cypherclaw.holdenu.com`: the page subscribes to `/api/cypherclaw/live-midi`,
maps note-on events into pitch/velocity-driven canvas shapes, and composites
those shapes over the continuous audio-feature visualizer. The remaining gap is
deployment-level proof. The live hostname must expose the current visualizer,
accept live MIDI WebSocket traffic, and show that the deployed browser runtime
keeps MIDI note shapes visible with the audio-feature reactions in the same
canvas frame.

Initial live exploration found the current Cloudflare deployment stale: the
root page still showed the prepared-address fallback and
`/api/cypherclaw/live-midi` plus `/api/cypherclaw/live-features` returned 404.
T-055d adds a gated live E2E check and uses it to verify the deployed
production surface after the Worker is updated.

## Technical Approach

- Keep PromptClaw as the ADP source of truth for the specification, progress,
  changelog, and escalation records.
- Implement the live verification harness in the sibling Worker project:
  `/Users/anthony/Programming/catalog-explorer/worker`.
- Preserve the existing Worker source, Durable Object protocol, inline browser
  visualizer runtime, SSE feature feed, HLS audio player, R2/D1 layout, and
  package dependencies.
- Add a dependency-free Node test gated by `CYPHERCLAW_RUN_LIVE_E2E=1` so the
  normal local test suite does not depend on the public network.
- Pin `workers_dev = false` in `wrangler.toml` so the custom-domain deployment
  path does not require enabling the script on a default workers.dev route.
- The live E2E test must:
  - fetch `https://cypherclaw.holdenu.com/` and require the deployed root page
    to expose the canvas visualizer, audio player, live-feature URL, live-MIDI
    URL, and MIDI/audio layer diagnostics;
  - fetch `/api/cypherclaw/live-features` and require an SSE bootstrap feature
    payload;
  - open two real `wss://cypherclaw.holdenu.com/api/cypherclaw/live-midi`
    WebSocket clients, send scripted note-on MIDI JSON through one client, and
    confirm the other client receives the exact MIDI events;
  - execute the deployed inline runtime in the existing VM-style fake browser
    harness, inject live-feature and MIDI messages, and assert the pitch-to-Y
    and velocity-to-radius mapping plus same-frame audio/MIDI draw calls.
- Run the gated live test in red phase before deployment, then deploy the
  existing Worker and rerun it green.

## Edge Cases

- The live test must fail loudly if production serves the old prepared page,
  because that page has no canvas, no live-feature SSE client, and no live MIDI
  client.
- The WebSocket fan-out check must filter for the scripted MIDI JSON it sent so
  unrelated live room traffic cannot create a false positive.
- The VM visualizer check must use the deployed HTML, not local source, so it
  verifies what browsers receive from the live hostname.
- MIDI shape assertions must cover at least two note-on events where the higher
  pitch maps higher on the canvas and the larger velocity maps to a larger
  radius.
- Audio-feature reactions must be asserted in the same animation frame as MIDI
  shapes, with audio drawing before the MIDI foreground blend and normal canvas
  compositing restored afterward.
- The test is explicitly opt-in because it depends on Cloudflare, DNS, and
  public-network availability.
- The Cloudflare account must have an account-level Workers subdomain
  initialized before Wrangler will upload scripts; T-055d uses the official
  Workers Subdomain API for that account prerequisite rather than adding a
  runtime dependency or provider secret.
- The task must not add npm packages, Python packages, provider secrets,
  database columns, D1 database migrations, Durable Object migrations, R2 layout
  changes, runtime state directories, startup-flow rewiring, agent commands, or
  SuperCollider source changes.
- Mandatory SuperCollider hardening remains a verification anchor only:
  profiled voice SynthDefs must still declare `fx_bus_id`, and
  `sw_sampler.scd` must still use `fx_bus_id` rather than `fx_bus`.

## Acceptance Criteria

1. T-055d has a written specification with problem statement, technical
   approach, edge cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-055d|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-055d-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`, including the
   stale live deployment finding and sibling Worker scope.
   - **VERIFY:** `rg -n "T-055d|Phase 0 Explore|stale live deployment|live MIDI E2E|catalog-explorer" progress.md`

3. The Worker project has a gated live E2E test that is skipped by default and
   only runs when explicitly opted in.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-e2e.test.js`

4. The gated live E2E test fails against a stale production deployment and
   passes after deployment when the live root page exposes the current
   visualizer, HLS audio player, live-feature SSE URL, live MIDI WebSocket URL,
   and MIDI/audio layer diagnostics.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && CYPHERCLAW_RUN_LIVE_E2E=1 npm test -- tests/cypherclaw-live-e2e.test.js`

5. The live WebSocket feed accepts scripted MIDI note-on JSON from one client
   and fans out the exact events to a second client.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && CYPHERCLAW_RUN_LIVE_E2E=1 npm test -- tests/cypherclaw-live-e2e.test.js`

6. The deployed browser runtime maps pitch and velocity correctly: higher MIDI
   pitch produces a higher canvas Y position, and larger velocity produces a
   larger MIDI shape radius.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && CYPHERCLAW_RUN_LIVE_E2E=1 npm test -- tests/cypherclaw-live-e2e.test.js`

7. The deployed browser runtime keeps audio-feature reactions visible in the
   same frame as MIDI shapes, draws audio before MIDI, uses the MIDI foreground
   blend only for the MIDI pass, and restores normal compositing afterward.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && CYPHERCLAW_RUN_LIVE_E2E=1 npm test -- tests/cypherclaw-live-e2e.test.js`

8. Wrangler config disables the default workers.dev route so custom-domain
   deploys do not require this Worker to be publicly exposed at a workers.dev
   script URL.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi-config.test.js`

9. Existing local Worker behavior and TypeScript checks remain green.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test && npm run check && npm run check:workers`

10. Existing live MIDI Workers-runtime latency coverage remains green.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm run test:workers -- tests/cypherclaw-live-midi-latency.vitest.ts`

11. SuperCollider routing hardening remains green for voice `fx_bus_id`
    declarations and `sw_sampler.scd` `fx_bus_id` routing.
    - **VERIFY:** `pytest tests/test_space_reverb_profiles.py::test_voice_synthdefs_declare_fx_bus_id_routing_contract tests/test_space_reverb_profiles.py::test_voice_synthdef_fx_bus_ids_are_pairwise_unique tests/test_sw_sampler.py::SwSamplerEndToEndTests::test_sw_sampler_source_and_runtime_harness_round_trip_json_diagnostic -q`

12. Task bookkeeping documents T-055d scope, assumptions, no new dependencies,
    no D1 or Durable Object migration, live deployment verification, and
    SuperCollider hardening.
    - **VERIFY:** `rg -n "T-055d|live MIDI E2E|stale live deployment|No new dependencies|No D1 database migration|No Durable Object migration|fx_bus_id" CHANGELOG.md progress.md ESCALATIONS.md specs/t-055d-spec.md`

13. Required final validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
