# Task T-053a: Live MIDI Emitter Daemon Scaffold

## Problem Statement

CC-090 requires CypherClaw to publish live MIDI events toward the holdenu
Cloudflare Worker at `/api/cypherclaw/midi-event`, with batching and event
metadata. The composer integration is intentionally out of scope for T-053a:
this slice creates an import-safe daemon scaffold, config loader, batching
queue, retrying HTTP POST client, and graceful shutdown behavior that later
composer code can call.

## Technical Approach

- Add `src/cypherclaw/live_midi_emitter.py` so the scaffold is covered by the
  existing package, Ruff, and mypy validation.
- Keep dependencies stdlib-only. Use `urllib.request` for the POST client and
  injectable callables for `urlopen`, sleep, and time so tests do not perform
  live network calls or real backoff delays.
- Define typed dataclasses for `LiveMidiEvent`, `LiveMidiEmitterConfig`,
  `MidiPostResult`, and the batching queue.
- Load config from environment variables with safe defaults:
  endpoint URL, optional bearer token, batch size, time flush interval,
  request timeout, retry count, and backoff base.
- Batch events by either queue size or elapsed time since the first queued
  event. The daemon flushes any remaining events when the stop event is set.
- POST a JSON batch payload containing source, batch id, event count, and
  enriched event objects. MIDI byte fields remain `status`, `data1`, and
  `data2`; contextual tags (`event_type`, `voice`, `scene`, `tuning`) remain
  in the POST payload for the Worker route to consume or normalize later.
- Retry transient failures only: network errors, HTTP 429, and HTTP 5xx.
  Non-retryable 4xx responses fail immediately.
- Add a console script entry point for the scaffold without reading composer
  state or wiring live playback paths.

## Edge Cases

- MIDI byte values must be integers from 0 through 255.
- Timestamps must be finite numbers.
- Empty batches must not issue HTTP requests.
- A size-triggered flush should reset the time-trigger window for the next
  batch.
- A pending time-triggered batch should remain queued until the configured
  interval elapses.
- HTTP 400/401/403/404/422 should not retry.
- HTTP 429/500/502/503/504 and `URLError` should retry with exponential
  backoff and then raise if attempts are exhausted.
- Shutdown must flush queued events exactly once and then return.
- No composer modules should import or instantiate the emitter in T-053a.
- Mandatory hardening: existing SuperCollider voice SynthDefs must continue
  declaring `fx_bus_id`, and `sw_sampler.scd` must continue routing through
  `fx_bus_id` rather than the legacy `fx_bus` control.

## Acceptance Criteria

1. T-053a has a written specification with problem statement, technical
   approach, edge cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-053a|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-053a-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "T-053a|Phase 0 Explore|CC-090|live_midi_emitter|midi-event" progress.md`

3. Config loading provides safe defaults and environment overrides without
   hardcoded secrets.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py::test_config_loads_defaults_and_env_overrides -q`

4. Live MIDI events validate MIDI bytes and timestamps and serialize enriched
   context fields into JSON-safe dictionaries.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py::test_live_midi_event_validates_bytes_and_serializes_metadata -q`

5. The batching queue flushes by configured batch size and by elapsed time.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py::test_batching_queue_flushes_by_size_and_time -q`

6. The HTTP client posts JSON batches with expected headers and retries only
   transient failures with deterministic exponential backoff.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py::test_http_client_posts_json_payload_with_auth_header tests/test_live_midi_emitter.py::test_http_client_retries_transient_failures_with_backoff tests/test_live_midi_emitter.py::test_http_client_does_not_retry_non_transient_client_errors -q`

7. The daemon loop flushes pending events on graceful shutdown and the CLI wires
   parseable options to the daemon without starting composer integration.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py::test_run_daemon_flushes_pending_events_on_shutdown tests/test_live_midi_emitter.py::test_main_builds_config_installs_signal_handlers_and_runs_daemon -q`

8. T-053a does not add composer integration.
   - **VERIFY:** `! rg -n "live_midi_emitter|midi-event" my-claw/tools/duet_composer.py src/cypherclaw/composer_api src/cypherclaw/composer_vocabulary_bridge.py`

9. Existing SuperCollider routing hardening remains green.
   - **VERIFY:** `pytest tests/test_space_reverb_profiles.py::test_voice_synthdefs_declare_fx_bus_id_routing_contract tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_send_writes_to_fx_bus tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_bus_default_is_sampler_bus -q`

10. Task bookkeeping documents scope, assumptions, no new dependencies, no
    database changes, no composer integration, and the hardening checks.
    - **VERIFY:** `rg -n "T-053a|live_midi_emitter|No new dependencies|No database changes|no composer integration|fx_bus_id|sw_sampler" CHANGELOG.md progress.md ESCALATIONS.md specs/t-053a-spec.md`

11. Required final validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
