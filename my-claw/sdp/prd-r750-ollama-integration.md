# PRD: R750 Ollama Agent Integration

## Overview

The Dell PowerEdge R750 (2x Xeon Silver 4310, 813GB RAM, no GPU) will run PromptClaw with Ollama as a first-class local agent alongside claude/codex/gemini. This PRD covers the code changes needed to integrate Ollama into the existing daemon architecture. No architectural rewrites — extend what exists.

**Depends on:** R750 bare metal setup (runbook), model evaluation (separate plan)

**Key files:** `my-claw/tools/agent_selector.py`, `my-claw/tools/cypherclaw_daemon.py`, `my-claw/tools/quota_monitor.py`

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| R750-001 | Add `ollama` to the `PROVIDERS` map in `agent_selector.py` with provider type `"local"` and seed fitness scores for 9 task categories. | MUST | T1 | - `PROVIDERS["ollama"]` returns `"local"`<br/>- Default fitness scores exist for all 9 categories<br/>- `netops` category seeded highest (0.80) reflecting LG SoT use case |
| R750-002 | Add dual-socket model-per-role routing configuration mapping task categories to specific Ollama models and NUMA-pinned ports (11434 for socket 0, 11435 for socket 1). | MUST | T1 | - Configuration maps coding, review, netops, orchestrator, and default roles to model names and ports<br/>- Model names are configurable without code changes (env var or config file)<br/>- Tests verify routing returns correct model+port for each category |
| R750-003 | Implement `_invoke_ollama()` in `cypherclaw_daemon.py` that calls the Ollama HTTP API directly (no subprocess), selecting model and port from the routing config based on task category. | MUST | T1 | - HTTP POST to `/api/generate` with correct model, prompt, and options<br/>- Timeout configurable per call (default 120s)<br/>- Returns response text on success, bracketed error string on failure |
| R750-004 | Add the Ollama branch to `run_agent()` so that when `agent == "ollama"`, it calls `_invoke_ollama()` instead of spawning a subprocess, while preserving observatory logging and pet updates. | MUST | T1 | - `run_agent("ollama", ...)` uses HTTP path, not subprocess<br/>- Observatory records the result (agent, duration, success, tokens)<br/>- Pet state updates as with other agents |
| R750-005 | Add local infinite-quota short-circuit to `quota_monitor.py` so provider `"local"` always returns 1.0 headroom and is never rate-limited. | MUST | T1 | - `get_agent_headroom("ollama")` returns 1.0<br/>- Ollama is never excluded from selection due to quota<br/>- Tests verify infinite headroom for local provider |
| R750-006 | Implement `ollama_health.py` with `check_health(port)` that verifies Ollama is responding on a given port, and `check_models(port)` that returns loaded model names. | MUST | T1 | - Health check returns True/False within 5s timeout<br/>- Model list returns list of loaded model names<br/>- Graceful return on connection refused or timeout |
| R750-007 | Add Ollama health status to the daemon's `/status` and Telegram `/local` command output showing both socket instances, loaded models, and response latency. | SHOULD | T2 | - Status output shows health for port 11434 and 11435<br/>- Loaded models listed per port<br/>- Response latency measured on health check |
| R750-008 | Implement fallback behavior: when Ollama is unhealthy, the agent selector automatically excludes it and falls back to cloud agents based on existing fitness scores. | MUST | T1 | - Unhealthy Ollama is excluded from candidate list<br/>- Cloud agents selected by existing fitness logic<br/>- Recovery: when Ollama returns healthy, it re-enters the candidate pool |
| R750-009 | Add `LOCAL_ONLY` environment variable support that restricts the daemon to only use the `ollama` agent, disabling all cloud API calls. | SHOULD | T2 | - When `LOCAL_ONLY=true`, only `ollama` is in the available agents list<br/>- Cloud agents are not invoked regardless of fitness scores<br/>- Unset or false allows normal multi-agent selection |
| R750-010 | Add instance identity bootstrap for the R750 home: generate `instance_id`, auto-generate artistic `instance_name`, record creation metadata. | MUST | T1 | - First boot generates a unique UUID instance_id<br/>- Artistic name generated from word lists<br/>- Identity record persists to `~/.promptclaw/identity.json`<br/>- Subsequent boots load existing identity without regenerating |
| R750-011 | Implement federation peer discovery via Tailscale: detect other PromptClaw instances on the tailnet by scanning for the identity endpoint. | SHOULD | T2 | - Discovers CypherClaw and other peers on the Tailscale network<br/>- Reads their public identity summary<br/>- Stores peer registry in `~/.promptclaw/federation/peers.json` |
| R750-012 | Add comprehensive tests for Ollama agent integration covering: agent selection with Ollama available, model routing, health check, quota bypass, fallback on unhealthy, and LOCAL_ONLY mode. | MUST | T1 | - Tests cover happy path (Ollama selected and invoked)<br/>- Tests cover fallback (Ollama down, cloud agent used)<br/>- Tests cover LOCAL_ONLY restriction<br/>- All tests pass with mocked HTTP responses |

## Dependency Map

```
R750-001 → R750-002 → R750-003 → R750-004
R750-005 (independent)
R750-006 → R750-007, R750-008
R750-010 → R750-011
R750-012 (depends on R750-001 through R750-008)
```

## Notes

- Model names in R750-002 are placeholders until the model evaluation plan completes. The architecture supports swapping models by changing config only.
- The R750 has no GPU. All inference is CPU-only across dual NUMA sockets. Response times will be 10-60s depending on model size and prompt length.
- The existing `agent_selector.py` EMA skill tracking will automatically tune Ollama fitness scores after deployment based on actual performance.
- `httpx` is the recommended HTTP client (already used by art_engine.py on CypherClaw). Fall back to `urllib` if httpx is not available.
