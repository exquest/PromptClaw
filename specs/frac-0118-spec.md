# Task frac-0118 Specification: test_synthesis_architecture_registry Depth 2

## Problem Statement

`tests/test_synthesis_architecture_registry.py` verifies the SenseWeave
synthesis architecture registry at focused invariant depth. It checks the six
required architecture records, required fields, macro-control safe ranges,
arc-phase winners, role lookups, fallback lookup behavior, and consistency with
`procedural_arc` and `production_course`.

Missing depth-2 coverage is a single realistic end-to-end path that proves the
same public surface produces meaningful operator-facing output across the
registry lifecycle:

1. resolve the canonical phase winners and role mappings from the registry,
2. build the existing `ArchitectureRegistryReport`,
3. serialize the report through `summarize_architecture_registry_report(...)`,
4. confirm the summary agrees with the lower-level lookup helpers and the
   PRD-backed production-course chapter, and
5. round-trip the diagnostic through JSON so status surfaces can persist or
   display it.

The production module already contains the one-path implementation from
`frac-0031` (`ArchitectureProfile`, `ArchitectureRegistryReport`,
`build_architecture_registry_report`, and
`summarize_architecture_registry_report`). This task therefore deepens the base
test surface unless the red tests expose a production gap.

The generated startup identity hardening bullets target the existing identity
startup subsystem. Current CLI, first-boot, daemon-ordering, and narrative ASGI
tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` plus
standalone/federated identity persistence. This task keeps those tests as
mandatory regression anchors rather than changing unrelated startup code.

The active ADP process is the task prompt's Explore -> Specify -> Test ->
Implement -> Verify -> Document workflow, as mirrored in
`sdp/templates/candidates/lead_t2/v006.md`.

## Technical Approach

- Add `tests/test_test_synthesis_architecture_registry_depth.py` using the
  recent depth-gate pattern. The gate requires:
  - `SynthesisArchitectureRegistryEndToEndTests` exists in
    `tests/test_synthesis_architecture_registry.py`;
  - the named method
    `test_registry_lookup_report_and_course_summary_round_trip_json_diagnostic`
    exists;
  - `classify_depth("tests/test_synthesis_architecture_registry.py").depth >= 2`;
  - the test module declares a machine-readable depth-2 marker either in the
    module docstring (`depth: 2`) or as a top-level `DEPTH = 2` constant.
- Confirm the red phase by running the new depth gate before the end-to-end
  class and marker exist.
- Extend `tests/test_synthesis_architecture_registry.py` without modifying
  existing locked assertions:
  - add a `depth: 2` marker to the module docstring;
  - import the existing report helpers;
  - append `SynthesisArchitectureRegistryEndToEndTests` with one deterministic
    lifecycle test.
- The end-to-end test will:
  - build the full architecture registry report;
  - summarize it into JSON-safe primitives;
  - assert the canonical six architecture IDs and five phases are present;
  - assert each phase winner agrees with `best_architecture_for_phase(...)`;
  - assert each phase candidate list agrees with `architectures_for_phase(...)`;
  - assert role mappings agree with `strategies_for_role(...)`;
  - assert every profile carries macro controls, a best phase, high-affinity
    phase diagnostics, and a cycle-safe fallback chain;
  - assert production-course synthesis concepts are all represented in the
    report;
  - round-trip a compact diagnostic through `json.dumps(..., sort_keys=True)`
    and `json.loads(...)`.
- Preserve production behavior unless the red tests reveal a runtime gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- This is intentionally one simple happy path for depth-2 coverage. Existing
  focused tests remain responsible for missing required architecture/phase
  checks, safe-range validation, unknown lookup fallback behavior, and
  procedural-arc consistency.
- JSON diagnostics only include strings, ints, floats, booleans, lists, and
  nested dictionaries so serialization stays deterministic and hermetic.
- Fallback chains are checked as meaningful output but not re-derived in this
  test; existing `tests/test_synthesis_architecture_registry_depth.py` owns the
  cycle boundary specifics from the production helper task.
- No database schema changes are introduced, so no migration or index work is
  required.
- Startup identity hardening remains a regression anchor and is not widened
  inside the synthesis registry tests.

## Acceptance Criteria

1. Existing synthesis architecture registry assertions remain green.
   VERIFY: `pytest tests/test_synthesis_architecture_registry.py -q`

2. The depth gate confirms `tests/test_synthesis_architecture_registry.py`
   reaches depth >= 2 and contains the named end-to-end class/method plus the
   machine-readable depth-2 marker.
   VERIFY: `pytest tests/test_test_synthesis_architecture_registry_depth.py -q`

3. `SynthesisArchitectureRegistryEndToEndTests` drives registry lookup,
   registry report generation, JSON-safe summary construction, production-course
   concept coverage, and diagnostic JSON round-trip through one meaningful path.
   VERIFY: `pytest tests/test_synthesis_architecture_registry.py::SynthesisArchitectureRegistryEndToEndTests -q`

4. The existing production helper depth tests remain green.
   VERIFY: `pytest tests/test_synthesis_architecture_registry_depth.py -q`

5. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing task notes mention the frac-0118 synthesis registry test
   deepening with no new dependencies or migrations.
   VERIFY: `grep -n "frac-0118" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
