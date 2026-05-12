# Task frac-0101 Specification: test_pedals_to_key Depth 2

## Problem Statement

`tests/test_pedals_to_key.py` covers the focused behavior of
`my-claw/tools/senseweave/pedals_to_key.py`: sustain maps to chord holding,
expression maps to harmonic tension and dynamics, and recent pedal gestures map
to either modulation, pedal point, or no special shift.

The missing frac-0101 work is to make the depth-2 contract explicit for this
test module. The production module already exposes the simple one-path
implementation requested by the task: all public helpers are stdlib-only,
deterministic, typed at their signatures, and return meaningful primitive
outputs. This task therefore deepens the test surface with a deterministic
depth gate plus one end-to-end class that drives a single expressive pedal
phrase through harmonic guidance, dynamic shaping, gesture interpretation, and
JSON-safe diagnostics.

The generated startup identity hardening bullets target the existing identity
startup subsystem. This checkout already wires `bootstrap_identity()` before
`FirstBootAnnouncer` in startup paths, and existing regression tests cover
standalone/federated persistence. This task keeps those tests as mandatory
hardening anchors rather than changing unrelated startup code without a
discovered gap.

## Technical Approach

- Add `tests/test_test_pedals_to_key_depth.py` with a deterministic depth gate
  requiring `tests/test_pedals_to_key.py` to contain
  `PedalsToKeyEndToEndTests` and classify at depth >= 2 through
  `sdp.fractal.classify_depth`.
- Confirm the red phase by running the new depth gate before
  `PedalsToKeyEndToEndTests` exists.
- Append `PedalsToKeyEndToEndTests` to `tests/test_pedals_to_key.py` without
  modifying existing locked assertions.
- Drive one meaningful pedals-to-key lifecycle inside the class:
  - call `pedal_to_harmonic_shift(sustain=True, expression=96)` and assert it
    holds the chord, produces high tension, and suggests extensions;
  - call `expression_to_dynamics(96)` and assert it produces a loud, bright
    dynamic profile;
  - call `key_shift_from_pedal_pattern(...)` for the same phrase's rapid
    on-off-on gesture and assert it suggests modulation;
  - call `key_shift_from_pedal_pattern(...)` for the phrase's held landing and
    assert it resolves to a pedal point;
  - serialize a combined diagnostic payload through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)`.
- Preserve production behavior unless the red tests expose a concrete gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path intentionally covers one happy expressive pedal phrase.
  Existing focused tests continue to own clamping, threshold boundaries,
  monotonic dynamics, slow pedal use, empty/single event inputs, and valid
  return domains.
- Diagnostics only include primitive values so the summary can be persisted or
  embedded in operator-facing reports without custom encoders.
- Startup identity hardening remains covered by the existing CLI, first-boot,
  daemon-ordering, and narrative ASGI tests; this task does not change identity
  startup wiring.

## Acceptance Criteria

1. Existing pedals-to-key regression assertions remain green.
   VERIFY: `pytest tests/test_pedals_to_key.py -q`

2. The depth gate confirms `tests/test_pedals_to_key.py` reaches depth >= 2
   and contains `PedalsToKeyEndToEndTests`.
   VERIFY: `pytest tests/test_test_pedals_to_key_depth.py -q`

3. `PedalsToKeyEndToEndTests` drives one meaningful pedal phrase through
   harmonic shift, expression dynamics, modulation gesture detection, pedal
   point detection, and JSON-safe diagnostics.
   VERIFY: `pytest tests/test_pedals_to_key.py::PedalsToKeyEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Full validation gate is green.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
