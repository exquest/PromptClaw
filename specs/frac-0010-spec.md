# Task frac-0010 Specification: Client Protocol Depth 2

## Problem Statement

`my-claw/tools/senseweave/generation/client_protocol.py` defines the
`GenerationResult` dataclass and the `GenerationClient` Protocol shared by
the Replicate, Modal, and local Ada backends. The fractal scanner classifies
the module at depth 1 (`all functions return trivial values`) because the
only function in the module — the protocol's `generate(...)` body — is `...`.
Callers that need to log a finished result, compare it against the original
request, or compute simple per-second cost metrics today re-derive that
plumbing in `cypherclaw_runtime`, `usage_journal`, and ad-hoc test fixtures.

The task is to deepen the module to a simple depth-2 implementation: one
straightforward path of typed, pure helpers around `GenerationResult` so any
client (Replicate, Modal, local) can produce a stable diagnostic dict, a
single-line operator log, a cost-per-second figure, and a typed pass/fail
outcome that compares the result against the request that produced it.

## Technical Approach

Extend `client_protocol.py` in place with pure helpers:

- `GenerationOutcome` — frozen dataclass with `passed: bool` and
  `reasons: tuple[str, ...]`. Empty `reasons` means the result satisfied
  every check.
- `cost_per_second(result)` — return `result.cost_usd / result.duration_actual_sec`,
  guarding against zero or negative durations by returning `0.0`.
- `result_summary(result)` — return a stable diagnostic dictionary with
  `model`, `sample_rate`, `duration_sec`, `cost_usd`, `cost_per_second_usd`,
  `latency_ms`, `request_id`, and `audio_path` keys (rounded numerics so
  log lines stay stable).
- `format_result_log_line(result)` — return a single space-separated line
  shaped `model=<m> dur=<sec>s cost=$<usd> latency=<ms>ms id=<request_id>`
  with `<unknown>` substituted for an empty `api_request_id`.
- `validate_generation_result(result, request, *, sample_rate_floor,
  duration_tolerance_sec)` — compare the result against the typed request:
  flag model mismatch, sample-rate floor breach, duration drift beyond
  tolerance, negative cost, and negative latency. Return a
  `GenerationOutcome` with the accumulated reason strings.

The `GenerationResult` dataclass and `GenerationClient` Protocol keep their
existing field order and contract so the Replicate, Modal, local-Ada, and
fake-client paths all keep working without modification. No new
dependencies, migrations, runtime state, secrets, or agent commands are
introduced.

## Edge Cases

- `cost_per_second` returns `0.0` for `duration_actual_sec <= 0.0`, so the
  helper is safe to call on degraded results that report zero seconds.
- `result_summary` rounds `duration_sec` to three decimals and `cost_usd` /
  `cost_per_second_usd` to four decimals so small floating-point jitter does
  not churn operator logs.
- `format_result_log_line` substitutes `<unknown>` for an empty
  `api_request_id` so log lines stay greppable when a backend has not yet
  populated the field.
- `validate_generation_result` accumulates every failure reason in a stable
  order (model, sample rate, duration, cost, latency) so callers see all
  problems on a single pass instead of failing on the first one.
- Sample rate is checked against an explicit floor (default `16_000`) and
  duration drift against an explicit tolerance (default `1.0` sec) so the
  helper can be reused for both production checks and lenient smoke tests.
- Startup identity hardening remains a regression anchor. The auto-generated
  bullets target the daemon startup subsystem, not this pure protocol module;
  existing `bootstrap_identity()` persistence and ordering tests in
  `test_first_boot.py` and `test_governor_integration.py` remain mandatory.

## Acceptance Criteria

1. `GenerationOutcome` is a frozen dataclass with `passed` and `reasons`
   fields exposed alongside `GenerationClient` and `GenerationResult`.
   VERIFY: `pytest tests/test_generation_client_protocol_depth.py::test_generation_outcome_is_frozen_dataclass -q`

2. `cost_per_second` returns dollars-per-second for a positive duration and
   `0.0` for a zero or negative duration.
   VERIFY: `pytest tests/test_generation_client_protocol_depth.py::test_cost_per_second_handles_positive_and_zero_durations -q`

3. `result_summary` emits a stable, operator-readable dictionary with rounded
   duration, cost, and per-second cost fields.
   VERIFY: `pytest tests/test_generation_client_protocol_depth.py::test_result_summary_is_stable_and_meaningful -q`

4. `format_result_log_line` produces a single-line summary and substitutes
   `<unknown>` for an empty `api_request_id`.
   VERIFY: `pytest tests/test_generation_client_protocol_depth.py::test_format_result_log_line_is_single_line_with_id_fallback -q`

5. `validate_generation_result` returns a passing `GenerationOutcome` when
   the result matches the request and accumulates reason strings for model,
   sample-rate, duration, cost, and latency violations.
   VERIFY: `pytest tests/test_generation_client_protocol_depth.py::test_validate_generation_result_accumulates_reasons -q`

6. Existing client protocol, Replicate, Modal, and local-Ada tests still
   pass.
   VERIFY: `pytest tests/test_generation_client_protocol.py tests/test_generation_replicate_retry.py tests/test_client_modal.py tests/test_client_local.py -q`

7. Fractal depth for
   `my-claw/tools/senseweave/generation/client_protocol.py` reaches at
   least depth 2.
   VERIFY: `python - <<'PY'
import sys
sys.path.insert(0, "/Users/anthony/Programming/sdp-cli/src")
from sdp.fractal import classify_depth
result = classify_depth("my-claw/tools/senseweave/generation/client_protocol.py")
print(result.depth, result.reason)
assert result.depth >= 2
PY`

8. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
