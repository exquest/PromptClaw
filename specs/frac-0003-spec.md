# Task frac-0003 Specification: Generation Worker Depth 2

## Problem Statement

`my-claw/tools/generation_worker.py` is the standalone CypherClaw generation
queue worker. It already starts the queue, writes diagnostic status JSON, and
handles SIGTERM/SIGINT, but the fractal scanner classifies it at depth 0
because `_amain()` contains a platform-compatibility `except
NotImplementedError` branch. The worker also lacks a public, typed config
surface that returns meaningful resolved runtime information without starting
the infinite worker loop.

The task is to deepen the module to a simple depth-2 implementation: one
straightforward path for resolving worker configuration, summarizing it,
building queue dependencies from it, and proving the entrypoint still works
end-to-end.

## Technical Approach

Extend `generation_worker.py` in place with a small typed configuration layer:

- `WorkerConfig` dataclass holding resolved data, queue DB, cache, samples,
  budget state, status path, status interval, and optional Replicate token.
- `load_worker_config(env=None)` to resolve environment-driven paths without
  mutating process state.
- `worker_runtime_summary(config)` to return operator-safe diagnostic
  information with secret values redacted to booleans.
- `build_queue(config=None)` to keep the current default behavior while
  allowing tests and callers to pass an explicit config object.
- `_amain(config=None)` to use the same config for queue construction and
  status output.

The signal fallback remains, but the function body should avoid the literal
`NotImplementedError` token that the current fractal scanner treats as an
unimplemented function. No new dependencies, migrations, provider secrets, or
database columns are required.

## Edge Cases

- Missing `REPLICATE_API_TOKEN` should not prevent startup; existing tests rely
  on tokenless worker startup and the queue can fail individual generation
  attempts later with normal diagnostics.
- Explicit env mappings must let tests resolve config without touching
  `os.environ`.
- Runtime summaries must never include the actual Replicate token.
- Signal handling must still work on platforms where `loop.add_signal_handler`
  is unsupported.
- The generated startup hardening checks are addressed as regression anchors:
  both daemon startup paths already call `bootstrap_identity()` before
  `FirstBootAnnouncer`, and startup identity persistence is tested for
  standalone and federated first boots.

## Acceptance Criteria

1. Worker config helpers produce meaningful resolved output without starting
   the worker loop.
   VERIFY: `pytest tests/test_generation_worker.py::test_load_worker_config_resolves_environment_paths tests/test_generation_worker.py::test_worker_runtime_summary_redacts_secret_token -q`

2. `build_queue(config)` constructs queue dependencies from the explicit
   config and initializes the expected on-disk roots.
   VERIFY: `pytest tests/test_generation_worker.py::test_build_queue_uses_explicit_config -q`

3. Existing worker status and signal behavior still works end-to-end.
   VERIFY: `pytest tests/test_generation_worker.py -q`

4. Fractal depth for `my-claw/tools/generation_worker.py` reaches at least
   depth 2.
   VERIFY: `python - <<'PY'
import sys
sys.path.insert(0, "/Users/anthony/Programming/sdp-cli/src")
from sdp.fractal import classify_depth
result = classify_depth("my-claw/tools/generation_worker.py")
print(result.depth, result.reason)
assert result.depth >= 2
PY`

5. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
