# Verification Report — T-014

**Verify Agent:** Claude Sonnet 4.6 (VERIFY)
**Date:** 2026-05-22
**Artifacts Reviewed:**
- `specs/t-014-spec.md`
- `src/cypherclaw/midi_fragments.py` (495 lines, new)
- `src/cypherclaw/midi_intake_daemon.py` (patch: fragment extraction wiring)
- `tests/test_midi_fragment_extractor.py` (161 lines, new)
- `tests/test_midi_intake_daemon.py` (patch: skips-manifest test)
- `ESCALATIONS.md`

## Correctness

All five acceptance criteria pass on live test runs:

1. **Melodic motifs** — `test_extracts_melodic_motifs_and_rhythm_cells_from_handcrafted_midi` PASS. Hand-crafted monophonic MIDI yields motifs with correct `notes`, `pitch_classes`, `interval_pattern`, `contour`, and `duration_ratios`.
2. **Rhythm cells** — same test, same file. Non-uniform durations produce cells; the uniform-filter (`set(durations) <= 1 and set(onset_deltas) <= 1`) correctly excludes perfectly uniform passages.
3. **Chord progressions** — `test_extracts_chord_progression_from_block_chords` PASS. C/F/G/C block chords resolve to correct symbols, roots, qualities, and start ticks.
4. **Groove patterns** — `test_extracts_groove_pattern_from_channel_ten_drums` PASS. Channel-9 drum notes map to `kick-hihat-snare-hihat` with correct beat/bar positions at 480 ppq.
5. **Sidecar integration** — `test_process_midi_file_writes_fragments_into_manifest` and `test_process_midi_file_skips_manifest_for_rejected_files` both PASS. Fragments appear in valid-file manifests; rejected files produce no sidecar.

Fragment extraction is placed in `process_midi_file` before the file is moved, reading from the source path while it still exists — ordering is correct.

## Completeness

Spec edge cases are handled:

- **Header-only / no track data** — `_parse_midi_file` returns `ParsedMidi` with an empty notes tuple; all four extractors return empty lists.
- **Truncated / malformed bytes** — parser returns `None` → `empty_midi_fragments()`.
- **Running status** — implemented in `_parse_track`; byte-level logic correctly distinguishes status bytes from data bytes and carries `running_status` forward.
- **Velocity-zero note-on as note-off** — handled in `event_type == 0x90 and data2 == 0` branch.
- **Overlapping repeated notes** — `active` dict holds a list per `(channel, note)` and pops FIFO on note-off, matching spec requirement.
- **Unclosed notes at track end** — `active` entries not closed are simply discarded; no fabricated durations.
- **SMPTE division** — guard `0 < division < 0x8000` applied in `_extract_groove_patterns` and `_bar_ticks`; beat positions fall back to 0.0.
- **Startup identity hardening** — `test_main_invokes_bootstrap_identity` and `test_identity_persistence_between_boots` both PASS. The spec explicitly notes these hardening bullets are unrelated to fragment mining; the daemon's existing startup order (`bootstrap_identity` before `FirstBootAnnouncer`) is verified and untouched.

No gaps in coverage identified relative to the spec.

## Consistency

- Implementation uses stdlib only (`collections`, `dataclasses`, `pathlib`) — no new dependencies added.
- `midi_fragments.py` is imported via try/except fallback matching the pattern used for `first_boot` and other sibling modules.
- Public API shape (`extract_midi_fragments → dict[str, object]`) matches spec exactly.
- `build_manifest` fallback (`empty_midi_fragments()` when no `fragments` key in metadata) preserves backward compatibility for callers that don't supply fragment metadata.
- File naming (`<basename>.mid.json`) consistent with prior sidecar convention from T-013c.
- Ruff clean, mypy clean, no type errors.

## Security

- `_parse_midi_file` limits varlen decode to 4 bytes per value, preventing unbounded loops on crafted input.
- `chunk_end > len(data)` guard prevents out-of-bounds reads on truncated chunks.
- No shell invocations, no user-supplied paths reaching `eval` or `exec`, no secrets involved.
- File writes limited to the already-established `processed/` sidecar convention.
- No new runtime state directories, HTTP routes, or external network calls.

## Quality

- 4941 tests pass, 11 skipped, 0 failures across the full suite.
- Ruff: all checks passed.
- mypy: no issues found in 37 source files.
- Test file uses a hand-rolled varlen encoder and MIDI writer (no mido dependency) consistent with spec's stdlib-only mandate.
- `_note_windows` correctly generates all windows of length 3–7 as sliding subsets rather than fixed partitions, producing overlapping motif coverage.

## Issues Found

None.

## Verdict: PASS

## Notes for Lead Agent

No action required. All acceptance criteria verified green. The startup identity regression anchors (`test_main_invokes_bootstrap_identity`, `test_identity_persistence_between_boots`) pass; the candidate hardening bullets in the task prompt are correctly addressed by pre-existing code and tests, consistent with the spec's explicit note that they are unrelated to fragment mining.
