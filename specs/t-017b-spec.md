# T-017b Specification

## Problem Statement

T-017a preserved imported MIDI files as ordered faithful note events, but the
processed manifest still lacks a CypherClaw scene payload that downstream
renderers can schedule directly. Faithful-transmission mode needs a scene-shaped
contract that keeps the imported pitch sequence and source rhythm intact while
remaining independent from MIDI vocabulary fragment selection. The faithful path
must not ask the composer vocabulary bridge to choose fragments or cite
`vocabulary_fragment_id` metadata.

## Technical Approach

- Add a small typed `cypherclaw.midi_scene` module with frozen dataclasses for a
  JSON-safe faithful MIDI scene:
  - `FaithfulSceneStep`
  - `FaithfulSceneLane`
  - `FaithfulScenePattern`
  - `FaithfulSceneConstraint`
  - `FaithfulMidiScene`
- Expose `build_faithful_midi_scene(events, ...)` where `events` are the parsed
  `FaithfulMidiEvent` records from T-017a.
- Map each event to one melody lane step in original order:
  - `pitch` stores the exact imported MIDI pitch.
  - `duration_ticks` stores the exact imported source duration.
  - `length_rows` is a quantized scheduler length computed from
    `duration_ticks / ticks_per_beat * rows_per_beat`, with a minimum of one
    row for positive durations.
  - `row` advances cumulatively by `length_rows`, preserving the imported
    rhythmic sequence.
  - `velocity` is normalized to `[0.0, 1.0]`, while original velocity is also
    retained in step metadata.
- The scene metadata marks `mode: faithful_transmission`,
  `source_transform: midi_whole_file_scene`, `source_event_count`, and
  `source_duration_ticks`. It must not include vocabulary fragment metadata.
- Wire `process_midi_file(..., faithful_transmission=True)` to place the
  scene dictionary in the processed manifest as `faithful_scene` alongside the
  existing `faithful_events` and empty `fragments` block.
- Keep default fragment-extraction mode unchanged and keep all vocabulary
  selection logic out of the faithful scene builder.
- No new dependency, database migration, provider secret, runtime state
  directory, HTTP route, or startup-flow change is required.
- The generated startup hardening bullets target the existing identity startup
  subsystem. `midi_intake_daemon.main()` already invokes
  `bootstrap_identity()` before `FirstBootAnnouncer()`, and standalone plus
  federated persistence remain mandatory regression anchors for this task.

## Edge Cases

- Empty event input returns a scene with one empty melody lane, zero rows, and
  explicit `source_event_count: "0"` metadata.
- Non-positive event durations are skipped so malformed event payloads cannot
  create zero-length scheduler steps.
- `ticks_per_beat <= 0` falls back to `rows_per_beat` as the row denominator,
  allowing SMPTE-style or malformed divisions to still produce bounded scene
  rows while retaining exact source durations in metadata.
- `rows_per_beat <= 0` falls back to `1`.
- MIDI velocities below `0` or above `127` are clamped before normalization.
- Malformed faithful files that validate only by header still produce an empty
  faithful scene rather than invoking fragment extraction.

## Acceptance Criteria

1. Parsed faithful MIDI events map to a JSON-safe CypherClaw scene shape with
   one melody lane, ordered steps, exact `pitch` sequence, exact
   `duration_ticks`, normalized velocities, cumulative rows, and no vocabulary
   fragment metadata.
   - **VERIFY:** `pytest tests/test_midi_scene.py::test_build_faithful_midi_scene_preserves_pitch_sequence_and_rhythm -q`

2. The scene builder handles empty input and invalid timing parameters without
   raising, producing an empty scene with deterministic metadata and no
   vocabulary citation keys.
   - **VERIFY:** `pytest tests/test_midi_scene.py::test_build_faithful_midi_scene_handles_empty_events_and_bad_timing -q`

3. Faithful intake manifests include `faithful_scene` alongside
   `faithful_events`, keep `fragments` empty, and bypass both fragment
   extraction and vocabulary fragment selection logic.
   - **VERIFY:** `pytest tests/test_midi_scene.py::test_process_midi_file_faithful_mode_writes_scene_without_fragment_selection -q`

4. Default intake behavior remains fragment extraction and does not add a
   faithful scene unless `faithful_transmission=True`.
   - **VERIFY:** `pytest tests/test_midi_scene.py::test_process_midi_file_default_mode_omits_faithful_scene -q`

5. Existing T-017a faithful loader and adjacent MIDI/composer vocabulary tests
   remain green.
   - **VERIFY:** `pytest tests/test_midi_faithful_loader.py tests/test_midi_intake_daemon.py tests/test_midi_fragment_extractor.py tests/test_midi_vocabulary_store.py tests/test_composer_vocabulary_bridge.py -q`

6. Mandatory startup identity hardening anchors remain covered for startup
   bootstrap ordering and standalone/federated identity persistence.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

7. Product-facing notes document faithful scene mapping and progress.
   - **VERIFY:** `rg -n "faithful_scene|faithful MIDI scene|midi_whole_file_scene|T-017b" CHANGELOG.md progress.md docs/handoff-protocol.md ESCALATIONS.md`

8. Full validation passes.
   - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
