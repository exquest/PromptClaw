# Task frac-0083 Specification: test_image_api_s3_uploader Depth 2

## Problem Statement

`tests/test_image_api_s3_uploader.py` already has basic tests for `upload_image`.
The missing depth-2 work is a named end-to-end test path that proves the helper functions and upload functions produce meaningful output together.

The affected production surface already implements the simple one-path S3 uploader and its summary features:

- `upload_image`
- `guess_content_type`
- `categorize_upload_size`
- `build_upload_report`
- `summarize_upload`
- `summarize_upload_report`

This task deepens the test surface without changing existing locked assertions unless the new red tests expose a concrete production gap.

## Technical Approach

- Preserve existing assertions in `tests/test_image_api_s3_uploader.py`.
- Add a depth gate at `tests/test_test_image_api_s3_uploader_depth.py` that requires `tests/test_image_api_s3_uploader.py` to contain `TestImageApiS3UploaderEndToEnd` and to classify at depth >= 2 through the repo-local `sdp.fractal.classify_depth`.
- Append `TestImageApiS3UploaderEndToEnd` to `tests/test_image_api_s3_uploader.py`. The class will drive one deterministic path through uploading an image, guessing its content type, generating an upload report, and outputting JSON-safe summaries.
- Use only stdlib test support and existing imports.
- Treat the generated startup identity hardening checks as regression anchors.

## Edge Cases

- This depth-2 pass intentionally exercises one deterministic happy path rather than expanding malformed-input matrices.
- The summary metadata should remain JSON-safe.
- No new dependencies, migrations, or database columns are introduced.

## Acceptance Criteria

1. Existing S3 uploader assertions remain green.
   VERIFY: `pytest tests/test_image_api_s3_uploader.py -q`

2. The new depth gate confirms `tests/test_image_api_s3_uploader.py` reaches depth >= 2 and contains `TestImageApiS3UploaderEndToEnd`.
   VERIFY: `pytest tests/test_test_image_api_s3_uploader_depth.py -q`

3. `TestImageApiS3UploaderEndToEnd` drives one meaningful public path through guessing content type, uploading an image, summarizing the upload, categorizing size, building a report, and summarizing the report.
   VERIFY: `pytest tests/test_image_api_s3_uploader.py::TestImageApiS3UploaderEndToEnd -q`

4. Startup identity hardening remains covered for CLI startup, standalone and federated identity persistence, daemon bootstrap-before-announcer ordering, and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing notes mention the frac-0083 s3-uploader depth-2 work.
   VERIFY: `grep -n "frac-0083" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
