# Task frac-0098 Specification: test_ollama_run_agent Depth 2

## Problem Statement

`tests/test_ollama_run_agent.py` covers `cypherclaw_daemon.run_agent` and the
LOCAL_ONLY routing surface at focused level: the Ollama HTTP path bypasses the
subprocess invoker, observatory bookkeeping records semaphore acquire/release
plus task results, the pet manager receives start/end/idle calls,
`_available_agents` and `_best_available_agent` snap to `ollama` under
`LOCAL_ONLY`, `route_message` rewrites cloud agents to `ollama`, `execute_plan`
coerces explicit cloud steps to `ollama`, and the cloud subprocess path is
preserved when `LOCAL_ONLY` is disabled.

The missing frac-0098 work is to make the depth-2 contract explicit for this
test module. The production runtime in `my-claw/tools/cypherclaw_daemon.py`
already exposes the simple one-path lifecycle (`run_agent` -> `_invoke_ollama`
-> observatory + pet manager bookkeeping -> JSON-safe operator output). This
task deepens the test surface with a deterministic depth gate plus one
end-to-end class that drives the existing `run_agent` lifecycle through the
ollama HTTP path, observatory + pet manager bookkeeping, and JSON-safe
diagnostic serialization.

The generated startup identity hardening bullets target the existing identity
startup subsystem. This checkout already wires `bootstrap_identity()` into both
daemon poll loops before `FirstBootAnnouncer`, and the CLI/narrative ASGI paths
plus standalone/federated identity persistence are covered by regression tests.
This task keeps those tests as mandatory hardening anchors rather than changing
unrelated startup code without a discovered gap.

## Technical Approach

- Add `tests/test_test_ollama_run_agent_depth.py` with a deterministic depth
  gate requiring `tests/test_ollama_run_agent.py` to contain
  `OllamaRunAgentEndToEndTests` and classify at depth >= 2 through the
  repo-local `sdp.fractal.classify_depth`.
- Confirm the red phase by running the new depth gate before
  `OllamaRunAgentEndToEndTests` exists.
- Append `OllamaRunAgentEndToEndTests` to `tests/test_ollama_run_agent.py`
  without modifying existing locked assertions.
- Drive one meaningful `run_agent` lifecycle inside the class:
  - stub the daemon's observatory, pet manager, semaphore, spinner, telegram
    sender, healer, and `time.time`;
  - call `cypherclaw_daemon.run_agent("ollama", prompt, timeout=..., task_label=...)`
    once with the HTTP path stubbed to a deterministic response;
  - assert `_invoke_ollama` received the prompt, timeout, task category, and
    task label exactly once, that the cloud subprocess invoker was never
    called, and that the returned output is the stubbed Ollama response;
  - assert pet manager receives `start`, `end` (with `success=True` and a
    finite duration), and `idle` for the `ollama` agent;
  - assert observatory records exactly one task result with the agent,
    task id, success flag, integer duration, zero tokens, and `gate_pass=True`;
  - assert observatory events are exactly the `semaphore_acquired` /
    `semaphore_released` pair, with no healing events emitted on the happy
    path;
  - serialize a combined diagnostic payload through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)` so run_agent
    output is safe for operator status surfaces.
- Preserve existing production behavior unless the red tests expose a concrete
  gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path intentionally covers one happy `run_agent("ollama", ...)`
  lifecycle. Existing focused tests continue to own LOCAL_ONLY coercion, route
  message rewriting, execute_plan coercion, the cloud path, and the
  `_available_agents` / `_best_available_agent` selectors.
- Cloud subprocess invocation is monkeypatched to fail loudly so the
  end-to-end ollama path can never silently regress to a subprocess.
- Observatory and pet manager interactions must remain order-preserving:
  semaphore_acquired precedes semaphore_released, task start precedes task
  end precedes task idle, and exactly one task result is recorded.
- Startup identity hardening remains covered by the existing CLI, first-boot,
  daemon-ordering, and narrative ASGI tests; this task does not change identity
  startup wiring.

## Acceptance Criteria

1. Existing run_agent regression assertions remain green.
   VERIFY: `pytest tests/test_ollama_run_agent.py -q`

2. The depth gate confirms `tests/test_ollama_run_agent.py` reaches depth >= 2
   and contains `OllamaRunAgentEndToEndTests`.
   VERIFY: `pytest tests/test_test_ollama_run_agent_depth.py -q`

3. `OllamaRunAgentEndToEndTests` drives one meaningful `run_agent` lifecycle
   through the ollama HTTP path, observatory + pet manager bookkeeping, and
   JSON-safe diagnostics.
   VERIFY: `pytest tests/test_ollama_run_agent.py::OllamaRunAgentEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0098 run_agent test deepening.
   VERIFY: `grep -n "frac-0098" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
