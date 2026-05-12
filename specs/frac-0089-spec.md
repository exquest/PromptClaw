# Task frac-0089 Specification: test_mix_verify Depth 2

## Problem Statement

`tests/test_mix_verify.py` already exercises the public
`my-claw/tools/senseweave/mix_verify.py` verification helpers at the function
and focused integration level: peak/RMS dBFS measurement, LUFS proxy
estimation, clipping/silence checks, harshness and low-end proxies,
frequency-lane masking, mix-profile/mastering-policy validation, render
loudness checks, master-bus safety, and per-note EMSD render shaping.

The missing work for frac-0089 is to make the depth-2 contract explicit: the
test file should contain a named end-to-end class that drives one realistic
mix verification path from mix-profile construction through synthetic render
generation, profile verification, loudness measurement, clipping/silence,
low-end, harshness, masking, and JSON-safe diagnostic output. A companion
depth gate should pin that class and the repo-local fractal classifier.

The production module already implements meaningful one-path outputs for this
scope, so no production behavior change is expected unless the new tests expose
a concrete gap.

The generated startup identity hardening bullets target the existing startup
identity subsystem. This checkout already documents and tests CLI startup,
daemon bootstrap-before-`FirstBootAnnouncer` ordering, standalone/federated
identity persistence, and narrative ASGI import persistence. This task keeps
those tests as mandatory regression anchors rather than modifying unrelated
startup code without a discovered gap.

## Technical Approach

- Add `tests/test_test_mix_verify_depth.py` with a deterministic depth gate
  requiring `tests/test_mix_verify.py` to contain `MixVerifyEndToEndTests` and
  classify at depth >= 2 through `sdp.fractal.classify_depth`.
- Confirm the red phase by running the new depth gate before the end-to-end
  class exists.
- Append `MixVerifyEndToEndTests` to `tests/test_mix_verify.py`.
- Drive one public end-to-end path:
  - build a `MixProfile` for the occupied-day garden patch;
  - synthesize role buffers from each target's frequency lane and level;
  - verify the profile/mastering policy is clean;
  - compute peak, RMS, LUFS proxy, clipping, silence, low-end, harshness, and
    masking outputs;
  - assert those outputs are meaningful and agree with `verify_render_loudness`;
  - serialize the diagnostic payload through `json.dumps`/`json.loads` to prove
    it is JSON-safe for operator reports.
- Preserve existing focused assertions and production behavior.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state files, HTTP routes, or auth behavior.

## Edge Cases

- The new end-to-end test intentionally covers one simple happy path, not every
  cadence, patch, or hardware backend.
- Existing focused tests remain responsible for silence, invalid policy,
  over-threshold harshness, sub-heavy low-end, masking, and loudness-failure
  edge cases.
- The synthetic renderer uses deterministic sine buffers and stdlib math only,
  so it does not depend on real audio files or SuperCollider.
- Startup identity hardening remains covered by existing CLI, first-boot,
  daemon-ordering, and narrative ASGI tests.

## Acceptance Criteria

1. Existing mix verification assertions remain green.
   VERIFY: `pytest tests/test_mix_verify.py -q`

2. The depth gate confirms `tests/test_mix_verify.py` reaches depth >= 2 and
   contains `MixVerifyEndToEndTests`.
   VERIFY: `pytest tests/test_test_mix_verify_depth.py -q`

3. `MixVerifyEndToEndTests` drives one meaningful public path from mix profile
   construction through synthetic rendering, verification helpers, and
   JSON-safe diagnostics.
   VERIFY: `pytest tests/test_mix_verify.py::MixVerifyEndToEndTests -q`

4. Related mix-engine coverage remains green for downstream profile generation.
   VERIFY: `pytest tests/test_mix_engine.py -q`

5. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing task notes mention the frac-0089 mix-verify test deepening.
   VERIFY: `grep -n "frac-0089" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
