# Task frac-0049 Specification: image_api S3 Uploader Depth 2

## Problem Statement

`src/cypherclaw/image_api/s3_uploader.py` is the boundary that pushes finished
generated images into the public CT Marketing bucket. Today the module exposes
only `upload_image(...)` plus the `UploadResult` dataclass and an internal
`_build_client(...)`. The fractal classifier puts it at depth 1
(`2/3 trivial, 1 real`) because the only real-logic surface is `upload_image`
itself; everything else is a thin pass-through.

Operators and downstream callers (worker batches, status reporting, dry-run
dashboards) have no module-owned way to:

- Map a generated filename to its S3 `Content-Type` without re-implementing
  the suffix → MIME table at every call site.
- Aggregate a batch of `UploadResult` records into a typed report (bucket,
  object count, total bytes, keys, urls) without iterating manually.
- Bucket an `UploadResult` into a coarse size band (empty / small / medium
  / large) for operator dashboards and structured logs.
- Render a JSON-safe summary of one upload or a batch report suitable for
  `json.dumps` without a custom encoder.

This task deepens the module to a simple depth-2 implementation by adding
typed helpers and one aggregate-report path around the existing upload
behavior. The existing `upload_image` signature and S3 side effects are
preserved.

## Technical Approach

- Add module-level constants:
  - `DEFAULT_CACHE_CONTROL: str` — the existing immutable cache header used by
    `upload_image`, hoisted out of the function body.
  - `DEFAULT_CONTENT_TYPE: str = "application/octet-stream"`.
  - `CONTENT_TYPE_BY_EXTENSION: Mapping[str, str]` — canonical lowercase
    suffix → MIME mapping for `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`.
- Add `guess_content_type(filename: str) -> str` that returns the
  `CONTENT_TYPE_BY_EXTENSION` value for the lowercased trailing suffix and
  falls back to `DEFAULT_CONTENT_TYPE` when the filename has no suffix or an
  unknown one. One algorithm path.
- Add a frozen `UploadReport` dataclass with fields
  `bucket`, `object_count`, `total_bytes`, `keys: tuple[str, ...]`, and
  `urls: tuple[str, ...]`.
- Add `build_upload_report(results: Iterable[UploadResult]) -> UploadReport`
  that materializes the iterable once, aggregates `bytes_uploaded`, and
  collects keys / urls in scaffold order. Empty input yields `bucket=""`,
  `object_count=0`, `total_bytes=0`, and empty key / url tuples.
- Add `categorize_upload_size(result: UploadResult) -> str` that returns
  one of `"empty"`, `"small"`, `"medium"`, or `"large"` using fixed byte
  thresholds (`< 1`, `< 64 KiB`, `< 1 MiB`, otherwise large).
- Add `summarize_upload(result: UploadResult) -> dict[str, object]` that
  emits a JSON-safe per-result summary including `bucket`, `key`, `url`,
  `bytes_uploaded`, and `size_category`.
- Add `summarize_upload_report(report: UploadReport) -> dict[str, object]`
  that emits a JSON-safe report summary with lists for `keys` and `urls`
  rather than tuples.
- Keep `upload_image(...)` signature and behavior identical. Internally
  swap the literal cache header for `DEFAULT_CACHE_CONTROL`.
- Use only the standard library plus the module's existing imports.
- No new dependencies, migrations, database columns, secrets, runtime state
  files, HTTP endpoints, or auth headers. This task does not modify the
  narrative HTTP service surface (`/healthz`, `/readyz`, bearer-token
  hardening) — `tests/test_smoke_narrative_script.py` remains the regression
  anchor for that contract.

## Edge Cases

- Filenames without a `.` classify as `DEFAULT_CONTENT_TYPE`.
- Suffix matching is case-insensitive: `IMAGE.PNG` resolves to `image/png`.
- Unknown suffixes (for example `.tiff`) classify as `DEFAULT_CONTENT_TYPE`.
- `build_upload_report` consumes any `Iterable[UploadResult]`, including
  generators, by materializing once before aggregation.
- `build_upload_report` on an empty iterable returns
  `UploadReport(bucket="", object_count=0, total_bytes=0, keys=(), urls=())`
  rather than raising.
- `categorize_upload_size` thresholds are exact: 0 → `"empty"`,
  `1..65_535` → `"small"`, `65_536..1_048_575` → `"medium"`,
  `>= 1_048_576` → `"large"`.
- `summarize_upload` and `summarize_upload_report` are JSON-safe
  (`json.dumps(summary)` succeeds with no custom encoder).
- `upload_image` continues to issue exactly one `put_object` call per
  invocation with the same `Bucket`, `Key`, `Body`, `ContentType`, and
  cache header (sourced from `DEFAULT_CACHE_CONTROL`).
- Startup identity hardening remains outside this module; existing
  `bootstrap_identity()` coverage in `tests/test_cli_identity_hardening.py`,
  `tests/test_first_boot.py::TestStartupIdentityPersistence`, and
  `tests/test_governor_integration.py::TestStartupIdentityWiring` is
  unaffected.

## Acceptance Criteria

1. Existing s3_uploader behavior remains unchanged.
   VERIFY: `pytest tests/test_image_api_s3_uploader.py -q`

2. `guess_content_type` returns canonical MIME types for known suffixes and
   `DEFAULT_CONTENT_TYPE` for unknown or missing suffixes.
   VERIFY: `pytest tests/test_image_api_s3_uploader_depth.py::test_guess_content_type_classifies_known_and_unknown -q`

3. `build_upload_report` aggregates a batch of `UploadResult` records into
   a typed report with matching bucket, object count, total bytes, keys,
   and urls.
   VERIFY: `pytest tests/test_image_api_s3_uploader_depth.py::test_build_upload_report_aggregates_results -q`

4. `build_upload_report` on an empty iterable returns an empty
   `UploadReport` without raising.
   VERIFY: `pytest tests/test_image_api_s3_uploader_depth.py::test_build_upload_report_handles_empty_iterable -q`

5. `categorize_upload_size` maps `bytes_uploaded` to one of
   `empty / small / medium / large` using the documented thresholds.
   VERIFY: `pytest tests/test_image_api_s3_uploader_depth.py::test_categorize_upload_size_thresholds -q`

6. `summarize_upload` and `summarize_upload_report` are JSON-safe and
   expose lists for keys/urls.
   VERIFY: `pytest tests/test_image_api_s3_uploader_depth.py::test_summarize_helpers_are_json_safe -q`

7. `upload_image` still issues one `put_object` call with the canonical
   cache header sourced from `DEFAULT_CACHE_CONTROL`.
   VERIFY: `pytest tests/test_image_api_s3_uploader_depth.py::test_upload_image_uses_default_cache_control -q`

8. Fractal depth for `src/cypherclaw/image_api/s3_uploader.py` reaches at
   least depth 2.
   VERIFY: `pytest tests/test_image_api_s3_uploader_depth.py::test_s3_uploader_module_reaches_depth_two -q`

9. Startup identity hardening remains covered for CLI startup and
   standalone/federated first-boot persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

10. Narrative HTTP smoke surface (`/healthz`, `/readyz`, bearer auth)
    remains green.
    VERIFY: `pytest tests/test_smoke_narrative_script.py -q`

11. Full project validation remains clean.
    VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
