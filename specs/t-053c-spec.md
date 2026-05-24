# Task T-053c: Composer Live MIDI Queue Publishing

## Problem Statement

T-053a added the live MIDI emitter transport scaffold and T-053b defined the
validated event schema. The live composer still does not publish note or
automation events into that emitter queue while it generates music. CC-090 needs
composer-side note/control generation points to enqueue live MIDI events tagged
with the current voice, scene, and tuning context so the Worker and visualizer
can receive a faithful live event stream.

## Technical Approach

- Keep the validated MIDI event schema and batching queue in
  `src/cypherclaw/live_midi_emitter.py`.
- Add a small emitter-side publisher wrapper around `BatchingMidiQueue` so
  producer code can enqueue events through the existing queue abstraction
  without reimplementing batching.
- Wire `my-claw/tools/duet_composer.py` to publish note-on and note-off events
  when `play_voice(...)` generates an audible note.
- Convert composer frequencies to nearest MIDI note numbers and composer
  amplitudes to bounded MIDI velocities.
- Extend tracker playback calls to pass scene name, tuning metadata, lane/row
  metadata, and resolved voice context into `play_voice(...)`.
- Publish tracker row automation as control-change events for the existing
  scene-level controls (`density`, `master_amp`, `reverb_send`) with a master
  voice tag, scene name, and tuning metadata.
- Keep live MIDI publishing fail-closed: publishing errors are logged/skipped
  and must not interrupt OSC note generation.
- Do not add new dependencies, database columns, migrations, Worker routes,
  startup-flow rewiring, agent commands, or SuperCollider source changes.

## Edge Cases

- Invalid or non-positive frequencies should not publish MIDI note events.
- Non-positive amplitudes should not publish note-on events.
- MIDI note numbers must be clamped to `[0, 127]`.
- MIDI velocities must be clamped to `[1, 127]`.
- Note-off timestamps should follow the note-on timestamp by the resolved note
  duration when a duration is known.
- Unknown scene or tuning context should serialize as empty scene and
  `twelve_tet` tuning rather than failing.
- Tracker scenes without tuning metadata should fall back to `twelve_tet`.
- Automation values outside `[0.0, 1.0]` should clamp before conversion to MIDI
  control values in `[0, 127]`.
- Missing or disabled live MIDI publisher state should leave composer playback
  unchanged.
- The recurring SuperCollider hardening checks remain mandatory anchors:
  profiled voice SynthDefs must expose `fx_bus_id`, and `sw_sampler.scd` must
  route through `fx_bus_id` rather than `fx_bus`.

## Acceptance Criteria

1. T-053c has a written specification with problem statement, approach, edge
   cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-053c|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-053c-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "T-053c|Phase 0 Explore|duet_composer|live_midi_emitter|CC-090" progress.md`

3. The emitter exposes a producer-facing publisher that enqueues events through
   `BatchingMidiQueue` and returns size/time-triggered batches without changing
   schema validation.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py::test_live_midi_publisher_uses_batching_queue_for_producer_events -q`

4. Composer note generation publishes note-on and note-off events with current
   voice, scene, tuning, timestamp, frequency, duration, and role metadata while
   preserving the existing OSC `/s_new` path.
   - **VERIFY:** `pytest tests/test_live_midi_composer_integration.py::test_play_voice_publishes_note_events_with_scene_and_tuning_context -q`

5. Tracker row automation publishes control-change events with scene/tuning
   context and clamped MIDI controller values.
   - **VERIFY:** `pytest tests/test_live_midi_composer_integration.py::test_tracker_row_automation_publishes_control_changes_with_context -q`

6. Tracker playback passes scene and tuning context from scheduled events into
   composer note publishing.
   - **VERIFY:** `pytest tests/test_live_midi_composer_integration.py::test_tracker_playback_wires_scene_tuning_context_to_play_voice -q`

7. Existing T-053a/T-053b emitter coverage remains green.
   - **VERIFY:** `pytest tests/test_live_midi_emitter.py -q`

8. Existing composer routing and no-viewer-count protections remain green.
   - **VERIFY:** `pytest tests/test_duet_composer_space_routing.py tests/test_composer_no_viewer_listener_counts.py -q`

9. Existing SuperCollider routing hardening remains green for `fx_bus_id` and
   `sw_sampler.scd`.
   - **VERIFY:** `pytest tests/test_space_reverb_profiles.py::test_voice_synthdefs_declare_fx_bus_id_routing_contract tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_send_writes_to_fx_bus tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_bus_default_is_sampler_bus -q`

10. Task bookkeeping documents scope, assumptions, no new dependencies, no
    database changes, and hardening checks.
    - **VERIFY:** `rg -n "T-053c|No new dependencies|No database changes|fx_bus_id|sw_sampler|live MIDI queue" CHANGELOG.md progress.md ESCALATIONS.md specs/t-053c-spec.md`

11. Required final validation passes.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
