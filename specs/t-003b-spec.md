# Task T-003b: Coupling Multiplier From Bus Value

## Problem Statement

T-003a added a Python-side reader for the shared `affective_state_bus`, but the
voice layer still lacks a pure helper that turns a bus value into the coupling
multiplier defined by the CypherClaw v2 PRD. Later subtasks will wire this
multiplier into per-voice modulator depths; this task provides the small,
testable arithmetic surface those subtasks can reuse.

Per PRD feature 8 / CC-072, a nominal modulator depth is scaled by:

```text
effective_depth = nominal_depth * (1 + coupling_strength * affective_state)
```

This task computes only the multiplier:

```text
1 + coupling_strength * affective_state
```

## Technical Approach

- Add a typed pure function in
  `my-claw/tools/senseweave/synthesis/senseweave_voice.py` next to the
  existing `read_affective_state_bus(...)` helper.
- Name the helper `coupling_multiplier_from_bus_value(...)` to make the input
  and output explicit.
- Accept `bus_value: float` and keyword-only `coupling_strength: float = 0.5`,
  matching the PRD's default per-voice coupling strength.
- Clamp `bus_value` to the shared affective-state bus range `[0.0, 1.0]`.
- Clamp `coupling_strength` to `[0.0, 1.0]`, matching the SuperCollider
  reference reader contract.
- Return `1.0 + clamped_coupling_strength * clamped_bus_value`.
- Keep this slice Python-only and side-effect-free. No OSC reads, env reads,
  database changes, migrations, provider secrets, runtime state directories, or
  new dependencies are required.

## Edge Cases

- `bus_value=0.0` returns `1.0` with default strength.
- `bus_value=0.5` returns `1.25` with default strength `0.5`.
- `bus_value=1.0` returns `1.5` with default strength `0.5`.
- Negative bus values clamp to `0.0`.
- Bus values above `1.0` clamp to `1.0`.
- Negative coupling strengths clamp to `0.0`.
- Coupling strengths above `1.0` clamp to `1.0`.
- The generated startup hardening bullets target the existing identity startup
  subsystem. This task does not modify startup paths; existing identity
  regression anchors remain mandatory verification.

## Acceptance Criteria

1. The pure multiplier helper returns the PRD boundary values for bus values
   `0.0`, `0.5`, and `1.0` using default coupling strength `0.5`.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestCouplingMultiplier::test_default_strength_boundary_values -q`

2. The pure multiplier helper clamps bus values and coupling strengths into
   `[0.0, 1.0]` before scaling.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestCouplingMultiplier::test_clamps_bus_value_and_coupling_strength -q`

3. The existing T-003a bus reader tests remain green.
   VERIFY: `pytest tests/test_senseweave_voice.py::TestAffectiveStateBusReader -q`

4. Existing affective-bus writer, flag, and decay behavior remain green.
   VERIFY: `pytest tests/test_affective_state_bus.py -q`

5. Startup identity hardening anchors still pass for both standalone and
   federated persistence paths.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Required validation passes before final commit.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
