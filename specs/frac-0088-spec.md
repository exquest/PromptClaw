# Task frac-0088 Specification: test_midi_state Depth 2

## Problem Statement

`tests/test_midi_state.py` exercises the MIDI input state tracker
`my-claw/tools/senseweave/midi_state.py` at the function level: the
constructor's initial values, `note_on`/`note_off`, `control_change` for
mod-wheel/sustain/volume, `pitch_bend_change`, `activity_rate`, the `to_dict`
/`from_dict` round trip, and `note_to_name`/`name_to_note` conversion.

The production module already exposes the depth-2 surface needed to run a
single end-to-end MIDI session through the tracker: chord notes can be held
while a pedal is engaged, mod wheel and pitch bend can be moved, expression
and volume CCs can land, the snapshot is JSON-safe via `to_dict()`, and the
snapshot can be re-hydrated through `from_dict()` so downstream consumers
(`my-claw/tools/midi_keyboard_listener.py`, `harmonic_planner.py`) can rely
on the published shape.

The missing work for frac-0088 is to deepen the test file itself from
function-level checks to a named end-to-end test class proving the public
MIDI tracker surface threads a realistic note-and-controller sequence into a
JSON-safe snapshot in one deterministic path, and to pin that depth with a
machine-verifiable gate.

The generated startup identity hardening bullets are already represented in
this checkout by CLI, daemon-ordering, first-boot persistence, and narrative
ASGI startup tests. This task treats those as regression anchors rather than
changing unrelated startup flow without a concrete gap.

## Technical Approach

- Add a deterministic depth gate at
  `tests/test_test_midi_state_depth.py` that requires
  `tests/test_midi_state.py` to contain `MidiStateEndToEndTests` and classify
  at depth >= 2 through the repo-local `sdp.fractal.classify_depth`.
- Append `MidiStateEndToEndTests` to `tests/test_midi_state.py`. The class
  uses `__test__ = True` so the depth gate's class-name lookup matches the
  pytest discovery name.
- Exercise one public end-to-end path through `MidiState`:
  - Drive a realistic chord-with-controllers sequence (chord on, pedal on,
    mod wheel, pitch bend, expression, volume, velocity-zero release, final
    note off).
  - Confirm aggregate state on the live tracker (notes held, last note,
    sustain, mod wheel, pitch bend, expression, volume, activity rate > 0).
  - Confirm `to_dict()` produces a JSON-safe snapshot whose `notes_on` is a
    sorted list (not a set) and that round-trips through
    `json.dumps`/`json.loads` and `MidiState.from_dict(...)` while preserving
    the live state.
  - Confirm `note_to_name`/`name_to_note` agree with the snapshot's
    `last_note` and that the chord round-trips through both helpers.
- Preserve existing assertions and production behavior unless the new tests
  expose a concrete implementation gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state files, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end sequence intentionally covers the simple happy path: chord
  held, pedal engaged, controllers moved, one note released via velocity 0,
  then the remaining notes released via explicit `note_off`.
- Existing focused tests remain responsible for individual CC threshold
  checks, no-op `note_off` of an unheld note, unknown CC pass-through, pitch
  bend boundary values, and full `note_to_name`/`name_to_note` round-trips
  across all 128 MIDI numbers.
- Snapshot output must remain JSON-safe so the listener daemon and harmonic
  planner can serialize it without custom encoders.
- Startup identity hardening remains scoped to the existing startup test
  anchors for CLI startup, daemon ordering, standalone/federated persistence,
  and ASGI import persistence.

## Acceptance Criteria

1. Existing midi-state assertions remain green.
   VERIFY: `pytest tests/test_midi_state.py -q`

2. The depth gate confirms `tests/test_midi_state.py` reaches depth >= 2 and
   contains `MidiStateEndToEndTests`.
   VERIFY: `pytest tests/test_test_midi_state_depth.py -q`

3. `MidiStateEndToEndTests` drives one meaningful public path through chord
   tracking, control-change handling, pitch bend, JSON-safe snapshot
   serialization, `from_dict` round trip, and `note_to_name` /
   `name_to_note` integration.
   VERIFY: `pytest tests/test_midi_state.py::MidiStateEndToEndTests -q`

4. Existing midi keyboard listener runtime coverage remains green so the
   downstream consumer of `MidiState` is not regressed.
   VERIFY: `pytest tests/test_midi_keyboard_listener_runtime.py -q`

5. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing task notes mention the frac-0088 midi-state test
   deepening.
   VERIFY: `grep -n "frac-0088" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
