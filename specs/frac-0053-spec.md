# Task frac-0053 Specification: test_genai Depth 2

## Problem Statement

`test_genai.py` is a root-level scratch script that creates a `google.genai`
client without an explicit API key, lists one model, and prints either the
client status or the raised exception. It currently classifies at fractal
depth 0 because it exposes no functions — only top-level script statements
inside a try/except — so the fractal scanner reports "no functions found".

That leaves callers and operator diagnostics with no module-owned way to:

- Construct a `google.genai` client through a typed entry point.
- Sample model names off a client without driving the full script.
- Run the smoke probe end-to-end and capture the result as a typed value
  (success flag, error message, model count, sampled model names) for tests
  or dashboards.
- Render the probe result as JSON-safe output or operator-friendly stdout
  lines without re-implementing the conditional script logic.

This task deepens the module to a simple depth-2 implementation: one
algorithm path per helper, meaningful output, and an end-to-end
`probe → summarize → render → main` flow that matches the existing CLI
behavior when the module is run as `python test_genai.py`.

## Technical Approach

- Add a frozen `GenAIProbeResult` dataclass with fields: `ok`, `error`,
  `model_count`, `sampled_models`.
- Add `create_genai_client(api_key: str | None = None) -> object` that
  imports `google.genai` lazily and returns either `genai.Client()` (default
  auth) or `genai.Client(api_key=api_key)` when an explicit key is provided.
- Add `list_model_names(client: object, *, limit: int) -> tuple[str, ...]`
  that iterates `client.models.list()` and returns up to `limit` model name
  strings in iteration order.
- Add `probe_genai_client(*, max_models: int = 1, client: object | None = None) -> GenAIProbeResult`
  that uses an injected client when given (so tests can drive the success
  and error paths without hitting the real API), otherwise calls
  `create_genai_client()`. The success path returns
  `GenAIProbeResult(ok=True, error="", model_count=len(names), sampled_models=names)`;
  any raised `Exception` is captured into an `ok=False` result with `error=str(exc)`,
  `model_count=0`, and `sampled_models=()`.
- Add `summarize_probe_result(result: GenAIProbeResult) -> dict[str, object]`
  that returns a JSON-safe dictionary with `ok`, `error`, `model_count`, and
  `sampled_models` (as a list).
- Add `format_probe_lines(result: GenAIProbeResult) -> tuple[str, ...]` that
  returns the canonical operator strings: on success, the leading
  "Successfully created client without explicit API key." header followed
  by one `"Model: <name>"` line per sampled model; on error, a single
  `"Error: <error>"` line. The lines match the original script output
  format byte-for-byte.
- Add `main() -> int` that runs `probe_genai_client()` and prints each line
  from `format_probe_lines(result)` via `print`. The `if __name__ == "__main__"`
  block calls `raise SystemExit(main())`.
- Use only the standard library plus the existing `google.genai` import.
  No new dependencies, migrations, database columns, secrets, runtime state
  files, HTTP routes, or auth changes are required. The narrative HTTP
  smoke surface (`/healthz`, `/readyz`, bearer auth) is not modified.

## Edge Cases

- `create_genai_client()` defers the `from google import genai` import until
  call time so importing `test_genai` does not fail when the optional
  `google-genai` dependency is absent.
- `list_model_names` uses a simple iteration with an `if` early break so
  the helper never exhausts the underlying iterator when `limit` is small.
- `probe_genai_client` injects the client through a keyword-only `client`
  parameter so tests can pass a fake client; the production `python test_genai.py`
  call path keeps the default `client=None` branch untouched.
- Any `Exception` raised by the client (auth failure, network error, missing
  default credentials) is folded into the result's `error` field rather than
  propagating, matching the original script's broad `except Exception`.
- `summarize_probe_result` always returns a JSON-safe dictionary
  (`json.dumps`-compatible) — `sampled_models` is rendered as a list, never
  a tuple.
- `format_probe_lines` produces the same leading "Successfully created
  client without explicit API key." header the original script printed and
  the same `"Model: <name>"` and `"Error: <error>"` lines, so the CLI output
  contract is preserved.
- `main` returns exit code `0` unconditionally; the broad `except` inside
  `probe_genai_client` keeps non-zero exits out of the smoke path.
- The generated startup hardening checks (`/healthz` + `/readyz` endpoints,
  bearer-token auth, `tests/test_smoke_narrative_script.py` regression
  anchor) target narrative HTTP startup wiring outside `test_genai.py`.
  This task re-runs those anchors to prove the genai smoke deepening does
  not affect the narrative HTTP contract.

## Acceptance Criteria

1. `test_genai` imports successfully and exposes the new probe surface.
   VERIFY: `pytest tests/test_test_genai_depth.py::test_test_genai_imports_with_probe_surface -q`

2. `create_genai_client` returns a `google.genai` client both when given
   an explicit API key and when the default-auth env path is populated.
   VERIFY: `pytest tests/test_test_genai_depth.py::test_create_genai_client_constructs_client -q`

3. `list_model_names` yields model names from the client up to the limit.
   VERIFY: `pytest tests/test_test_genai_depth.py::test_list_model_names_respects_limit -q`

4. `probe_genai_client` returns a populated `GenAIProbeResult` on the
   success path through an injected client.
   VERIFY: `pytest tests/test_test_genai_depth.py::test_probe_genai_client_success_path -q`

5. `probe_genai_client` captures raised exceptions into an `ok=False`
   result with the stringified error and zero models.
   VERIFY: `pytest tests/test_test_genai_depth.py::test_probe_genai_client_error_path -q`

6. `summarize_probe_result` emits a JSON-safe dictionary with
   `sampled_models` as a list and `model_count` matching the result.
   VERIFY: `pytest tests/test_test_genai_depth.py::test_summarize_probe_result_is_json_safe -q`

7. `format_probe_lines` renders the canonical success header and per-model
   lines on the success path and a single error line on the error path.
   VERIFY: `pytest tests/test_test_genai_depth.py::test_format_probe_lines_matches_canonical_output -q`

8. `main` runs `probe → format → print` end-to-end and returns exit code
   `0`.
   VERIFY: `pytest tests/test_test_genai_depth.py::test_main_returns_zero_and_prints_probe_lines -q`

9. Fractal depth for `test_genai.py` reaches at least depth 2.
   VERIFY: `pytest tests/test_test_genai_depth.py::test_test_genai_module_reaches_depth_two -q`

10. Startup identity hardening remains covered for CLI startup and
    standalone/federated first-boot persistence.
    VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

11. Narrative HTTP smoke surface (`/healthz`, `/readyz`, bearer auth)
    remains green.
    VERIFY: `pytest tests/test_smoke_narrative_script.py -q`

12. Full project validation remains clean.
    VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
