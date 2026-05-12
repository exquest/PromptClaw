# Task frac-0096 Specification: test_ollama_health Depth 2

## Problem Statement

`tests/test_ollama_health.py` covers the Ollama health helper at focused level:
it asserts the happy-path `check_health` URL and timeout, the connection-error
fallback for `check_health`, the loaded-model name extraction by
`check_models`, and the connection-error fallback for `check_models`. The
production module `my-claw/tools/ollama_health.py` already exposes the simple
one-path implementation: `_ps_url(port)`, `_read_ps(port, timeout)`,
`check_health(port)`, and `check_models(port)`.

The missing frac-0096 work is to make the depth-2 contract explicit for this
test module: a deterministic depth gate plus a named end-to-end class that
drives one meaningful Ollama health-probe lifecycle through the existing
public surface (`check_health` → `check_models`), confirms the URL/timeout
plumbing, exercises the connection-error fallback, and round-trips a JSON-safe
diagnostic snapshot.

The generated startup identity hardening bullets target the existing identity
startup subsystem. This checkout already wires `bootstrap_identity()` into CLI
startup, daemon bootstrap before `FirstBootAnnouncer`, and narrative ASGI
import startup, with regression tests covering standalone/federated identity
persistence. This task keeps those tests as mandatory regression anchors
rather than modifying unrelated startup code without a discovered gap.

## Technical Approach

- Add `tests/test_test_ollama_health_depth.py` with a deterministic depth
  gate requiring `tests/test_ollama_health.py` to contain
  `OllamaHealthEndToEndTests` and classify at depth >= 2 through the
  repo-local `sdp.fractal.classify_depth`.
- Confirm the red phase by running the new depth gate before the end-to-end
  class exists.
- Append `OllamaHealthEndToEndTests` to `tests/test_ollama_health.py` without
  modifying the existing locked assertions.
- Drive one Ollama health-probe lifecycle inside the class:
  - patch `urlopen` with a recording fake that returns one realistic `/api/ps`
    payload (two named models plus one malformed entry without a name);
  - call `check_health(11434)` and confirm it returns `True`, the recorded URL
    is `http://localhost:11434/api/ps`, and the recorded timeout is the module
    default `DEFAULT_TIMEOUT_S` (5 seconds);
  - call `check_models(11434)` and confirm only the well-formed model names
    survive in the listed order;
  - swap the patched `urlopen` for one that raises a `URLError`, confirm
    `check_health` returns `False` and `check_models` returns `[]` so the
    degraded path is exercised inside the same lifecycle;
  - serialize the combined `{healthy, degraded}` diagnostic payload through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)` to prove the
    health-probe lifecycle output is JSON-safe.
- Preserve the existing focused assertions and production behavior unless the
  red test exposes a concrete gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path intentionally covers one healthy `/api/ps` payload and a
  single connection-error fallback, not every Ollama status code, alternate
  payload schema, or non-default timeout. Existing focused tests remain
  responsible for those branches.
- The healthy `/api/ps` payload includes a malformed entry without a `name`
  field to confirm the helper drops it without raising.
- The diagnostic payload must stay JSON-safe without custom encoders so
  downstream operator dashboards can persist it.
- Startup identity hardening remains covered by the existing CLI, first-boot,
  daemon-ordering, and narrative ASGI tests; this task does not change the
  identity startup wiring.

## Acceptance Criteria

1. Existing Ollama health helper assertions remain green.
   VERIFY: `pytest tests/test_ollama_health.py -q`

2. The depth gate confirms `tests/test_ollama_health.py` reaches depth >= 2
   and contains `OllamaHealthEndToEndTests`.
   VERIFY: `pytest tests/test_test_ollama_health_depth.py -q`

3. `OllamaHealthEndToEndTests` drives one meaningful Ollama health-probe
   lifecycle from healthy probe through degraded probe and JSON-safe
   diagnostics.
   VERIFY: `pytest tests/test_ollama_health.py::OllamaHealthEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0096 Ollama health test
   deepening.
   VERIFY: `grep -n "frac-0096" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
