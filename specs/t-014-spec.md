# T-014 Spec: MIDI Fragment Extraction

## Problem Statement

CypherClaw's MIDI intake path currently validates incoming MIDI files, moves
valid files to `processed/`, and writes sidecar manifests with header-level
metadata. It does not yet mine the musical vocabulary inside each MIDI file.
T-014 adds a deterministic fragment extractor so every processed MIDI sidecar
can describe melodic motifs, rhythm cells, chord progressions, and drum-groove
patterns from the source file.

## Technical Approach

- Extend `src/cypherclaw/midi_intake_daemon.py`, the existing MIDI intake
  boundary, instead of adding a separate service.
- Keep the implementation stdlib-only. Although the product PRD mentions
  `mido`, it is not a direct project dependency; this task should not add a
  dependency for hand-crafted unit-test MIDIs.
- Parse enough Standard MIDI File structure for extraction:
  - `MThd` header and `MTrk` track chunks.
  - Variable-length delta times.
  - Running status.
  - Channel note on/off events, with velocity-zero note-on treated as note-off.
  - Meta tempo/time-signature events when present, with 4/4 defaults.
  - Unknown MIDI/meta/sysex events skipped safely.
- Expose a typed public helper:
  - `extract_midi_fragments(path) -> dict[str, object]`
  - The returned dict has JSON-safe keys:
    `melodic_motifs`, `rhythm_cells`, `chord_progressions`,
    `groove_patterns`.
- Melodic motifs:
  - Extract sliding windows of 3 to 7 non-drum notes from each track/channel.
  - Ignore windows with duplicate onset ticks so block chords do not become
    melody.
  - Include `notes`, `pitch_classes`, `interval_pattern`, `contour`,
    `duration_ticks`, `duration_ratios`, `start_tick`, `track`, and `channel`.
- Rhythm cells:
  - Extract sliding windows of 3 to 7 non-drum notes from each track/channel.
  - Keep cells with non-uniform durations or onset deltas.
  - Include `duration_ticks`, `duration_ratios`, `onset_delta_ticks`,
    `onset_delta_ratios`, `start_tick`, `track`, and `channel`.
- Chord progressions:
  - Group non-drum notes by shared onset tick.
  - Treat groups with at least three distinct pitch classes as chords.
  - Identify common triad quality (`major`, `minor`, `diminished`,
    `augmented`, `sus2`, `sus4`) by testing pitch-class intervals from likely
    roots.
  - Return one progression containing ordered `symbols`, `roots`, `qualities`,
    `start_ticks`, and chord details when at least two chords are found.
- Groove patterns:
  - Treat MIDI channel 10 (zero-based channel `9`) as drums.
  - Normalize drum onsets to beat/bar positions using the parsed division and
    time signature.
  - Map common GM drum notes to roles such as `kick`, `snare`, and `hihat`.
  - Include `drum_notes`, `drum_roles`, `pattern`, `beat_positions`,
    `bar_positions`, `track`, and `channel`.
- Sidecar integration:
  - `process_midi_file(...)` extracts fragments for valid MIDI files before
    writing the processed-file manifest.
  - `build_manifest(...)` includes a JSON-safe `fragments` block. Header-only
    or fragmentless valid MIDI files get empty fragment lists.
  - Rejected files still do not get sidecar manifests.

## Edge Cases

- Header-only files that pass the current `MThd` validation return empty
  fragment lists instead of failing intake.
- Truncated, malformed, or chunkless files return empty fragment lists when
  called directly; intake still uses the existing processed/rejected routing.
- Running status is supported for hand-authored compact MIDI tracks.
- Overlapping repeated notes close in FIFO order.
- Unclosed notes at track end are ignored for fragment mining rather than
  fabricating durations.
- SMPTE division values are treated as unsupported for beat normalization; tick
  extraction still works and groove beat positions fall back to zero-safe
  defaults.
- No database migrations, schema changes, provider secrets, runtime state
  directories, HTTP routes, or startup flow changes are required.
- The auto-generated startup hardening items are unrelated to fragment mining.
  Existing daemon/narrative startup identity tests remain mandatory regression
  anchors.

## Acceptance Criteria

1. Hand-crafted monophonic MIDI files produce melodic motifs of 3 to 7 notes,
   including interval pattern, contour, and duration-ratio metadata.
   - **VERIFY:**
     `pytest tests/test_midi_fragment_extractor.py::test_extracts_melodic_motifs_and_rhythm_cells_from_handcrafted_midi -q`

2. Hand-crafted MIDI files with non-uniform note lengths produce rhythm cells
   with duration and onset-delta patterns.
   - **VERIFY:**
     `pytest tests/test_midi_fragment_extractor.py::test_extracts_melodic_motifs_and_rhythm_cells_from_handcrafted_midi -q`

3. Hand-crafted block-chord MIDI files produce a chord progression with ordered
   root, quality, symbol, and onset metadata.
   - **VERIFY:**
     `pytest tests/test_midi_fragment_extractor.py::test_extracts_chord_progression_from_block_chords -q`

4. Hand-crafted drum MIDI files on channel 10 produce a normalized groove
   pattern with drum roles and beat/bar positions.
   - **VERIFY:**
     `pytest tests/test_midi_fragment_extractor.py::test_extracts_groove_pattern_from_channel_ten_drums -q`

5. Processed valid MIDI sidecar manifests include the extracted fragment block,
   while rejected files continue to omit sidecars.
   - **VERIFY:**
     `pytest tests/test_midi_fragment_extractor.py::test_process_midi_file_writes_fragments_into_manifest -q`
   - **VERIFY:**
     `pytest tests/test_midi_intake_daemon.py::test_process_midi_file_skips_manifest_for_rejected_files -q`

6. Startup identity hardening remains covered for bootstrap-before-announcer
   ordering and standalone/federated identity persistence.
   - **VERIFY:**
     `pytest tests/test_midi_intake_daemon.py::test_main_invokes_bootstrap_identity tests/test_midi_intake_daemon.py::test_identity_persistence_between_boots tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

7. Required validation passes with no new dependency or migration.
   - **VERIFY:**
     `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
