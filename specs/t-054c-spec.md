# Task T-054c: Live MIDI Durable Object Config and Route Reachability

## Problem Statement

T-054a and T-054b added the `LiveMidiRoom` Durable Object runtime in the
sibling `/Users/anthony/Programming/catalog-explorer/worker` project, including
the public `/api/cypherclaw/live-midi` WebSocket route, a top-level
`LIVE_MIDI_ROOM` binding, a top-level Durable Object migration, and event
fan-out. T-054c closes the deployment contract for that route: the Worker must
keep the route reachable through typed `Env` bindings and Wrangler config in
every configured Wrangler environment that can run this Worker.

The current Worker has a `[env.dev]` section for dev deployments but no
environment-scoped Durable Object binding or migration. Wrangler environment
bindings are not inherited from the top level, so `wrangler --env dev` would
lose `env.LIVE_MIDI_ROOM` even though the source route exists.

## Technical Approach

- Keep PromptClaw as the ADP source of truth for specification, progress,
  changelog, and escalation records.
- Implement Worker changes in
  `/Users/anthony/Programming/catalog-explorer/worker`.
- Add dependency-free Node tests that inspect `worker/wrangler.toml` and
  `worker/src/index.ts` before implementation.
- Pin the Durable Object config contract:
  - top-level `[[durable_objects.bindings]]` binds `LIVE_MIDI_ROOM` to
    `LiveMidiRoom`;
  - top-level `[[migrations]]` includes `new_sqlite_classes = ["LiveMidiRoom"]`;
  - `[[env.dev.durable_objects.bindings]]` binds `LIVE_MIDI_ROOM` to
    `LiveMidiRoom`;
  - `[[env.dev.migrations]]` includes `new_sqlite_classes = ["LiveMidiRoom"]`.
- Pin the source contract that makes the route reachable:
  - `Env` includes `LIVE_MIDI_ROOM: DurableObjectNamespace`;
  - the route table dispatches `GET /api/cypherclaw/live-midi` to
    `serveCypherClawLiveMidi`;
  - non-WebSocket requests return `426` with `Upgrade: websocket`;
  - WebSocket upgrades forward to the global `LiveMidiRoom` instance.
- Implement the minimum missing config: add `env.dev` Durable Object binding and
  migration entries to `worker/wrangler.toml`.
- Do not change the T-054b fan-out assertions after the red phase.

## Edge Cases

- Top-level deploys and `--env dev` deploys must both expose
  `env.LIVE_MIDI_ROOM`.
- `env.dev` should use its own Durable Object namespace rather than reaching
  into production storage.
- Non-WebSocket requests must not call the Durable Object namespace and must
  return `426` with `Upgrade: websocket`.
- WebSocket upgrade routing must continue using the stable room name
  `idFromName("global")`.
- The task must not add npm dependencies, provider secrets, D1 migrations, R2
  layout changes, runtime state directories, database columns, or
  SuperCollider source changes.
- Mandatory hardening remains explicit: existing SuperCollider voice SynthDefs
  must declare `fx_bus_id`, and `sw_sampler.scd` must route through
  `fx_bus_id` rather than the legacy `fx_bus` control.

## Acceptance Criteria

1. T-054c has a written specification with problem statement, technical
   approach, edge cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-054c|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-054c-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "T-054c|Phase 0 Explore|env.dev|LIVE_MIDI_ROOM|LiveMidiRoom" progress.md`

3. Worker tests pin the top-level and `env.dev` Wrangler Durable Object binding
   plus migration for `LiveMidiRoom`.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi-config.test.js`

4. Worker tests pin the source route/type contract for
   `/api/cypherclaw/live-midi`, including `LIVE_MIDI_ROOM` in `Env` and the
   minimal `Upgrade: websocket` guard returning `426`.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi-config.test.js`

5. Existing live MIDI WebSocket routing, acceptance, validation, and fan-out
   behavior remains intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-live-midi.test.js`

6. Existing CypherClaw Worker behavior remains intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test`

7. Worker TypeScript checks pass.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm run check`

8. Existing SuperCollider routing hardening remains green: all profiled voice
   SynthDefs declare `fx_bus_id`, and `sw_sampler.scd` routes through
   `fx_bus_id`.
   - **VERIFY:** `pytest tests/test_space_reverb_profiles.py::test_voice_synthdefs_declare_fx_bus_id_routing_contract tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_send_writes_to_fx_bus tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_bus_default_is_sampler_bus -q`

9. Task bookkeeping documents T-054c scope, assumptions, no new dependencies,
   no D1 database migration, the Wrangler Durable Object migration, and the
   hardening checks.
   - **VERIFY:** `rg -n "T-054c|LiveMidiRoom|LIVE_MIDI_ROOM|env.dev|No new dependencies|No D1 database migration|new_sqlite_classes|fx_bus_id|sw_sampler" CHANGELOG.md progress.md ESCALATIONS.md specs/t-054c-spec.md`

10. Required final validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
