# frac-0034 Spec: Startle Daemon Depth 2

## Problem Statement

`my-claw/tools/startle_daemon.py` is currently a depth-0 script: importing the module starts an infinite loop, all errors are silently swallowed, there is no typed function API to test, and the call into `senseweave.startle.update_startle(state, amp, transient)` passes the room transient bool where a baseline RMS float is expected. The daemon should have one simple working path that reads `/tmp/room_activity.json`, maintains a rolling baseline, runs the existing `update_startle` logic, and writes a JSON state file the rest of the organism (e.g. `inner_life.world_model`) already consumes.

## Technical Approach

- Keep the existing `senseweave.startle` detection module unchanged; only deepen the daemon shell around it.
- Replace the top-level `while True` loop with import-safe typed helpers:
  - `read_room_activity(...)` loads one JSON object from the room-activity path.
  - `amp_from_room(...)` returns the `max(window_mic_amp, cypherclaw_mic_amp)` reading.
  - `update_baseline(history, amp, *, window=...)` returns a new bounded baseline history.
  - `baseline_value(history, *, floor=...)` returns the median amplitude with a non-zero floor so `update_startle` can compare against a real baseline RMS.
  - `render_output(...)` builds the JSON payload (`startled`, `startle_count`, `cooldown_active`, `face_reaction`, `should_mute`, `baseline`, `amp`, `timestamp`) consumed by `inner_life.world_model.poll_state`.
  - `write_output(...)` atomically writes the payload via a `.tmp` rename.
  - `process_once(...)` reads, updates the baseline, calls `update_startle`, writes the output, and returns the new daemon state plus the rendered payload.
  - `run_daemon(...)` repeats `process_once(...)` and supports `max_iterations` for tests.
- Add a small CLI entry point with `--once`, `--interval`, `--room-path`, `--state-path`.
- Preserve the one-path scope: a single rolling-median baseline, the existing `update_startle` rule set, and the existing `/tmp/startle_state.json` consumer contract (`startled`, `startle_count`, `cooldown_active`, `face_reaction`, `timestamp`).

## Edge Cases

- Missing, corrupt, or non-object room-activity JSON produces a quiet (zero-amp) snapshot and does not crash the loop.
- Missing `window_mic_amp` / `cypherclaw_mic_amp` keys default to `0.0`.
- A first cycle has an empty baseline history; `baseline_value` returns the configured floor so `update_startle` sees a real positive baseline rather than dividing by zero.
- Repeated identical loud cycles still respect the existing `senseweave.startle` cooldown and `should_mute_output` window logic — the daemon does not introduce its own duplicate suppression.
- Startup identity hardening is not changed by this task; existing tests verify first-boot persistence and bootstrap-before-announcer ordering for standalone and federated startup paths.

## Acceptance Criteria

1. The daemon module is import-safe and exposes a typed function API.
   - **VERIFY:** `pytest tests/test_startle_daemon.py::test_module_import_is_side_effect_free -q`

2. `amp_from_room` and the baseline helpers produce meaningful values from a fused room-activity payload.
   - **VERIFY:** `pytest tests/test_startle_daemon.py::test_amp_and_baseline_helpers_produce_meaningful_values -q`

3. One processing cycle converts a loud room reading into a written startle JSON payload that surfaces the surprise face reaction and increments the startle count.
   - **VERIFY:** `pytest tests/test_startle_daemon.py::test_process_once_writes_startled_state_for_loud_room -q`

4. The daemon loop runs the configured number of iterations and writes a quiet payload when the room is silent.
   - **VERIFY:** `pytest tests/test_startle_daemon.py::test_run_daemon_writes_quiet_state_for_silent_room -q`

5. Existing `senseweave.startle` behavior remains intact.
   - **VERIFY:** `pytest tests/test_startle.py tests/test_startle_daemon.py -q`

6. Startup identity hardening remains explicitly covered for first-boot identity persistence, standalone/federated modes, and bootstrap-before-announcer wiring.
   - **VERIFY:** `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

7. Required validation passes with no new dependency or migration.
   - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
