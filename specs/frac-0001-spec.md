# Task frac-0001 Specification: Catalog Depth 2

## Problem Statement

`my-claw/curriculum/catalog.py` contains the authoritative 40-course EMSD
catalog, but its callable surface is still mostly shallow accessors. The
fractal scanner classifies it at depth 1 because most functions return direct
constants or simple projections. The catalog needs a simple one-path layer that
returns meaningful grouped/indexed output and supports an end-to-end catalog
health check without adding a new subsystem.

## Technical Approach

Extend the existing catalog module in place with pure, typed helper functions:

- group courses by category
- select courses by semester
- expose a prerequisite graph
- index exercises by stable course/exercise key
- build a compact catalog summary
- validate the catalog's basic internal consistency

The functions will use only the existing dataclasses and `COURSE_CATALOG`.
They will be deterministic, stdlib-only, and side-effect free. Existing catalog
objects, generated scaffold behavior, and verifier behavior remain unchanged.

## Edge Cases

- Unknown category names should return an empty tuple rather than raising.
- Semesters with no courses should return an empty tuple.
- Duplicate course codes, duplicate exercise IDs within a course, missing
  prerequisites, invalid categories, empty exercise expected features, and
  malformed verifier names should be reported by validation.
- The current committed catalog should validate cleanly.
- No database migrations are applicable because the catalog is static Python
  metadata.
- Startup identity hardening is kept as a verification anchor only. Existing
  daemon startup already calls `bootstrap_identity()` before
  `FirstBootAnnouncer` in both entrypoints.

## Acceptance Criteria

1. Catalog helpers produce meaningful grouped, filtered, indexed, and summary
   output from the existing catalog.
   VERIFY: `pytest tests/test_emsd_catalog_depth.py::test_catalog_depth_helpers_return_meaningful_output -q`

2. Catalog validation passes for the committed catalog and reports clear errors
   for an invalid one.
   VERIFY: `pytest tests/test_emsd_catalog_depth.py::test_catalog_validation_reports_inconsistencies -q`

3. Existing curriculum scaffold and verifier behavior remains compatible.
   VERIFY: `pytest tests/test_emsd_curriculum.py tests/test_executable_curriculum.py -q`

4. Fractal depth for `my-claw/curriculum/catalog.py` reaches at least depth 2.
   VERIFY: `python - <<'PY'
import sys
sys.path.insert(0, "/Users/anthony/Programming/sdp-cli/src")
from sdp.fractal import classify_depth
result = classify_depth("my-claw/curriculum/catalog.py")
print(result.depth, result.reason)
assert result.depth >= 2
PY`

5. Startup identity hardening remains covered for standalone/federated startup
   paths.
   VERIFY: `pytest tests/test_first_boot.py tests/test_governor_integration.py -q`
