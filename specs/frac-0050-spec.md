# Task frac-0050 Specification: image_api Schemas Depth 2

## Problem Statement

`src/cypherclaw/image_api/schemas.py` owns the Pydantic wire contract for the
CypherClaw image API: submit requests, submit/status responses, job lifecycle
status values, and the normalized `InternalSpec` consumed by the parser,
Gemini backend, worker, and FastAPI app.

The module currently classifies at fractal depth 0 because it exposes only data
models and no functions. The schemas work end-to-end, but callers and operator
diagnostics have no module-owned way to produce meaningful JSON-safe summaries
from a `StatusResponse` or `InternalSpec` without duplicating lifecycle and
dimension logic outside the schema boundary.

This task deepens the schema module to a simple depth-2 implementation by adding
one typed status-summary path and one typed internal-spec profile path. Existing
request/response fields, validation behavior, API routes, worker behavior, and
database persistence remain unchanged.

## Technical Approach

- Add lifecycle constants:
  - `TERMINAL_JOB_STATUSES: frozenset[JobStatus]` for `completed` and `failed`.
  - `ACTIVE_JOB_STATUSES: tuple[JobStatus, ...]` for `queued`, `running`, and
    `uploading`.
- Add `is_terminal_status(status: JobStatus) -> bool`.
- Add a frozen `JobLifecycleSummary` dataclass with fields:
  `job_id`, `project_slug`, `status`, `is_terminal`, `output_count`,
  `has_outputs`, `has_error`, `cost_usd`, and `content_piece_id`.
- Add `build_job_lifecycle_summary(response: StatusResponse) -> JobLifecycleSummary`
  that derives lifecycle facts from one status response.
- Add `summarize_status_response(response: StatusResponse) -> dict[str, object]`
  that emits a JSON-safe dictionary with `status` as the enum value.
- Add a frozen `InternalSpecProfile` dataclass with fields:
  `project`, `filename`, `width`, `height`, `pixel_count`, `megapixels`,
  `prompt_preview`, `prompt_length`, `has_style`, `style`,
  `model_override`, and `content_piece_id`.
- Add `build_internal_spec_profile(spec: InternalSpec, *, prompt_preview_chars: int = 96) -> InternalSpecProfile`
  that derives image dimensions, prompt preview, prompt length, style presence,
  and override metadata from the normalized spec.
- Add `summarize_internal_spec(spec: InternalSpec, *, prompt_preview_chars: int = 96) -> dict[str, object]`
  that emits a JSON-safe dictionary for logs, dashboards, and tests.
- Keep all Pydantic schema class fields and `model_config` settings unchanged.
- Use only the standard library plus existing Pydantic imports. No migrations,
  database columns, dependencies, provider secrets, runtime files, HTTP routes,
  or auth behavior changes are required.

## Edge Cases

- Only `completed` and `failed` are terminal; `queued`, `running`, and
  `uploading` remain active.
- A completed status response with output URLs reports `has_outputs=True`,
  `output_count=len(output_urls)`, and `has_error=False`.
- A failed status response with an error reports `is_terminal=True`,
  `has_error=True`, and keeps `output_count=0` when there are no URLs.
- Prompt previews collapse internal whitespace before truncation so summaries
  are single-line and log-friendly.
- `prompt_preview_chars` is treated as a simple positive budget; the default is
  sufficient for operator summaries. This task intentionally avoids broader
  validation paths.
- `megapixels` is rounded to three decimal places from `width * height`.
- Summary dictionaries are directly serializable with `json.dumps`.
- Existing image API parser, worker, app, jobs DB, and S3 uploader tests remain
  green, proving the schema additions do not alter end-to-end behavior.
- The generated startup hardening checks target `bootstrap_identity()` startup
  wiring. Current CLI, daemon, and narrative API startup paths already call
  `bootstrap_identity()` before dependent first-boot work; this task re-runs
  those anchors instead of modifying unrelated startup code.

## Acceptance Criteria

1. Existing image API behavior remains unchanged across parser, worker, app,
   jobs DB, and S3 uploader coverage.
   VERIFY: `pytest tests/test_image_api_spec_parser.py tests/test_image_api_worker.py tests/test_image_api_app.py tests/test_image_api_jobs_db.py tests/test_image_api_s3_uploader.py -q`

2. `is_terminal_status` classifies `completed` and `failed` as terminal and
   `queued`, `running`, and `uploading` as active.
   VERIFY: `pytest tests/test_image_api_schemas_depth.py::test_is_terminal_status_classifies_lifecycle_values -q`

3. `build_job_lifecycle_summary` produces meaningful lifecycle output for a
   completed `StatusResponse`.
   VERIFY: `pytest tests/test_image_api_schemas_depth.py::test_build_job_lifecycle_summary_for_completed_response -q`

4. `build_job_lifecycle_summary` produces meaningful lifecycle output for a
   failed `StatusResponse`.
   VERIFY: `pytest tests/test_image_api_schemas_depth.py::test_build_job_lifecycle_summary_for_failed_response -q`

5. `build_internal_spec_profile` derives dimensions, pixel count, megapixels,
   prompt preview, prompt length, style presence, and model override metadata
   from an `InternalSpec`.
   VERIFY: `pytest tests/test_image_api_schemas_depth.py::test_build_internal_spec_profile_derives_image_metadata -q`

6. `summarize_status_response` and `summarize_internal_spec` return JSON-safe
   dictionaries with enum values rendered as strings.
   VERIFY: `pytest tests/test_image_api_schemas_depth.py::test_schema_summaries_are_json_safe -q`

7. Fractal depth for `src/cypherclaw/image_api/schemas.py` reaches at least
   depth 2.
   VERIFY: `pytest tests/test_image_api_schemas_depth.py::test_image_api_schemas_module_reaches_depth_two -q`

8. Startup identity hardening remains covered for CLI startup and
   standalone/federated first-boot persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

9. Narrative ASGI startup identity persistence remains green.
   VERIFY: `pytest tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

10. Full project validation remains clean.
    VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
