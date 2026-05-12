# frac-0036 Spec: Theramini MIDI Depth 2

## Problem Statement

`my-claw/tools/theramini_midi.py` is currently a depth-1 script
(`3/4 trivial, 1 real`, 122 lines): the only "real" function is the monolithic
`run()` loop, which mixes device opening, raw MIDI byte parsing, note/CC/pitch
bookkeeping, JSON rendering, and the sleep loop in one body. There is no typed
function API to test the parsing logic against, so the module has zero direct
test coverage and the duet pipeline can only validate it end-to-end on real
hardware.

This task deepens the module to a simple depth-2 implementation by extracting
typed, stdlib-only helpers for the parser and the per-cycle update path while
preserving the existing `/tmp/theramini_state.json` consumer contract that
`senseweave.theramini_duet.normalize_theramini_state` and
`tests/test_theramini_listener_runtime.py` already rely on.

## Technical Approach

- Keep `senseweave.theramini_duet.normalize_theramini_state` and the existing
  `/tmp/theramini_state.json` field contract (`timestamp`, `is_playing`,
  `pitch_hz`, `pitch_note`, `pitch_confidence`, `state`,
  `consecutive_silence_ms`, `midi_cc`, `pitch_bend`) unchanged.
- Replace the single `run()` body with import-safe typed helpers:
  - `midi_to_freq(note)` and `midi_to_name(note)` retained as pure helpers.
  - `MidiEvent` frozen dataclass for one parsed MIDI message
    (`kind: Literal["note_on", "note_off", "cc", "pitch_bend"]`,
    `data1: int`, `data2: int`).
  - `MidiState` dataclass holding current note, last-note timestamp,
    silence-start timestamp, CC map, and pitch-bend value.
  - `parse_midi_messages(buf)` returns `(events, remaining_buf)` from a raw
    MIDI byte buffer, skipping non-status bytes and handling 2-byte
    program/aftertouch messages.
  - `apply_midi_event(state, event, now)` returns a new `MidiState` after
    applying one parsed event (note on/off/CC/pitch-bend).
  - `process_buffer(state, buf, now)` parses any complete events out of `buf`
    and returns the updated state plus the remaining bytes.
  - `render_state(state, now)` returns the JSON payload after
    `normalize_theramini_state`, including `is_playing` derived from the
    same `now - last_note_time < 2.0` rule the current `run()` uses.
  - `write_state(payload, state_path)` atomically writes the rendered payload
    via a `.tmp` rename (preserving the existing consumer contract).
  - `read_midi_buffer(fd, size)` does one non-blocking `os.read`, returning
    `b""` on `BlockingIOError`/`OSError`.
  - `process_once(state, fd, buf, *, now=None, state_path=...)` reads new
    MIDI bytes, runs `process_buffer`, writes the rendered state, and
    returns `(new_state, remaining_buf, payload)`.
  - `run_daemon(*, device, interval, max_iterations, state_path)` opens the
    MIDI device (or writes the `no_device` fallback payload when it can't),
    then loops `process_once` with `max_iterations` for tests.
- Add a `main(argv)` CLI entry point with `--device`, `--interval`,
  `--state-path`, `--once`, and `--max-iterations`.
- Type hints on all new function signatures. No new dependencies, migrations,
  provider secrets, database columns, or agent commands are introduced.

## Edge Cases

- A buffer shorter than 3 bytes is left intact for the next read.
- A non-status byte at `buf[0]` is dropped one byte at a time until a status
  byte is found.
- `Note On` with velocity `0` is treated as a `Note Off` for the matching
  note (existing behavior).
- A `Note Off` for a note that is not currently held leaves `current_note`
  unchanged; `silence_start` is set the first time silence begins.
- Program change (`0xC0`) and channel pressure (`0xD0`) consume two bytes.
- Missing or unopenable MIDI devices produce the existing `state="no_device"`
  payload at the same shape (`is_playing=False`, `pitch_hz=None`,
  `consecutive_silence_ms` ticking from the daemon start).
- `is_playing` decays to `False` after `2.0` seconds without a fresh note,
  matching the current `run()` rule.

## Acceptance Criteria

1. The module is import-safe and exposes the typed function API.
   - **VERIFY:** `pytest tests/test_theramini_midi.py::test_module_import_is_side_effect_free -q`

2. `parse_midi_messages` and `apply_midi_event` produce meaningful events
   from a raw byte buffer and update `MidiState` accordingly.
   - **VERIFY:** `pytest tests/test_theramini_midi.py::test_parse_and_apply_midi_events -q`

3. `process_buffer` and `render_state` translate a Note On stream into a
   JSON payload that surfaces `is_playing=True`, the right pitch
   frequency/note name, and the conversation contract added by
   `normalize_theramini_state`.
   - **VERIFY:** `pytest tests/test_theramini_midi.py::test_render_state_for_active_note -q`

4. After the configured silence window, `render_state` reports
   `is_playing=False`, increasing `consecutive_silence_ms`, and the
   conversation phase falls back to `listening`.
   - **VERIFY:** `pytest tests/test_theramini_midi.py::test_render_state_for_silent_window -q`

5. `process_once` reads from a MIDI file descriptor end-to-end and writes the
   payload atomically to the state path.
   - **VERIFY:** `pytest tests/test_theramini_midi.py::test_process_once_writes_state_for_note_on -q`

6. `run_daemon` writes the existing `no_device` fallback payload when the
   MIDI device cannot be opened, matching the current consumer contract.
   - **VERIFY:** `pytest tests/test_theramini_midi.py::test_run_daemon_writes_no_device_state -q`

7. Fractal depth for `my-claw/tools/theramini_midi.py` reaches at least
   depth 2.
   - **VERIFY:** `pytest tests/test_theramini_midi.py::test_theramini_midi_reaches_depth_two -q`

8. Existing theramini listener and duet behavior remain intact.
   - **VERIFY:** `pytest tests/test_theramini_listener_runtime.py tests/test_theramini_duet.py -q`

9. Startup identity hardening remains explicitly covered for first-boot
   identity persistence, standalone/federated modes, and
   bootstrap-before-announcer wiring.
   - **VERIFY:** `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

10. Required validation passes with no new dependency or migration.
    - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
