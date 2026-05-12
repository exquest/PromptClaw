# frac-0033 Spec: Sensory Journal Daemon Depth 2

## Problem Statement

`my-claw/tools/sensory_journal_daemon.py` is currently a depth-0 script: import starts an infinite loop, all errors are swallowed, there are no typed functions to test, and calls into `senseweave.sensory_journal.log_event(...)` do not match the journal API. The daemon should have one simple working path that reads the fused organism state, detects meaningful sensory transitions, writes JSONL journal entries, and can run end-to-end under tests.

## Technical Approach

- Keep the existing durable journal implementation in `my-claw/tools/senseweave/sensory_journal.py`.
- Replace the top-level loop with import-safe typed helpers:
  - `read_fused_state(...)` loads one JSON object from the fused state path.
  - `snapshot_from_state(...)` normalizes Theramini, room, and mood fields.
  - `events_from_snapshots(...)` emits one ordered list of journal event specs.
  - `process_once(...)` reads, detects, writes, and returns the new snapshot plus written entries.
  - `run_daemon(...)` repeats `process_once(...)`, carrying the previous snapshot to avoid duplicate edge events.
- Add a small CLI entry point with `--once`, `--interval`, `--fused-path`, and `--journal-path`.
- Preserve the one-path scope: Theramini start, room transient, and mood energy shift are the only event classes.

## Edge Cases

- Missing, corrupt, or non-object fused state produces no events and does not crash the loop.
- Missing nested state sections use defaults: Theramini not playing, room quiet/no transient, mood energy `0.5`.
- A first cycle compares against the same neutral defaults so active startup state still creates meaningful events.
- Repeated identical active state does not duplicate Theramini start, room transient, or mood-shift entries on the next loop iteration.
- Startup identity hardening is not changed by this task; existing tests verify first-boot persistence and bootstrap-before-announcer ordering for standalone and federated startup paths.

## Acceptance Criteria

1. The daemon module is import-safe and exposes a typed function API.
   - **VERIFY:** `pytest tests/test_sensory_journal_daemon.py::test_module_import_is_side_effect_free -q`

2. One processing cycle converts a fused organism state into meaningful Theramini, room, and mood journal entries.
   - **VERIFY:** `pytest tests/test_sensory_journal_daemon.py::test_process_once_reads_fused_state_and_appends_meaningful_events -q`

3. The daemon loop carries previous state and suppresses duplicate edge-triggered events across repeated active cycles.
   - **VERIFY:** `pytest tests/test_sensory_journal_daemon.py::test_run_daemon_carries_previous_snapshot_between_cycles -q`

4. Existing sensory journal behavior remains intact.
   - **VERIFY:** `pytest tests/test_sensory_journal.py tests/test_sensory_journal_daemon.py -q`

5. Startup identity hardening remains explicitly covered for first-boot identity persistence, standalone/federated modes, and bootstrap-before-announcer wiring.
   - **VERIFY:** `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

6. Required validation passes with no new dependency or migration.
   - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
