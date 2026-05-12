# Task frac-0081: Deepen test_governor_integration from depth 1 to depth 2

## Problem Statement
The test file `tests/test_governor_integration.py` currently covers budget enforcement across grain density, density multiplier, DSP cap, and LLM suppression, as well as checking the `bootstrap_identity` startup flow. However, it lacks a dedicated end-to-end test path that drives the entire governor lifecycle through its public API, and it lacks an explicit depth gate to ensure it remains at depth 2 (`Simple: one-path implementation`).

## Technical Approach
1. **Preserve Production Behavior**: Do not modify the underlying `my-claw/tools/senseweave/resource_governor.py` implementation, as it already implements the required simple depth-2 path.
2. **Deepen the Test**: Add a looped or comprehensive end-to-end class (`TestGovernorIntegrationEndToEnd`) to `tests/test_governor_integration.py` that fully cycles through a snapshot -> pressure -> budget computation, confirming meaningful output constraints.
3. **Add Depth Gate**: Introduce `tests/test_governor_integration_depth.py` that asserts `classify_depth("tests/test_governor_integration.py").depth >= 2`.

## Edge Cases
- Ensuring `test_governor_integration_depth.py` correctly points to the test module and fails if depth < 2.
- The End-to-end test needs to accurately mock or provide parameters to `take_snapshot` without requiring actual disk I/O, as done by the helper functions in the test file.

## Acceptance Criteria
1. **Depth Gate Present**: A depth gate test exists for `test_governor_integration.py`.
   - **VERIFY**: `pytest tests/test_governor_integration_depth.py -v`
2. **End-to-End Coverage**: `test_governor_integration.py` contains a one-path end-to-end test suite for the governor integration.
   - **VERIFY**: `pytest tests/test_governor_integration.py -v`
3. **Startup Identity Tests Kept**: Existing `bootstrap_identity` checks remain.
   - **VERIFY**: `pytest tests/test_governor_integration.py::TestStartupIdentityWiring -v`
4. **All Tests Pass**: Full suite validation.
   - **VERIFY**: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`