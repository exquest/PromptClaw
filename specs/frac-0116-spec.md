# Task frac-0116 Specification: test_sw_sampler Depth 2

## Problem Statement

`tests/test_sw_sampler.py` currently verifies the
`my-claw/tools/senseweave/synthesis/sw_sampler.scd` granular SynthDef source
and the SC-side runtime harness `my-claw/supercollider/test_sw_sampler.scd`
at focused unit level: SynthDef identity, required argument names and
defaults, range-clip guards, signal-chain UGens, dry/fx-send routing, and
SC-side runtime checks (`.load`, 2-second render, non-silence, FFT spectral
peak, gate=0 release tail, known-content buffer).

Missing depth-2 coverage is a single realistic end-to-end test path that
proves the granular voice's source contract and runtime harness produce
meaningful diagnostic output across the full surface:

1. extract argument defaults for the canonical SynthDef control surface
   (`amp`, `grain_size_ms`, `density`, `position`, `position_rate`,
   `pitch_transpose_semitones`, `pitch_jitter_semitones`, `attack_sec`,
   `release_sec`, `gate`, `out_bus`, `fx_bus`, `fx_send`, `bufnum`),
2. verify the integrated granular signal chain stages
   (`Impulse.kr` -> `TRand.kr` -> `.midiratio` -> `Sweep.ar`/`Phasor.ar`
   -> `GrainBuf.ar(... bufnum ...)` -> `EnvGen.kr(Env.asr, gate, doneAction: 2)`
   -> dry `Out.ar(out_bus, ...)` + parallel `Out.ar(fx_bus, ...)` send) appear
   in source order,
3. confirm the dry write to `out_bus` is not scaled by `fx_send` so the
   parallel-send architecture is preserved,
4. confirm the SC-side runtime harness compiles the source, allocates a
   known-content buffer, renders 2 seconds, asserts non-silence, computes an
   FFT for spectral-peak verification, and exercises the gate=0 release tail,
5. produce a stable operator-style diagnostic that captures the SynthDef
   name, source path, runtime harness path, control defaults, signal-chain
   stages, and runtime-check results in JSON-safe form.

The production source already implements this one-path behavior. This task
therefore deepens the test surface unless the red tests expose a concrete
source gap.

The generated startup identity hardening bullets target the existing identity
startup subsystem. Current CLI, first-boot, daemon-ordering, and narrative
ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer`
plus standalone/federated identity persistence. This task keeps those tests
as mandatory regression anchors rather than changing unrelated startup code.

The active ADP process is the task prompt's Explore -> Specify -> Test ->
Implement -> Verify -> Document workflow.

## Technical Approach

- Add `tests/test_test_sw_sampler_depth.py` using the recent depth-gate
  pattern. The gate requires:
  - `SwSamplerEndToEndTests` exists in `tests/test_sw_sampler.py`;
  - the named method
    `test_sw_sampler_source_and_runtime_harness_round_trip_json_diagnostic`
    exists;
  - `classify_depth("tests/test_sw_sampler.py").depth >= 2`.
- Confirm the red phase by running the new depth gate before the end-to-end
  class exists.
- Append `SwSamplerEndToEndTests` to `tests/test_sw_sampler.py` without
  modifying existing locked assertions. The class drives one deterministic
  path:
  - parse the SynthDef argument block once and read every documented control
    default plus `bufnum`;
  - locate the integrated signal-chain UGen stages in canonical source order
    (`Impulse.kr`, `TRand.kr`, `.midiratio`, `Sweep.ar` or `Phasor.ar`,
    `GrainBuf.ar` reading `bufnum`, `EnvGen.kr(Env.asr, gate, doneAction: 2)`,
    dry `Out.ar(out_bus, ...)`, parallel `Out.ar(fx_bus, ...)`);
  - confirm the dry `Out.ar(out_bus, ...)` argument list does not reference
    `fxAmt` or `fx_send` so the dry path is not scaled by the send;
  - inspect the SC-side runtime harness for source compile, known-content
    buffer allocation, 2-second render, non-silence, FFT spectral-peak,
    and gate=0 release-tail checks;
  - build a primitive diagnostic payload of the SynthDef name, source path,
    runtime-harness path, defaults, stage positions, and runtime checks, and
    verify `json.dumps(..., sort_keys=True)` / `json.loads(...)` round-trips
    it.
- Preserve production behavior unless the red tests reveal a runtime gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- This is intentionally one simple happy path for depth-2 coverage. Existing
  focused tests remain responsible for individual control names, clip
  ranges, per-stage UGen presence, `fx_bus` default value, and the
  individual SC-side runtime assertions.
- Comments inside the SCD source are stripped before stage-position checks so
  documentation references to `Out.ar`/`fx_send` cannot mask source-order
  regressions.
- The diagnostic payload only stores strings, booleans, ints, floats, lists,
  and nested dicts, so JSON serialization stays deterministic and hermetic.
- No database schema changes are introduced, so no migration or index work
  is required.
- Startup identity hardening remains a regression anchor and is not widened
  inside the sw_sampler tests.

## Acceptance Criteria

1. Existing sw_sampler assertions remain green.
   VERIFY: `pytest tests/test_sw_sampler.py -q`

2. The depth gate confirms `tests/test_sw_sampler.py` reaches depth >= 2 and
   contains the named end-to-end class/method.
   VERIFY: `pytest tests/test_test_sw_sampler_depth.py -q`

3. `SwSamplerEndToEndTests` drives the SynthDef defaults, integrated
   granular signal-chain stage ordering, parallel-send dry/wet routing,
   SC-side runtime-harness checks, and JSON-safe diagnostic round-trip.
   VERIFY: `pytest tests/test_sw_sampler.py::SwSamplerEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0116 sw_sampler test
   deepening with no new dependencies or migrations.
   VERIFY: `grep -n "frac-0116" CHANGELOG.md progress.md ESCALATIONS.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
