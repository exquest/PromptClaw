# Task frac-0064 Specification: test_client_local Depth 2

## Problem Statement

`tests/test_client_local.py` owns the compact regression coverage for
`my-claw/tools/senseweave/generation/client_local.py`, the offline local
generation backend used by CypherClaw generation workflows when a network GPU
backend is not needed. The production module already provides meaningful
one-path behavior: `LocalAdaClient.generate()` accepts a typed
`GenerationRequest` or legacy mapping, writes a deterministic mono WAV preview,
returns typed `GenerationResult` metadata for typed requests, returns a
queue/cache/storage-friendly mapping for legacy callers, emits stable local
request ids, and exposes an operator-readable request summary.

Exploration found the generated task depth is stale in this checkout:
`sdp.fractal.classify_depth("tests/test_client_local.py")` already reports
depth 2 (`simple implementations (44 lines)`), while
`sdp.fractal.classify_depth("my-claw/tools/senseweave/generation/client_local.py")`
reports depth 3. This task still improves the requested affected surface by
making the depth requirement explicit and by adding end-to-end coverage to the
primary `tests/test_client_local.py` file. Existing assertions are preserved
unchanged, and production behavior is not expected to change.

## Technical Approach

- Preserve `my-claw/tools/senseweave/generation/client_local.py` behavior unless
  the new tests expose a real regression. The source already produces
  meaningful output and needs no planned production change.
- Add a dedicated test-file depth gate at
  `tests/test_test_client_local_depth.py`. Because the file already reports
  depth 2, the red phase is pinned by requiring the new
  `TestLocalAdaClientEndToEnd` class to exist in `tests/test_client_local.py`
  as well as requiring `classify_depth("tests/test_client_local.py").depth >= 2`.
- Append `TestLocalAdaClientEndToEnd` to `tests/test_client_local.py`. The new
  methods use looped and table-driven assertions so the scanner records real
  integration test logic rather than trivial one-call checks.
- Drive one simple public path through the existing API:
  - Verify typed `GenerationRequest` inputs produce deterministic WAV files,
    typed metadata, nonzero frames, and stable request ids across multiple
    prompts/seeds.
  - Verify legacy mapping inputs produce end-to-end payloads with path,
    duration, model, latency, cost, prediction id, request id, and summary
    fields suitable for queue/cache/storage call sites.
  - Verify request summaries and legacy payloads are JSON-safe and stable.
  - Verify repeated generation for identical mapping requests rewrites the same
    deterministic bytes and keeps the same local id/path.
  - Verify public result summaries validate against the shared protocol helper
    for typed requests.
- Keep the change stdlib-only apart from the existing generation-request test
  dependency on NumPy already used elsewhere in the test suite. No new
  dependencies, migrations, provider secrets, runtime state files, database
  columns, HTTP routes, or auth changes are required.
- Treat the generated startup hardening bullets as mandatory verification
  anchors. Existing startup identity tests cover `bootstrap_identity()`
  persistence, standalone/federated reuse, CLI startup invocation,
  bootstrap-before-`FirstBootAnnouncer` ordering, and ASGI app import
  persistence; those tests are re-run in this task.

## Edge Cases

- The depth gate asserts `depth >= 2` rather than an exact depth or reason so
  later test improvements remain compatible.
- Because the requested "depth 0" starting point is stale, the red phase uses a
  locked class-presence assertion for the new end-to-end coverage rather than
  relying only on the classifier.
- Existing tests and assertions in `tests/test_client_local.py` remain
  unchanged; new coverage is appended in a separate class.
- WAV assertions inspect container metadata and the first frames instead of
  asserting exact samples beyond deterministic repeat-generation bytes.
- Latency assertions use an injectable clock for typed requests and a
  nonnegative bound for legacy mapping requests.
- No startup identity source changes are expected because the existing tree
  already has dedicated regression anchors for the generated hardening items.

## Acceptance Criteria

1. Existing local-client behavioral tests remain unchanged and green.
   VERIFY: `pytest tests/test_client_local.py -q`

2. The new red-phase depth gate confirms `tests/test_client_local.py` reaches
   at least depth 2 and contains the new end-to-end class.
   VERIFY: `pytest tests/test_test_client_local_depth.py -q`

3. The new end-to-end class covers typed request WAV generation, mapping
   payload shape, summary stability, deterministic repeat generation,
   JSON-safe diagnostics, and shared protocol validation from the existing
   public API.
   VERIFY: `pytest tests/test_client_local.py::TestLocalAdaClientEndToEnd -q`

4. The production local-client source remains unchanged in behavior and still
   works through the public API.
   VERIFY: `python -c "import os, sys, wave; from pathlib import Path; sys.path.insert(0, os.path.join(os.getcwd(), 'my-claw', 'tools')); from senseweave.generation.client_local import LocalAdaClient, local_request_id; client=LocalAdaClient(output_dir='/tmp/promptclaw-local-client-smoke', sample_rate=8000); req={'request_hash':'frac-0064-smoke','prompt':'steady local preview','duration_sec':0.25,'seed':11,'model':'musicgen-medium'}; result=client.generate(req); path=Path(result['audio_path']); assert result['prediction_id']==local_request_id(req) and path.exists(); wav=wave.open(str(path), 'rb'); assert wav.getframerate()==8000 and wav.getnframes()==2000; wav.close(); print(result['prediction_id'], result['duration_actual_sec'])"`

5. Startup identity hardening remains covered for first-run identity
   persistence, standalone/federated reuse, CLI startup invocation,
   bootstrap-before-announcer ordering, and ASGI app import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing progress and changelog notes mention the depth-2 local-client
   test coverage.
   VERIFY: `grep -n "frac-0064" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
