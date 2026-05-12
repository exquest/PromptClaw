# Task frac-0007 Specification: Collaborative Canvas Depth 2

## Problem Statement

`my-claw/tools/senseweave/collaborative_canvas.py` stores shared visual
canvas state for the CypherClaw art installation. It can add/remove layers,
toggle visibility, clamp opacity, and persist JSON state, but the public
surface is mostly state plumbing. The fractal scanner currently classifies the
module at depth 1 (`7/12 trivial, 5 real`) because callers cannot ask the
module for a meaningful operator summary or a simple rendered output; they can
only inspect raw layer objects and reimplement ordering/composition.

The task is to deepen the module to a simple depth-2 implementation: add one
straightforward text-render/diagnostic path that produces useful output from
the existing `Canvas` state while preserving the current JSON contract and
existing tests.

## Technical Approach

Extend `collaborative_canvas.py` in place with three typed helpers:

- `canvas_layer_manifest(canvas)` returns a priority-sorted list of stable
  dictionaries for every layer, including name, priority, kind (`text`,
  `image`, or `empty`), opacity, position, and visibility. This gives
  diagnostics a meaningful layer listing without exposing dataclass internals.
- `canvas_summary(canvas)` returns a stable dictionary with total/visible/
  hidden counts, text/image counts, top visible layer name, and a visible
  layer bounds box derived from text content extents and image positions.
- `render_text_canvas(canvas, width, height, fill=" ")` composites visible
  text layers into a fixed-size string grid in existing priority order. Image
  layers remain represented in manifests/summaries but are not rasterized by
  the stdlib-only text renderer.

Existing `CanvasLayer`, `Canvas`, `write_canvas_state`, and
`read_canvas_state` behavior remains compatible. No new dependencies,
migrations, secrets, provider commands, or database columns are introduced.

## Edge Cases

- Hidden layers are excluded from summary bounds and text rendering but remain
  present in the manifest with `visible=False`.
- Image-only layers count as image layers and occupy their position in summary
  bounds, but they do not draw characters in `render_text_canvas`.
- Empty-content layers are reported as `empty` and ignored by text rendering.
- Text rendering clips characters outside the requested grid and treats space
  characters as transparent, so higher-priority labels can overlay lower
  layers without erasing them.
- Non-positive render dimensions return an empty string.
- Startup identity hardening remains a regression anchor. Existing tests cover
  `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`
  for standalone and federated startup paths.

## Acceptance Criteria

1. `canvas_layer_manifest` returns priority-sorted, operator-readable metadata
   for text, image, hidden, and empty layers.
   VERIFY: `pytest tests/test_collaborative_canvas_depth.py::test_canvas_layer_manifest_reports_ordered_layer_metadata -q`

2. `canvas_summary` reports meaningful counts, top visible layer, and visible
   layer bounds.
   VERIFY: `pytest tests/test_collaborative_canvas_depth.py::test_canvas_summary_reports_counts_top_layer_and_bounds -q`

3. `render_text_canvas` composites visible text layers by priority into a
   deterministic fixed-size text grid.
   VERIFY: `pytest tests/test_collaborative_canvas_depth.py::test_render_text_canvas_composes_visible_text_layers_by_priority -q`

4. End-to-end JSON state still round-trips and can be rendered after reload.
   VERIFY: `pytest tests/test_collaborative_canvas_depth.py::test_canvas_state_roundtrip_can_render_text_output -q`

5. Existing collaborative canvas behavior remains compatible.
   VERIFY: `pytest tests/test_collaborative_canvas.py -q`

6. Fractal depth for `my-claw/tools/senseweave/collaborative_canvas.py`
   reaches at least depth 2.
   VERIFY: `python - <<'PY'
import sys
sys.path.insert(0, "/Users/anthony/Programming/sdp-cli/src")
from sdp.fractal import classify_depth
result = classify_depth("my-claw/tools/senseweave/collaborative_canvas.py")
print(result.depth, result.reason)
assert result.depth >= 2
PY`

7. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

8. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
