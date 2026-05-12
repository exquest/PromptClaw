# Task frac-0002 Specification: Gallery X11 Wrapper Depth 2

## Problem Statement

`my-claw/tools/gallery_x11.py` is the historical compatibility entrypoint
that launches the X11 gallery display. The fractal scanner classifies it at
depth 0 because the wrapper currently contains no functions of its own — it
only re-imports `main` from `gallery.gallery_x11` and runs it. The wrapper
needs a simple one-path layer that adds meaningful pre-launch behavior
(argument parsing, runtime summary, runtime validation, environment
override application) so it operates end-to-end and reaches depth 2 without
duplicating the underlying display loop.

## Technical Approach

Extend the wrapper module in place with pure, typed helper functions:

- `parse_args(argv)` — parse CLI flags (`--display`, `--window-pos`,
  `--check`) for the wrapper entrypoint.
- `runtime_summary(env)` — return the effective gallery runtime
  configuration as a dict (display, window_pos, art_dir, art_dir_exists,
  resolution, duration_seconds).
- `validate_runtime(env)` — return a tuple of human-readable problems
  with the current runtime; empty tuple when healthy.
- `apply_overrides(args, env)` — mutate the process environment to honor
  CLI overrides before delegating to the underlying display loop.
- `main(argv)` — argument-parse, apply overrides, validate runtime, and
  either run the existing `gallery.gallery_x11.main()` or exit with
  reported problems.

The helpers re-use the existing `gallery.gallery_x11` constants
(`ART_DIR`, `DURATION`, `WIDTH`, `HEIGHT`) and its
`gallery_window_position` helper. They are deterministic, stdlib-only, and
side-effect free except for `apply_overrides` and `main`. The underlying
package module is unchanged.

## Edge Cases

- Missing `DISPLAY` env var: `validate_runtime` reports the problem rather
  than raising.
- Missing art directory: `validate_runtime` reports the problem; `--check`
  exits non-zero without launching the display loop.
- No CLI overrides supplied: `apply_overrides` is a no-op.
- Explicit env dict supplied to `runtime_summary` / `validate_runtime`:
  callers can probe runtime state without touching `os.environ`.
- The existing `gallery.gallery_x11.gallery_window_position` behavior is
  preserved verbatim — the wrapper does not reimplement window positioning.

## Acceptance Criteria

1. Wrapper helpers produce meaningful parsed, summarized, and validated
   output without launching the display loop.
   VERIFY: `pytest tests/test_gallery_x11_wrapper_depth.py -q`

2. Wrapper `main` honors `--check` and runtime-validation failures by
   exiting non-zero without delegating to the display loop.
   VERIFY: `pytest tests/test_gallery_x11_wrapper_depth.py::test_main_check_mode_reports_problems_without_delegating tests/test_gallery_x11_wrapper_depth.py::test_main_runs_delegate_when_runtime_is_clean -q`

3. Existing X11 gallery runtime tests still pass against the underlying
   package module.
   VERIFY: `pytest tests/test_gallery_x11_runtime.py -q`

4. Fractal depth for `my-claw/tools/gallery_x11.py` reaches at least
   depth 2.
   VERIFY: `python - <<'PY'
import sys
sys.path.insert(0, "/Users/anthony/Programming/sdp-cli/src")
from sdp.fractal import classify_depth
result = classify_depth("my-claw/tools/gallery_x11.py")
print(result.depth, result.reason)
assert result.depth >= 2
PY`
