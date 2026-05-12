# Task frac-0079: Deepen test_generation_request from depth 1 to depth 2

## Problem Statement
The test suite for `GenerationRequest` currently covers field validation, defaults, immutability, and hashing at a unit level, but it lacks a deterministic end-to-end integration class that verifies the full lifecycle of a request in one coherent flow. It also needs a depth gate to ensure it satisfies fractal depth 2 requirements. 

## Technical Approach
1. Append an end-to-end class `class TestGenerationRequestEndToEnd:` to `tests/test_generation_request.py`. This class will instantiate multiple requests, demonstrate rejection of invalid fields, apply hashing, test equality, and ensure stable output across a complete usage lifecycle.
2. Add a depth gate test at `tests/test_generation_request_depth.py` that asserts `classify_depth("tests/test_generation_request.py").depth >= 2`.

## Edge Cases
- Validation of numpy array shapes and dtypes during the end-to-end flow.
- Ensure that the hash function remains stable ignoring the backend identity.

## Acceptance Criteria
1. `tests/test_generation_request.py` contains `TestGenerationRequestEndToEnd`.
   - VERIFY: `grep -q "TestGenerationRequestEndToEnd" tests/test_generation_request.py`
2. `tests/test_generation_request_depth.py` exists and asserts depth >= 2.
   - VERIFY: `pytest tests/test_generation_request_depth.py -v`
3. All tests pass.
   - VERIFY: `pytest tests/test_generation_request.py tests/test_generation_request_depth.py -x`