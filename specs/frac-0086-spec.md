# Task frac-0086 Specification: Listener Review Depth 2

## Problem Statement

`tests/test_listener_review.py` currently verifies that the listener-review
operator guide, review log template, and documented ablation CLI are present.
The runtime module behind those tests is still only an artifact-presence
validator. Depth 2 requires a simple one-path implementation whose functions
produce meaningful output and can be driven end-to-end through the existing
listener-review artifacts.

The recurring startup identity hardening items are already covered in this
checkout by CLI, daemon-ordering, first-boot persistence, and narrative ASGI
startup tests. This task will re-run those tests as regression anchors rather
than changing startup flow without an identified gap.

## Technical Approach

- Extend `my-claw/tools/senseweave/render/listener_review.py` with typed,
  stdlib-only review-log helpers:
  - `ListenerReviewEntry` for one parsed review row.
  - `ListenerReviewReport` for artifact status plus parsed entries.
  - `parse_review_log(...)` to parse the existing markdown table.
  - `build_listener_review_report(...)` to combine artifact validation,
    required-field validation, CLI references, and parsed entries.
  - `summarize_listener_review_report(...)` to emit JSON-safe operator output.
- Keep `validate_listener_review_artifacts()` behavior compatible: it returns
  `True` only when the guide/log exist and the guide references the ablation
  CLI.
- Deepen `tests/test_listener_review.py` with an end-to-end class that drives
  the public report API through temporary workflow artifacts.
- Add `tests/test_test_listener_review_depth.py` to pin the depth gate and the
  end-to-end class name.

## Edge Cases

- Empty review logs should parse to zero entries while preserving artifact
  status in the report.
- Missing required table columns should surface in the report instead of
  raising.
- Markdown separator rows should be ignored.
- Unknown `action` values are reported in `invalid_actions`; no broader action
  policy is introduced.
- Startup identity persistence is not reimplemented here; existing standalone
  and federated boot tests are the regression surface.

## Acceptance Criteria

1. Existing listener-review artifact checks remain green.
   VERIFY: `pytest tests/test_listener_review.py::test_validate_listener_review_artifacts tests/test_listener_review.py::test_ablation_cli_prog_matches_documented_name -q`

2. Review-log parsing returns typed entries with meaningful fields from the
   markdown table.
   VERIFY: `pytest tests/test_listener_review.py::ListenerReviewEndToEndTests::test_parse_review_log_returns_typed_entries -q`

3. The listener-review report combines artifact status, required columns,
   parsed entries, action counts, and JSON-safe summary output.
   VERIFY: `pytest tests/test_listener_review.py::ListenerReviewEndToEndTests -q`

4. The listener-review test file is pinned at fractal depth 2 and contains the
   end-to-end class.
   VERIFY: `pytest tests/test_test_listener_review_depth.py -q`

5. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Full validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`

