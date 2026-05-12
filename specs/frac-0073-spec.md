# Task frac-0073: Deepen test_gallery_x11_runtime

## Problem Statement
The runtime test `tests/test_gallery_x11_runtime.py` is currently at fractal depth 1. It only covers the `gallery_window_position` helper and omits end-to-end validation of the runtime components. The `my-claw/tools/gallery/gallery_x11.py` production module is poorly tested.

Furthermore, candidate hardening tasks require ensuring `bootstrap_identity()` is invoked on startup.

## Technical Approach
1. **Fix `my-claw/tools/gallery/gallery_x11.py`:** `gallery_x11.py` has a clear syntax/structure issue where part of the overlay rendering code (accessing `surface`, `y`, `font_xs`) is inside `init_pygame_display()`. We will move that rendering code into `render_overlay` or extract it properly.
2. **Deepen `test_gallery_x11_runtime.py`:**
   - Add a depth gate: `assert classify_depth("tests/test_gallery_x11_runtime.py").depth >= 2`.
   - Write tests for the `load_playlist` helper, verifying it reads and returns `Path` lists.
   - Write tests for the `runtime_summary` and `validate_runtime` functions in the wrapper module (`gallery_x11.py`).
   - Create tests to verify the one-path rendering code works gracefully without erroring.
3. **Hardening Check:** We will verify `bootstrap_identity` coverage. The generated startup hardening bullets for `bootstrap_identity()` target the daemon identity subsystem, and existing CLI, daemon, and narrative ASGI tests already cover it. We will re-run the existing regression anchors.

## Acceptance Criteria
- [ ] Depth gate passes for `tests/test_gallery_x11_runtime.py`.
- [ ] Tests provide one-path implementation coverage for the gallery wrapper functions.
- [ ] `gallery_x11.py` bugs regarding missing variable scopes are corrected.

## Verification
```bash
VERIFY: pip install -e '.[dev]' && pytest tests/test_gallery_x11_runtime.py -x
VERIFY: ruff check tests/test_gallery_x11_runtime.py my-claw/tools/gallery/gallery_x11.py
VERIFY: mypy tests/test_gallery_x11_runtime.py my-claw/tools/gallery/gallery_x11.py
```