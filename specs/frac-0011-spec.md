# Task frac-0011 Specification: Local Client Depth 2

## Problem Statement

`my-claw/tools/senseweave/generation/client_local.py` still implements
`LocalAdaClient.generate(...)` as a pure `NotImplementedError` stub. The
fractal scanner classifies the module at depth 0 (`all functions raise
NotImplementedError`), and the `"local"` backend cannot exercise the
generation queue, cache, storage, or diagnostics path end to end without
switching to Replicate or Modal.

The task is to deepen the local client to a simple depth-2 implementation:
one deterministic offline synthesis path that writes a small WAV preview and
returns meaningful generation metadata. This is not the future GPU Ada model;
it is the minimum local backend needed for offline end-to-end operation and
for callers to receive a real `GenerationResult` / result payload.

## Technical Approach

Implement `LocalAdaClient` as a stdlib-only deterministic preview backend:

- Keep the existing `generate(self, request: Any) -> Any` implementation
  signature so the existing signature parity tests with `ReplicateClient`
  remain valid.
- Add `LocalAdaClient(output_dir=None, sample_rate=48000, clock=time.monotonic)`
  so tests can write into temporary directories and pin latency without
  touching global runtime state.
- For typed `GenerationRequest` inputs, write a mono PCM WAV under
  `output_dir` and return a `GenerationResult` with:
  `audio_path`, `sample_rate`, `duration_actual_sec`, `model_used`,
  `cost_usd=0.0`, `latency_ms`, and a stable `api_request_id`.
- For legacy mapping inputs, use the same WAV synthesis path and return a
  dictionary that exposes `audio_path`, `sample_rate`, `duration_actual_sec`,
  `model_used`, `cost_usd`, `latency_ms`, and `prediction_id`, so the queue,
  cache, budget, and storage duck-typed helpers can process it end to end.
- Add `local_request_id(request)` and `local_request_summary(request)` helpers
  so callers and tests can inspect the resolved local request without opening
  the WAV file.
- Derive a stable local request id from `request.hash()` / `request_hash` when
  available, otherwise from prompt, duration, seed, and model fields.
- Synthesize one deterministic tone per request. The seed and prompt choose
  a bounded frequency; the waveform has enough amplitude to be non-silent but
  remains safely below clipping.

No new dependencies, database migrations, provider secrets, or agent command
strings are introduced.

## Edge Cases

- Typed `GenerationRequest` validation remains the authority for duration,
  model, and centroid shape. The local client does not duplicate those checks.
- Legacy mapping requests use simple defaults only when a field is absent:
  duration `5.0`, seed `0`, model `"local-ada-preview"`, and empty prompt.
- The WAV path is deterministic for the same request id and is overwritten by
  repeat local generations. This keeps the one-path implementation simple and
  makes repeat runs idempotent for tests.
- The generated audio is local-only and cost-free (`cost_usd=0.0`); budget
  code can still record it safely because zero-cost records are already a
  supported no-op.
- Startup identity hardening remains a regression anchor. This task does not
  alter daemon startup, but verification must still exercise the existing
  standalone/federated persistence and `bootstrap_identity()` ordering tests.

## Acceptance Criteria

1. `local_request_id` and `local_request_summary` return stable,
   operator-readable metadata for both typed and mapping requests.
   VERIFY: `pytest tests/test_client_local_depth.py::test_local_request_summary_is_stable_and_meaningful -q`

2. `LocalAdaClient.generate(GenerationRequest)` writes a real WAV file and
   returns a `GenerationResult` with meaningful model, duration, sample-rate,
   request-id, cost, and latency metadata.
   VERIFY: `pytest tests/test_client_local_depth.py::test_local_ada_client_generates_typed_wav_result -q`

3. Legacy mapping requests use the same local synthesis path and return a
   duck-typed payload that queue/cache/storage callers can consume end to end.
   VERIFY: `pytest tests/test_client_local_depth.py::test_local_ada_client_mapping_request_returns_end_to_end_payload -q`

4. Local generation is deterministic for the same request: repeat runs resolve
   to the same id/path and write the same WAV bytes.
   VERIFY: `pytest tests/test_client_local_depth.py::test_local_generation_is_deterministic_for_same_request -q`

5. Existing client protocol, Replicate, Modal, and local-client regression
   tests still pass.
   VERIFY: `pytest tests/test_generation_client_protocol.py tests/test_generation_replicate_retry.py tests/test_client_modal.py tests/test_client_local.py tests/test_client_local_depth.py -q`

6. Fractal depth for `my-claw/tools/senseweave/generation/client_local.py`
   reaches at least depth 2.
   VERIFY: `python - <<'PY'
import sys
sys.path.insert(0, "/Users/anthony/Programming/sdp-cli/src")
from sdp.fractal import classify_depth
result = classify_depth("my-claw/tools/senseweave/generation/client_local.py")
print(result.depth, result.reason)
assert result.depth >= 2
PY`

7. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

8. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
