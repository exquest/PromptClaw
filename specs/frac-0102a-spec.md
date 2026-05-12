# Task frac-0102a Specification: Render-Ablation Depth Coverage Notes

## Problem Statement

`tests/test_render_ablation.py` is the render-ablation test surface for
`my-claw/tools/senseweave/render/ablation.py`. The frac-0102 parent task
already added depth-2 coverage in this checkout, but the split frac-0102a task
asks for the prior depth-1 coverage to be located and documented: which
functions and paths were exercised, which outputs were only smoke-checked, and
which concrete gaps should be filled by follow-up depth work.

This task is documentation-only. It must not change render-ablation runtime
behavior, locked render-ablation assertions, database schemas, dependencies,
provider configuration, or startup identity wiring.

## Technical Approach

- Treat the affected area as:
  - `tests/test_render_ablation.py`
  - `tests/test_test_render_ablation_depth.py`
  - `my-claw/tools/senseweave/render/ablation.py`
  - existing frac-0102 task records in `specs/`, `CHANGELOG.md`,
    `progress.md`, and `ESCALATIONS.md`
- Use git history at the parent of `8e43ac3` to identify the focused
  pre-depth-2 test shape, since current `HEAD` already contains
  `RenderAblationEndToEndTests`.
- Add a small documentation contract test that requires a notes file at
  `sdp/notes/frac-0102a-render-ablation-depth.md`.
- Write the notes file with short, concrete sections for:
  - location and current state;
  - paths/functions exercised by the depth-1 baseline;
  - outputs that were smoke-checked rather than deeply validated;
  - concrete gaps to fill.
- Update task bookkeeping in `CHANGELOG.md`, `progress.md`, and
  `ESCALATIONS.md`.

## Edge Cases

- The notes must distinguish the pre-depth-2 baseline from current `HEAD`, where
  the parent task has already added an end-to-end class.
- The notes must not imply live audio rendering, real SenseWeave rule execution,
  provider calls, or external services are covered by `test_render_ablation`.
- Generated hardening bullets about `bootstrap_identity()` are out of scope for
  this render-ablation documentation task; existing startup identity tests remain
  the verification anchors.

## Acceptance Criteria

1. The documentation contract test exists and pins the requested notes file
   shape.
   VERIFY: `pytest tests/test_frac_0102a_notes.py -q`

2. The notes file locates `test_render_ablation`, lists exercised
   paths/functions, identifies smoke-checked outputs, and names concrete gaps.
   VERIFY: `grep -n "tests/test_render_ablation.py\\|Smoke-Checked Outputs\\|Concrete Gaps" sdp/notes/frac-0102a-render-ablation-depth.md`

3. Render-ablation behavior and existing depth gates remain unchanged and green.
   VERIFY: `pytest tests/test_render_ablation.py tests/test_test_render_ablation_depth.py -q`

4. Startup identity hardening remains covered by existing regression anchors.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Task bookkeeping names the frac-0102a documentation artifact.
   VERIFY: `grep -n "frac-0102a" CHANGELOG.md progress.md ESCALATIONS.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
