# Verification Report — T-017b

**Verify Agent:** Verify-T-017b (Claude Sonnet 4.6)
**Date:** 2026-05-22
**Artifacts Reviewed:**
- `src/cypherclaw/midi_scene.py` (new, 218 lines)
- `src/cypherclaw/midi_intake_daemon.py` (modified)
- `tests/test_midi_scene.py` (new, 237 lines)
- `specs/t-017b-spec.md`
- `CHANGELOG.md`, `progress.md`, `docs/handoff-protocol.md`, `ESCALATIONS.md`

## Correctness

Implementation matches the spec exactly. `build_faithful_midi_scene` produces a
`FaithfulMidiScene` with one `faithful_midi` melody lane containing ordered
`FaithfulSceneStep` records preserving exact `pitch`, `duration_ticks`, and
cumulative `row` offsets. Velocity is normalized to `[0.0, 1.0]` with original
value retained in per-step metadata. Scene metadata carries `mode:
faithful_transmission`, `source_transform: midi_whole_file_scene`,
`source_event_count`, and `source_duration_ticks` — no vocabulary fragment keys
present anywhere in the payload.

`process_midi_file(..., faithful_transmission=True)` now calls
`build_faithful_midi_scene` on the loaded faithful events and writes the result
into the manifest under `faithful_scene`. `fragments` remains the empty
structure. Default (fragment-extraction) mode is unchanged and never writes
`faithful_scene`. The test for default mode monkeypatches
`extract_midi_fragments` to confirm the vocabulary path is still exercised and
that `faithful_scene` is absent.

All four AC-verified test cases pass. Row arithmetic confirmed: with
`ticks_per_beat=120` and `rows_per_beat=4`, a 120-tick note → 4 rows; a 240-tick
note → 8 rows; cumulative rows are `[0, 4, 12]` matching the spec.

## Completeness

All spec-specified edge cases are covered and tested:

- **Empty input:** returns a scene with one lane, zero steps, `rows=0`,
  `source_event_count: "0"`, no fragment keys.
- **Non-positive durations:** skipped in the builder loop; malformed events
  cannot produce zero-length steps.
- **`ticks_per_beat <= 0`:** `_duration_to_rows` falls back to `rows_per_beat`
  as denominator, preventing division by zero.
- **`rows_per_beat <= 0`:** `safe_rows_per_beat = max(1, int(rows_per_beat))`
  ensures minimum of 1.
- **Velocity out of range:** `_clamp_int(value, 0, 127)` before normalization.
- **Malformed faithful files:** header-only valid files load empty event list →
  empty faithful scene, no fragment extraction.

The `_int_metadata` helper in `midi_intake_daemon.py` handles int/str/other
`division` values from the parsed MIDI header, preventing a type error when
`ticks_per_beat` arrives as a string.

## Consistency

- Frozen dataclasses with `to_dict()` methods follow the same pattern used
  throughout the MIDI subsystem (e.g. `FaithfulMidiEvent`).
- Dual-import fallback (`cypherclaw.midi_scene` / `midi_scene`) is consistent
  with T-017a's `midi_loader` and the rest of the daemon's import block.
- `_int_metadata` is a local private helper — no leakage into the public API.
- CHANGELOG entry, `progress.md` status, and `docs/handoff-protocol.md`
  all reference `T-017b`, `faithful_scene`, and `midi_whole_file_scene`.

## Security

- No shell execution, no eval, no dynamic imports.
- All user-supplied values are type-converted defensively before use.
- No new HTTP routes, database migrations, provider secrets, or state directories
  added (confirmed by spec and diff review).
- No secrets in any committed file.

## Quality

Full suite results:

| Suite | Result |
|---|---|
| `tests/test_midi_scene.py` (4 tests) | 4 passed |
| Adjacent MIDI + composer vocabulary (67 tests) | 67 passed |
| Startup identity hardening anchors (11 tests) | 11 passed |
| Full `pytest tests/ -x` | **4960 passed, 11 skipped** |
| `ruff check src/ tests/` | All checks passed |
| `mypy src/` | No issues found in 41 source files |

**Hardening checks (from candidate hardening bullets):**

1. *"Runtime does not invoke bootstrap_identity on startup"* — `midi_intake_daemon.main()` already calls `bootstrap_identity()` before `FirstBootAnnouncer()`. Confirmed by startup identity hardening anchor tests (11 passed). **CLEAR.**
2. *"Add bootstrap_identity() invocation in startup flow"* — Already wired; no change needed. **CLEAR.**
3. *"Ensure this path is used on both standalone and federated modes"* — `TestStartupIdentityPersistence` and `TestStartupIdentityModePersistence` both pass. **CLEAR.**
4. *"Add integration test: startup + identity persistence between boots"* — `test_asgi_module_startup_bootstraps_identity_persistence_between_imports` passes. **CLEAR.**
5. *"Re-run pip install -e '.[dev]' && pytest tests/ -x after wiring"* — 4960 tests pass. **CLEAR.**

## Issues Found

None.

## Verdict: PASS

## Notes for Lead Agent

No items to address. All acceptance criteria met, all hardening anchors confirmed,
full suite green, linting and typing clean.
