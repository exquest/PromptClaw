# Task T-053b: Live MIDI Event Schema

## Problem Statement

T-053a added the live MIDI emitter transport scaffold, but its event shape still
accepts any non-empty `event_type` and does not define event-specific validation
for note-on, note-off, control-change, and pitch-bend messages. Later live MIDI
Worker and visualizer slices need a stable producer-side schema so batches carry
validated MIDI byte data plus CypherClaw voice, scene, and tuning context tags.

## Technical Approach

- Keep the implementation in `src/cypherclaw/live_midi_emitter.py`, because the
  T-053a batching, HTTP POST, config, and daemon code already serialize live
  MIDI events there.
- Keep the schema stdlib-only and dataclass-based. No Pydantic or MIDI package
  is required.
- Define a schema version constant and a closed set of supported event types:
  `note_on`, `note_off`, `control_change`, and `pitch_bend`.
- Tighten `LiveMidiEvent` validation so status class, data-byte ranges, event
  type, timestamp, and context tags are checked at construction.
- Add helper constructors for the four supported event kinds. Helpers compute
  MIDI status bytes from `channel`, enforce semantic ranges, and preserve
  `voice`, `scene`, `tuning`, and `metadata` on the event.
- Add serialization helpers that validate incoming payload mappings and emit
  JSON-safe dictionaries without changing the T-053a transport responsibilities.
- Add the schema version to the batch payload returned by `build_batch_payload`
  while preserving `source`, `batch_id`, `event_count`, and `events`.
- Keep composer integration out of scope. This task only defines and serializes
  events; it does not connect composer playback to the emitter.

## Edge Cases

- `event_type` must be one of the four supported values.
- `status` must be a MIDI status byte in `[0, 255]`; data bytes must be channel
  data bytes in `[0, 127]`.
- `channel` helper inputs must be integers in `[0, 15]`.
- `note_on` must use status class `0x90` and non-zero velocity.
- `note_off` must accept explicit `0x80` note-off events and the MIDI
  convention of `0x90` with velocity zero.
- `control_change` must use status class `0xB0`.
- `pitch_bend` must use status class `0xE0`; helper bend values must be
  integers in `[0, 16383]` and serialize to LSB/MSB data bytes.
- Timestamps must be finite numbers.
- `voice`, `scene`, and `tuning` must be string tags; empty strings are allowed
  for unknown context.
- Metadata must be JSON-safe. Invalid metadata should fail before HTTP POST.
- Empty batches still return the existing successful no-op post result and must
  not issue an HTTP request.
- No dependencies, database changes, migrations, provider secrets, runtime state
  directories, startup-flow rewiring, agent command strings, Worker changes, or
  SuperCollider changes are required.
- The generated startup-identity hardening bullets are covered by existing
  regression tests. T-053b will re-run those anchors rather than changing
  unrelated startup flow.

## Acceptance Criteria

1. T-053b has a written specification with problem statement, approach, edge
   cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-053b|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-053b-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "T-053b|Phase 0 Explore|live_midi_emitter|midi_scene|event schema" progress.md`

3. The live MIDI event schema rejects unsupported event types, mismatched status
   classes, out-of-range data bytes, non-finite timestamps, non-string context
   tags, and non-JSON-safe metadata.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py::test_live_midi_event_schema_rejects_invalid_event_shapes -q`

4. Helper constructors serialize `note_on`, `note_off`, `control_change`, and
   `pitch_bend` events with correct status/data bytes and preserved
   voice/scene/tuning tags.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py::test_event_helper_constructors_emit_supported_schema_shapes -q`

5. Payload validation accepts serialized schema events, rejects malformed
   payload mappings, and preserves context metadata through a round trip.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py::test_validate_live_midi_event_payload_round_trips_context -q`

6. Batch payloads carry the schema version and expected batch shape for mixed
   MIDI event kinds.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py::test_build_batch_payload_includes_schema_version_and_mixed_event_shapes -q`

7. Existing T-053a config, batching, HTTP, retry, daemon, and CLI coverage stays
   green.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py -q`

8. Startup identity hardening remains green, including first-boot identity
   persistence, standalone/federated reuse, and bootstrap-before-announcer
   wiring.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

9. Task bookkeeping documents T-053b scope, assumptions, no new dependencies, no
   database changes, no composer integration, and startup identity anchors.
   - **VERIFY:** `rg -n "T-053b|MIDI event schema|No new dependencies|No database changes|no composer integration|startup identity" CHANGELOG.md progress.md ESCALATIONS.md specs/t-053b-spec.md`

10. Required final validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
