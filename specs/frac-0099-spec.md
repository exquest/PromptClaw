# Task frac-0099 Specification: test_orchestral_form Depth 2

## Problem Statement

`tests/test_orchestral_form.py` currently covers the orchestral form helpers at
focused function level: tutti role assignment, diverging crescendo,
converging diminuendo, sfp pair selection, timbral tinting, effect-budget
availability, and post-tutti silence decisions.

The missing frac-0099 work is to make the depth-2 contract explicit for this
test module. The production module
`my-claw/tools/senseweave/synthesis/orchestral_form.py` already exposes the
simple one-path implementation the task asks for: each public function is
typed, deterministic, and returns meaningful orchestration data. This task
therefore deepens the test surface with a deterministic depth gate plus one
end-to-end class that drives the existing public orchestral form surface
through a complete development-climax-to-resolution planning flow.

The generated startup identity hardening bullets target the existing identity
startup subsystem. This checkout already wires `bootstrap_identity()` into
the CLI/narrative startup paths and both daemon startup order checks, with
standalone/federated persistence covered by regression tests. This task keeps
those tests as mandatory hardening anchors rather than changing unrelated
startup code without a discovered gap.

## Technical Approach

- Add `tests/test_test_orchestral_form_depth.py` with a deterministic depth
  gate requiring `tests/test_orchestral_form.py` to contain
  `OrchestralFormEndToEndTests` and classify at depth >= 2 through the
  repo-local `sdp.fractal.classify_depth`.
- Confirm the red phase by running the new depth gate before
  `OrchestralFormEndToEndTests` exists.
- Append `OrchestralFormEndToEndTests` to `tests/test_orchestral_form.py`
  without modifying existing locked assertions.
- Drive one meaningful orchestral-form lifecycle inside the class:
  - assign tutti roles for the complete voice list and group them by role;
  - plan a diverging development crescendo and converging resolution
    diminuendo;
  - use `EffectBudget` to gate tinting, sfp, and tutti techniques at movement
    indices used by the composer;
  - select a development tint and dramatic sfp pair;
  - detect post-tutti silence and reentry after the crescendo collapses;
  - serialize a combined diagnostic payload through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)`.
- Preserve existing production behavior unless the red tests expose a concrete
  gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path intentionally covers one happy development-to-resolution
  orchestration flow. Existing focused tests continue to own zero-bar plans,
  unknown voice fallback, existing tint no-op behavior, and silence thresholds.
- Diagnostics convert `TuttiRole` and `ArticulationPair` objects to primitive
  JSON-safe values before serialization so operator surfaces can persist the
  summary without custom encoders.
- Startup identity hardening remains covered by the existing CLI, first-boot,
  daemon-ordering, and narrative ASGI tests; this task does not change identity
  startup wiring.

## Acceptance Criteria

1. Existing orchestral-form regression assertions remain green.
   VERIFY: `pytest tests/test_orchestral_form.py -q`

2. The depth gate confirms `tests/test_orchestral_form.py` reaches depth >= 2
   and contains `OrchestralFormEndToEndTests`.
   VERIFY: `pytest tests/test_test_orchestral_form_depth.py -q`

3. `OrchestralFormEndToEndTests` drives one meaningful orchestral form flow
   through tutti roles, dynamic plans, effect budgeting, sfp selection,
   post-tutti silence, reentry, and JSON-safe diagnostics.
   VERIFY: `pytest tests/test_orchestral_form.py::OrchestralFormEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0099 orchestral-form test
   deepening.
   VERIFY: `grep -n "frac-0099" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
