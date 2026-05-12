# Task frac-0116a Specification: sw_sampler Depth Marker Gate

## Problem Statement

`tests/test_sw_sampler.py` now has depth-2 behavioral coverage from
frac-0116, but the coverage tier is only discoverable by running the
repo-local depth classifier and inspecting the companion gate test. Queue and
coverage tooling need a machine-readable marker directly on the covered test
module so `tests/test_sw_sampler.py` can advertise its intended tier without
executing pytest.

This fractional task is the RED half only: add a locked gate that asserts the
presence of a `depth: 2` marker, or an equivalent top-level depth constant, in
`tests/test_sw_sampler.py`. The marker itself is intentionally not added in
this task so the red phase remains observable for the follow-up implementation
task.

The active ADP process is the task prompt's Explore -> Specify -> Test ->
Implement -> Verify -> Document workflow, mirrored in
`sdp/templates/candidates/lead_t2/v006.md`.

## Technical Approach

- Extend `tests/test_test_sw_sampler_depth.py`, the existing depth gate for
  `tests/test_sw_sampler.py`.
- Parse `tests/test_sw_sampler.py` with `ast` rather than importing it.
- Treat the marker as present when either:
  - the module docstring contains a case-insensitive `depth: 2` or
    `depth = 2` style marker; or
  - a top-level constant whose name contains `DEPTH` is assigned the integer
    literal `2`, or a string literal containing the same marker form.
- Keep the existing frac-0116 assertions untouched and do not modify
  `tests/test_sw_sampler.py` during this RED task.
- Add no runtime code, dependencies, migrations, provider secrets, runtime
  state files, HTTP routes, or startup behavior.

## Edge Cases

- The gate inspects only the module docstring and top-level constants because
  nested comments or local variables are not stable machine-readable metadata.
- Matching is case-insensitive and allows either `:` or `=` so common metadata
  spelling variants are accepted while still requiring an explicit depth value.
- The existing depth-2 classifier gate remains responsible for proving actual
  test depth; this new gate only checks the declared tier marker.
- The generated startup identity hardening bullets are outside this
  marker-only test scope. Existing CLI, first-boot, daemon-ordering, and
  narrative ASGI tests remain the regression anchors.

## Acceptance Criteria

1. Exploration findings and assumptions are recorded for frac-0116a.
   VERIFY: `grep -n "frac-0116a" progress.md ESCALATIONS.md`

2. The specification documents the marker-only RED scope and acceptance
   criteria.
   VERIFY: `test -f specs/frac-0116a-spec.md && grep -n "RED half" specs/frac-0116a-spec.md`

3. The existing sw_sampler depth gate file includes a locked marker test that
   parses `tests/test_sw_sampler.py` and accepts module-docstring or top-level
   constant markers.
   VERIFY: `grep -n "test_test_sw_sampler_declares_machine_readable_depth_two_marker" tests/test_test_sw_sampler_depth.py`

4. The marker test fails before the marker is added to `tests/test_sw_sampler.py`.
   VERIFY: `pytest tests/test_test_sw_sampler_depth.py::test_test_sw_sampler_declares_machine_readable_depth_two_marker -q`

5. Existing frac-0116 depth coverage remains otherwise green when the RED
   marker test is not selected.
   VERIFY: `pytest tests/test_test_sw_sampler_depth.py::test_test_sw_sampler_reaches_depth_two_with_e2e_class tests/test_sw_sampler.py::SwSamplerEndToEndTests -q`

6. Product-facing task notes mention that frac-0116a adds the RED marker gate
   without adding dependencies or migrations.
   VERIFY: `grep -n "frac-0116a" CHANGELOG.md progress.md ESCALATIONS.md`
