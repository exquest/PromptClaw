# Task frac-0066 Specification: test_config Depth 2

## Problem Statement

`tests/test_config.py` is the compact regression suite for PromptClaw's
configuration load/validate path. The production module,
`promptclaw/config.py`, already has meaningful depth-2+ behavior from prior
work: it builds defaults, loads/saves `promptclaw.json`, validates agent and
routing settings, reports enabled agents, emits JSON-safe config summaries,
and returns defaults when a config file is absent.

The remaining gap is the requested affected surface itself:
`sdp.fractal.classify_depth("tests/test_config.py")` reports depth 1 because
the current tests are short smoke checks. This task deepens the test file to a
simple depth-2 end-to-end suite without changing existing assertions or
production behavior unless the new tests expose a real regression.

## Technical Approach

- Preserve the existing `ConfigTests` assertions in `tests/test_config.py`.
- Add a dedicated depth gate at `tests/test_test_config_depth.py` that requires
  `tests/test_config.py` to classify at depth >= 2 and to contain the new
  `ConfigEndToEndTests` class. This provides the red phase before the target
  test file is deepened.
- Append `ConfigEndToEndTests` to `tests/test_config.py` using the existing
  unittest style. The new tests drive one public configuration path end to end:
  default config creation, init-project scaffold output, save/load round trip,
  validation, enabled-agent ordering, status reporting, JSON-safe summaries,
  load-or-default fallback, command-agent persistence, and CLI-compatible
  JSON payload shape.
- Keep all changes stdlib-only. No migrations, new dependencies, provider
  secrets, database columns, runtime state files, or orchestration behavior
  changes are required.
- Treat the generated startup identity hardening bullets as regression
  anchors. Existing startup tests already cover CLI startup bootstrap,
  standalone/federated persistence, bootstrap-before-`FirstBootAnnouncer`
  ordering in both daemon entrypoints, and ASGI import persistence; this task
  re-runs those anchors.

## Edge Cases

- The depth gate asserts `depth >= 2` rather than an exact reason, so future
  improvements that raise the depth remain compatible.
- Because the production config module already classifies at depth 3, this
  task does not add another config helper or alter the on-disk JSON contract.
- Existing test assertions in `tests/test_config.py` remain unchanged; new
  coverage is appended in a separate class.
- `load_or_default` is verified to return defaults without writing a config
  file, then to load the same path after `save_config` writes one.
- Command-agent round-trip coverage uses placeholder commands and test env
  keys only; it does not introduce real provider commands or secrets.

## Acceptance Criteria

1. Existing config smoke tests remain unchanged and green.
   VERIFY: `pytest tests/test_config.py::ConfigTests -q`

2. The new red-phase depth gate confirms `tests/test_config.py` reaches at
   least depth 2 and contains `ConfigEndToEndTests`.
   VERIFY: `pytest tests/test_test_config_depth.py -q`

3. The new end-to-end class covers scaffold load, config save/load,
   validation, status reporting, JSON-safe summaries, load-or-default, command
   agent persistence, and CLI-compatible payload shape through the existing
   public API.
   VERIFY: `pytest tests/test_config.py::ConfigEndToEndTests -q`

4. The config production module remains behavior-compatible with its existing
   depth tests and consumers.
   VERIFY: `pytest tests/test_config.py tests/test_promptclaw_config_depth.py tests/test_bootstrap.py tests/test_doctor.py -q`

5. Startup identity hardening remains covered for first-run identity
   persistence, standalone/federated reuse, CLI startup invocation,
   bootstrap-before-announcer ordering, and ASGI app import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing progress and changelog notes mention the depth-2 config test
   coverage.
   VERIFY: `grep -n "frac-0066" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
