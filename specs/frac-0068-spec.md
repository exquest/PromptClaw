# Task frac-0068 Specification: test_contact_mic_calibration_runtime Depth 2

## Problem Statement

`tests/test_contact_mic_calibration_runtime.py` is the regression suite for
the contact-mic calibration harness in
`my-claw/tools/contact_mic_calibration.py`. The production harness already
implements the one-path runtime contract documented in
`docs/contact-mic-calibration-protocol.md`: default capture scenarios,
16-bit PCM WAV analysis, ALSA device parsing, capture bundle writing, and CLI
entry points for list, analyze, and run.

The requested affected surface is the test file itself. This task deepens the
runtime test from depth 1 to depth 2 by adding end-to-end coverage that proves
the public harness functions produce meaningful output and that the simple
capture/analyze/run path works without touching live audio hardware.

## Technical Approach

- Preserve every existing assertion in `tests/test_contact_mic_calibration_runtime.py`.
- Add a red-phase depth gate at
  `tests/test_test_contact_mic_calibration_runtime_depth.py` requiring the
  runtime test file to classify at depth >= 2 and to contain the new
  `ContactMicCalibrationEndToEndTests` class.
- Append `ContactMicCalibrationEndToEndTests` to the runtime test file using
  pytest style. The class exercises:
  - multi-window WAV analysis with channel labels, activity counts, activation
    ratios, and JSON-safe report shape;
  - full calibration bundle writing with a fake capture backend, per-scenario
    JSON reports, `summary.json`, and backend call metadata;
  - CLI `list-scenarios` and `analyze` JSON output through `main()`;
  - ALSA parsing across multiple devices and fallback behavior for missing
    preferred devices.
- Keep all tests stdlib-only and hardware-free. The fake backend writes WAV
  files directly and no external commands or devices are invoked.
- Treat the generated startup identity hardening checks as regression anchors.
  Current startup docs and tests already cover `bootstrap_identity()` before
  `FirstBootAnnouncer`, standalone/federated persistence, CLI startup
  invocation, and ASGI import persistence, so this task re-runs those anchors
  rather than changing startup code.

## Edge Cases

- Empty or missing preferred ALSA devices should return `None` without raising.
- CLI JSON paths must emit parseable JSON to stdout and return status code 0.
- The end-to-end bundle test verifies both the in-memory manifest and the files
  written to disk so a future regression cannot pass by returning only a Python
  object.
- Existing test assertions remain locked after the red phase; all new coverage
  is appended in a separate class.
- No migrations, dependencies, provider secrets, database columns, runtime
  state files, HTTP routes, or auth behavior are introduced.

## Acceptance Criteria

1. Existing contact-mic runtime tests remain unchanged and green.
   VERIFY: `pytest tests/test_contact_mic_calibration_runtime.py::test_required_scenarios_match_protocol_defaults tests/test_contact_mic_calibration_runtime.py::test_analyze_wav_reports_channel_metrics_and_activity tests/test_contact_mic_calibration_runtime.py::test_run_calibration_writes_summary_bundle tests/test_contact_mic_calibration_runtime.py::test_parse_arecord_device_lines_finds_scarlett_address -q`

2. The red-phase depth gate confirms
   `tests/test_contact_mic_calibration_runtime.py` reaches at least depth 2
   and contains `ContactMicCalibrationEndToEndTests`.
   VERIFY: `pytest tests/test_test_contact_mic_calibration_runtime_depth.py -q`

3. The new end-to-end class covers meaningful WAV analysis, calibration bundle
   writing, CLI JSON output, and ALSA parsing/fallback behavior through the
   existing public API.
   VERIFY: `pytest tests/test_contact_mic_calibration_runtime.py::ContactMicCalibrationEndToEndTests -q`

4. The calibration harness remains behavior-compatible with the product docs
   and existing runtime tests.
   VERIFY: `pytest tests/test_contact_mic_calibration_runtime.py -q`

5. Startup identity hardening remains covered for first-run identity
   persistence, standalone/federated reuse, CLI startup invocation,
   bootstrap-before-announcer ordering, and ASGI app import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing progress and changelog notes mention the depth-2 contact-mic
   runtime test coverage.
   VERIFY: `grep -n "frac-0068" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
