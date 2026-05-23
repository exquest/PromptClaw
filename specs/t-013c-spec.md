# Task T-013c Specification: MIDI Intake Manifest Sidecars

## Problem Statement

The MIDI intake daemon already validates incoming `.mid` / `.midi` files and
moves accepted files into `processed/`. The missing behavior for this task is
the intake-pipeline side effect: after a valid MIDI is moved successfully, a
JSON manifest sidecar must be written next to the moved file so downstream
tools can inspect file provenance and basic MThd metadata without reopening the
inbox.

The task prompt's generated startup-hardening bullets target the existing
identity startup subsystem. This checkout already wires
`bootstrap_identity()` before `FirstBootAnnouncer` in the MIDI daemon startup
path, and existing startup identity tests cover persistence between boots in
standalone/federated modes. This task keeps those tests as mandatory
regression anchors rather than broadening MIDI sidecar work into unrelated
startup rewiring.

The active ADP process is the task prompt's Explore -> Specify -> Test ->
Implement -> Verify -> Document workflow.

## Technical Approach

- Reuse the existing `read_mthd_header(...)` and `build_manifest(...)`
  helpers to assemble the sidecar payload from the moved processed file.
- Keep `process_midi_file(...)` as the single file-level pipeline step: it
  validates, computes event metadata, moves to `processed/` or `rejected/`,
  and writes the manifest only for valid processed files.
- Add a small typed `process_intake_cycle(...)` helper that scans one intake
  directory once, waits for stable MIDI files, dispatches each stable path
  through `process_midi_file(...)`, and returns the event records. This gives
  tests and future operators a deterministic one-cycle seam without starting a
  long-running watcher.
- Treat the sidecar name as `<midi filename>.json`, e.g. `take.mid.json`.
  This preserves the full moved filename and supports both `.mid` and
  `.midi` inputs without ambiguity.
- Keep rejected files out of the manifest path: invalid MIDI moves to
  `rejected/` and receives no JSON sidecar.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, or runtime state directories.

## Edge Cases

- Missing intake directory: one-cycle processing returns an empty event list
  via the existing `scan_once(...)` missing-directory behavior.
- Non-MIDI files in intake: ignored by `scan_once(...)`.
- Unstable or disappearing MIDI files: skipped for the cycle and logged as
  `midi_skipped`.
- Invalid MIDI header: moved to `rejected/` with no sidecar.
- Existing processed filename collision: `_unique_destination(...)` selects a
  non-overwriting destination and the sidecar is written for that destination.
- Truncated or unreadable MThd chunk on a file that still starts with `MThd`:
  the file can be processed, but manifest header fields are omitted.

## Acceptance Criteria

1. Dropping a valid MIDI into an intake directory and running one intake cycle
   moves the file to `processed/` and writes a valid JSON sidecar next to it.
   VERIFY: `pytest tests/test_midi_intake_daemon.py::test_process_intake_cycle_moves_valid_midi_and_writes_manifest_sidecar -q`

2. The direct file-level pipeline writes a manifest sidecar for valid MIDI
   files moved to a processed directory.
   VERIFY: `pytest tests/test_midi_intake_daemon.py::test_intake_cycle_produces_manifest_sidecar -q`

3. Rejected MIDI candidates do not receive sidecar manifests.
   VERIFY: `pytest tests/test_midi_intake_daemon.py::test_process_midi_file_skips_manifest_for_rejected_files -q`

4. Manifest content is JSON-serializable and includes filename, UTC timestamp,
   file size, SHA-256, MThd header metadata, and track count when available.
   VERIFY: `pytest tests/test_midi_intake_daemon.py::test_build_manifest_is_json_serializable tests/test_midi_intake_daemon.py::test_build_manifest_includes_all_required_fields -q`

5. Startup identity hardening remains covered for daemon startup ordering and
   standalone/federated identity persistence.
   VERIFY: `pytest tests/test_midi_intake_daemon.py::test_main_invokes_bootstrap_identity tests/test_midi_intake_daemon.py::test_identity_persistence_between_boots tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence -q`

6. Product-facing task notes mention T-013c and record that no new
   dependencies or migrations were introduced.
   VERIFY: `grep -n "T-013c" CHANGELOG.md progress.md ESCALATIONS.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
