# Task T-053d: Composer + Emitter Mock Worker End-to-End

## Problem Statement

T-053a through T-053c added the producer-side live MIDI pieces: validated MIDI
event schema, batching queue, retrying HTTP POST transport, and composer
publishing from `play_voice(...)` and tracker row automation. The remaining
CC-090 gap is an end-to-end proof that composer-generated events actually move
through the emitter's batching/HTTP path into a Worker-shaped endpoint with the
expected tags and ordering.

T-053d adds a local integration test with a mock Worker HTTP endpoint. The test
drives composer note publishing into a real `LiveMidiPublisher`, lets the
emitter flush a batch to the mock endpoint, and asserts that the received JSON
batch preserves note ordering and voice, scene, tuning, and metadata tags. It
also adds basic telemetry/log lines around producer flushes and posted batches
so runtime operators can see batch IDs, event counts, endpoints, and first/last
event context without exposing provider secrets.

## Technical Approach

- Keep the implementation in the existing Python producer path:
  `src/cypherclaw/live_midi_emitter.py` and `my-claw/tools/duet_composer.py`.
- Add a stdlib-only pytest integration test. Use `http.server` on localhost as
  the mock Worker endpoint, with no live Cloudflare, no provider secrets, and
  no external network dependency.
- In the test, import `duet_composer.py` with the existing fake
  `pythonosc.udp_client` pattern, attach a `LiveMidiPublisher` backed by a
  `BatchingMidiQueue`, and configure the publisher to post through
  `post_midi_batch(...)` to the mock Worker endpoint.
- Script two `play_voice(...)` calls with stable timestamps. The queue should
  size-flush after four events: note-on/note-off for the first note, then
  note-on/note-off for the second note.
- Assert the mock Worker receives one JSON batch with the expected schema
  version, source, event count, event ordering, voice tag, scene tag, tuning
  tag, note numbers, velocities, timestamps, and composer metadata.
- Add lightweight emitter telemetry without changing the batch schema:
  producer flush log lines when `LiveMidiPublisher` flushes a batch, and HTTP
  success/failure log lines that include batch ID, endpoint, event count,
  attempts, status, and first/last event context.
- Keep live MIDI publishing fail-closed for composer playback.
- Do not add dependencies, database columns, migrations, Worker routes,
  runtime state directories, startup-flow rewiring, agent commands, provider
  secrets, or SuperCollider source changes.

## Edge Cases

- The mock Worker must bind localhost on an ephemeral port and shut down even
  if assertions fail.
- The integration test must not hit the real
  `https://cypherclaw.holdenu.com/api/cypherclaw/midi-event` endpoint.
- The POST payload must remain JSON-safe and retain
  `cypherclaw.live_midi_event.v1`.
- Event order must be composer emission order inside the batch.
- Note-off timestamps must follow their matching note-on timestamps by the
  composer-resolved duration.
- Batch telemetry must avoid bearer tokens and metadata dumps that could leak
  secrets.
- Posting an empty batch must remain a no-op and must not log a false success.
- Startup identity hardening remains a verification anchor only. Existing
  PromptClaw tests cover `bootstrap_identity()` invocation before
  `FirstBootAnnouncer` and identity persistence in standalone and federated
  modes.

## Acceptance Criteria

1. T-053d has a written specification with problem statement, technical
   approach, edge cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-053d|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-053d-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "T-053d|Phase 0 Explore|mock Worker|live_midi_emitter|duet_composer|CC-090" progress.md`

3. The mock Worker end-to-end integration test drives `duet_composer.play_voice`
   through a real `LiveMidiPublisher` and `post_midi_batch(...)`, and the mock
   endpoint receives one batched payload with correct schema, source, tags,
   note ordering, note values, timestamps, and metadata.
   - **VERIFY:** `pytest tests/test_live_midi_e2e.py::test_composer_events_reach_mock_worker_batched_with_tags_and_ordering -q`

4. Live MIDI producer/HTTP telemetry emits basic batch diagnostics without
   exposing bearer tokens.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py::test_live_midi_publisher_logs_flush_telemetry tests/test_live_midi_e2e.py::test_composer_events_reach_mock_worker_batched_with_tags_and_ordering -q`

5. Existing T-053a/T-053b emitter tests and T-053c composer publishing tests
   remain green.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py tests/test_live_midi_composer_integration.py -q`

6. Existing composer routing and no-viewer-count protections remain green.
   - **VERIFY:** `pytest tests/test_duet_composer_space_routing.py tests/test_composer_no_viewer_listener_counts.py -q`

7. Startup identity hardening remains green, including bootstrap before
   announcement and identity persistence across standalone/federated modes.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

8. Existing SuperCollider routing hardening remains green for `fx_bus_id` and
   `sw_sampler.scd`.
   - **VERIFY:** `pytest tests/test_space_reverb_profiles.py::test_voice_synthdefs_declare_fx_bus_id_routing_contract tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_send_writes_to_fx_bus tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_bus_default_is_sampler_bus -q`

9. Task bookkeeping documents T-053d scope, assumptions, no new dependencies,
   no database changes, no Worker route changes, and hardening checks.
   - **VERIFY:** `rg -n "T-053d|mock Worker|No new dependencies|No database changes|no Worker route|startup identity|fx_bus_id|sw_sampler" CHANGELOG.md progress.md ESCALATIONS.md specs/t-053d-spec.md`

10. Required final validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
