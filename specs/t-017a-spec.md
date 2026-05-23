# T-017a Specification

## Problem Statement

CypherClaw's MIDI intake path currently treats every valid imported MIDI file
as vocabulary source material and always runs fragment extraction before writing
the processed-file manifest. Faithful-transmission mode needs a different
contract: when the operator opts in, the intake path should load the imported
MIDI as an ordered whole-file sequence of playable note events and bypass
fragment extraction entirely. This preserves the source pitch/rhythm/velocity
shape for later faithful rendering without populating motif/rhythm/chord/groove
fragments from that same pass.

## Technical Approach

- Add a small typed loader module under `src/cypherclaw/` using the same
  dependency-free Standard MIDI File parsing style as `midi_fragments.py`.
- Expose `load_faithful_midi_events(path)` returning ordered note events with
  `pitch`, `duration`, and `velocity` fields. Durations are in source ticks to
  preserve imported rhythm before later tuning/voice/space rendering.
- Parse all MIDI tracks in file order, ignore non-note data such as CC and
  pitch-bend messages, treat note-on velocity `0` as note-off, and order events
  by note start tick, track, channel, and pitch.
- Add a `faithful_transmission` boolean to `process_midi_file(...)`.
  - Default `False` keeps existing fragment extraction behavior.
  - `True` calls the faithful loader, stores the loaded event payload in the
    manifest, sets a manifest mode marker, and does not call
    `extract_midi_fragments(...)`.
- Add a CLI flag `--faithful-transmission` to `cypherclaw-midi-intake`; the
  default dispatch used by `main()` should pass that flag into the intake
  processing path.
- Keep invalid MIDI handling unchanged: rejected files move to `rejected/` and
  do not receive sidecar manifests.
- No new dependency, migration, provider secret, runtime state directory, HTTP
  route, database column, or startup-flow change is required.
- The generated startup identity hardening bullets are regression anchors for
  the existing identity startup subsystem; `midi_intake_daemon.main()` already
  invokes `bootstrap_identity()` before `FirstBootAnnouncer()` and both
  standalone/federated persistence remain covered by existing tests.

## Edge Cases

- Single-track and multi-track MIDI files should produce one globally ordered
  event stream.
- CC, program-change, aftertouch, pitch-bend, sysex, and metadata events should
  be skipped without disrupting parsing.
- Running status should be honored for channel messages.
- Overlapping same-pitch notes on the same channel should pair note-offs with
  note-ons in FIFO order.
- Zero-duration notes are ignored rather than emitted.
- Negative SMPTE-style divisions are accepted as header metadata; faithful
  event durations remain raw tick deltas.
- Malformed or truncated MIDI returns an empty faithful event list when loaded
  directly and falls back to an empty faithful manifest payload if intake
  validation accepted only the header.
- In faithful mode, the manifest keeps the existing empty `fragments` shape so
  downstream readers that expect that key remain compatible.

## Acceptance Criteria

1. The faithful MIDI loader returns ordered JSON-safe `(pitch, duration,
   velocity)` event data from a single-track imported MIDI file, preserving
   source tick durations and velocities.
   - **VERIFY:** `pytest tests/test_midi_faithful_loader.py::test_load_faithful_midi_events_returns_ordered_pitch_duration_velocity -q`

2. The faithful MIDI loader handles multi-track input and skips non-note MIDI
   events while maintaining global note order.
   - **VERIFY:** `pytest tests/test_midi_faithful_loader.py::test_load_faithful_midi_events_merges_tracks_and_ignores_control_data -q`

3. Faithful intake mode writes a processed-file manifest with
   `mode: "faithful_transmission"`, a `faithful_events` list, and empty
   fragments, and it bypasses `extract_midi_fragments(...)`.
   - **VERIFY:** `pytest tests/test_midi_faithful_loader.py::test_process_midi_file_faithful_mode_writes_events_and_bypasses_fragments -q`

4. Default intake behavior remains vocabulary-fragment extraction and does not
   add faithful events unless the mode flag is set.
   - **VERIFY:** `pytest tests/test_midi_faithful_loader.py::test_process_midi_file_default_mode_keeps_fragment_extraction -q`

5. The CLI parser exposes `--faithful-transmission`, and `main()` wires it into
   the default dispatch without changing startup identity ordering.
   - **VERIFY:** `pytest tests/test_midi_faithful_loader.py::test_parse_args_and_main_wire_faithful_transmission_flag -q`

6. Existing MIDI intake, fragment extraction, vocabulary store, and composer
   vocabulary tests remain green.
   - **VERIFY:** `pytest tests/test_midi_intake_daemon.py tests/test_midi_fragment_extractor.py tests/test_midi_vocabulary_store.py tests/test_composer_vocabulary_bridge.py -q`

7. Mandatory startup identity hardening anchors remain covered for startup
   bootstrap, bootstrap-before-announcer ordering, and standalone/federated
   identity persistence.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

8. Product-facing change notes and progress mention faithful-transmission MIDI
   intake.
   - **VERIFY:** `rg -n "faithful-transmission|faithful_transmission|faithful MIDI" CHANGELOG.md progress.md`

9. Full validation passes.
   - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
