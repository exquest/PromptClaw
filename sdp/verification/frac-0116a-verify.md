# Verification Report — frac-0116a

**Verify Agent:** Claude Sonnet 4.6 (Verify)
**Date:** 2026-05-03
**Artifacts Reviewed:**
- `specs/frac-0116a-spec.md`
- `tests/test_test_sw_sampler_depth.py`
- `tests/test_sw_sampler.py`
- `CHANGELOG.md`
- `ESCALATIONS.md`
- `progress.md`
- git log (commits `2f907fe`, `4cce20e`)

## Correctness

**FAIL — scope violation.** The spec explicitly states: "This fractional task is the RED half only… The marker itself is intentionally not added in this task so the red phase remains observable for the follow-up implementation task."

Commit `2f907fe` correctly added only the gate test (no marker in `tests/test_sw_sampler.py`). However, commit `4cce20e` (`fix(scope): resolve gate failures`) then added `Coverage depth: 2.` to the `tests/test_sw_sampler.py` module docstring, which is explicitly out-of-scope for this RED task.

As a result, `test_test_sw_sampler_declares_machine_readable_depth_two_marker` now PASSES when it must remain FAILING until the follow-up GREEN task. Acceptance criterion 4 is violated.

The documentation (CHANGELOG.md line 5, ESCALATIONS.md line 1001) asserts the marker was NOT added — a direct contradiction of the code state.

## Completeness

The gate test itself is well-structured and complete. It handles:
- Module docstring scanning via `_DEPTH_TWO_MARKER_RE`
- Top-level `ast.Assign` and `ast.AnnAssign` constants with `DEPTH` in the name
- Integer literal `2` and string-embedded marker forms
- Case-insensitive matching, `:` and `=` separators

Acceptance criteria 1, 2, 3, 5, and 6 are structurally satisfied (spec file exists, frac-0116a referenced in progress/ESCALATIONS/CHANGELOG, gate function is present, existing frac-0116 tests pass). Criterion 4 fails.

## Consistency

Gate implementation pattern (AST parsing, no imports of the target module) is consistent with the existing `test_test_sw_sampler_reaches_depth_two_with_e2e_class` approach. The regex module-level constant follows established project conventions.

The commit attribution is internally inconsistent: the commit message says "fix(scope): resolve gate failures" implying a post-hoc correction, and the documentation claims the opposite of what was done.

## Security

No security concerns. The change is purely test-infrastructure: AST parsing of a local test file, no secrets, no runtime code, no HTTP routes or external dependencies introduced.

## Quality

Gate test logic is clean and readable. The helper functions (`_target_names`, `_literal_value`, `_has_machine_readable_depth_two_marker`) are well-named and minimal. Ruff and mypy pass. The quality of the test code is not the issue; the scope discipline is.

## Issues Found

- [x] **Scope violation — marker added in RED task — severity: blocking.** `tests/test_sw_sampler.py` line 13 contains `Coverage depth: 2.` added by commit `4cce20e`. The spec forbids this; the marker belongs in the follow-up GREEN implementation task. The RED gate test (`test_test_sw_sampler_declares_machine_readable_depth_two_marker`) now passes when it must remain failing.
- [x] **Documentation contradicts code — severity: blocking.** CHANGELOG.md and ESCALATIONS.md both state the marker was not added. The actual code contains the marker. This false record must be corrected regardless of how the scope issue is resolved.

## Verdict: FAIL

## Notes for Lead Agent

The fix is straightforward: revert commit `4cce20e` (remove the `Coverage depth: 2.` line from `tests/test_sw_sampler.py`). The gate test and all other artifacts from commit `2f907fe` are correct and should be preserved.

After reverting:
1. `pytest tests/test_test_sw_sampler_depth.py::test_test_sw_sampler_declares_machine_readable_depth_two_marker -q` must FAIL (1 failed).
2. `pytest tests/test_test_sw_sampler_depth.py::test_test_sw_sampler_reaches_depth_two_with_e2e_class tests/test_sw_sampler.py::SwSamplerEndToEndTests -q` must PASS (2 passed).
3. Update CHANGELOG.md and ESCALATIONS.md to remove the false claim that "full-suite validation … stopped at the intentional RED gate with 1 failed" — that statement was true at the time but was then undermined by the same task adding the marker. After the revert, those statements become accurate again and can stand.
4. The follow-up GREEN task (adding the depth marker to `tests/test_sw_sampler.py`) remains the correct vehicle for closing the RED gate.
