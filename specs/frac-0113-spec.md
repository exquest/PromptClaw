# Task frac-0113 Specification: test_sampler_effects Depth 2

## Problem Statement

`tests/test_sampler_effects.py` currently verifies the
`sw_sampler_fx` SuperCollider source at a detailed but mostly
branch-by-branch level: SynthDef identity, argument defaults, clipping,
bus conventions, FX-stage presence, reverb branch selection, stage
ordering, compiled-artifact conventions, and the existence of the
SC-side runtime harness.

Missing depth-2 coverage is a single realistic end-to-end test path
that proves the sampler effects surface produces meaningful diagnostic
output across both artifacts the project relies on:

1. the declarative `sampler_effects.scd` source that defines
   `sw_sampler_fx`,
2. the SC-side runtime harness that compiles the source, toggles
   `freeze_amount`, drives an impulse through the full chain, and checks
   the 61.74 Hz comb peak,
3. a stable operator-style diagnostic that captures the effective bus
   defaults, canonical FX stage order, key controls, and runtime harness
   checks in JSON-safe form.

The production SuperCollider source already implements the one-path FX
chain required by the sampler PRD: stereo sampler bus input, delay,
FreeVerb/PartConv reverb, spectral freeze, comb resonance tuned to B,
and final output. This task deepens the test surface unless the red
tests expose a concrete source or harness gap.

The generated startup identity hardening bullets target the existing
identity startup subsystem. Current CLI, first-boot, daemon-ordering,
and narrative ASGI tests already cover `bootstrap_identity()` before
`FirstBootAnnouncer` plus standalone/federated identity persistence.
This task keeps those tests as mandatory regression anchors rather than
changing unrelated startup code.

The active ADP process is the task prompt's Explore -> Specify -> Test
-> Implement -> Verify -> Document workflow, as mirrored in
`sdp/templates/candidates/lead_t2/v006.md`.

## Technical Approach

- Add `tests/test_test_sampler_effects_depth.py` using the recent
  depth-gate pattern. The gate requires:
  - `SamplerEffectsEndToEndTests` exists in
    `tests/test_sampler_effects.py`;
  - the named method
    `test_sampler_effects_source_and_runtime_harness_round_trip_json_diagnostic`
    exists;
  - `classify_depth("tests/test_sampler_effects.py").depth >= 2`.
- Confirm the red phase by running the new depth gate before the
  end-to-end class exists.
- Append `SamplerEffectsEndToEndTests` to `tests/test_sampler_effects.py`
  without modifying existing locked assertions. The class drives one
  deterministic path:
  - parse the SynthDef argument block and extract meaningful defaults
    for `in_bus`, `out_bus`, delay, reverb, freeze, and comb controls;
  - verify the source contains one ordered full chain from `In.ar` to
    `DelayC.ar`, `FreeVerb.ar`, `PV_Freeze`, `CombC.ar`, `LPF.ar`, and
    `Out.ar`;
  - verify the SC-side harness compiles `sampler_effects.scd`, toggles
    `freeze_amount`, exercises `comb_decay` / `comb_damping`, runs the
    impulse/comb path, and checks the 61.74 Hz comb target;
  - build a primitive diagnostic payload and verify
    `json.dumps(..., sort_keys=True)` / `json.loads(...)` round-trips
    it.
- Preserve production behavior unless the red tests reveal a runtime
  gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- This is intentionally one simple happy path for depth-2 coverage.
  Existing focused tests remain responsible for malformed defaults,
  individual clipping ranges, branch-selection details, and SC harness
  conventions.
- The Python CI environment does not have the SuperCollider toolchain,
  so the new end-to-end test remains declarative and validates the
  runtime harness source rather than invoking `sclang`.
- The diagnostic payload only stores strings, floats, lists, and nested
  dicts, so JSON serialization stays deterministic and hermetic.
- No database schema changes are introduced, so no migration or index
  work is required.
- Startup identity hardening remains a regression anchor and is not
  widened inside the sampler-effects tests.

## Acceptance Criteria

1. Existing sampler-effects assertions remain green.
   VERIFY: `pytest tests/test_sampler_effects.py -q`

2. The depth gate confirms `tests/test_sampler_effects.py` reaches
   depth >= 2 and contains the named end-to-end class/method.
   VERIFY: `pytest tests/test_test_sampler_effects_depth.py -q`

3. `SamplerEffectsEndToEndTests` drives the SCD source, SC-side runtime
   harness, ordered FX chain, control defaults, and JSON-safe diagnostic
   lifecycle.
   VERIFY: `pytest tests/test_sampler_effects.py::SamplerEffectsEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0113 sampler-effects test
   deepening with no new dependencies or migrations.
   VERIFY: `grep -n "frac-0113" CHANGELOG.md progress.md ESCALATIONS.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
