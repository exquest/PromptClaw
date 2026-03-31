# Codex Verification Prompt: Graceful LLM Provider Degradation — IMPLEMENTED

## Status: COMPLETE — Verify, Commit, and Push

All code is written and all 27 tests pass. This prompt is for final verification and deployment.

## What Was Implemented

A full graceful-degradation system so PromptClaw and the CypherClaw daemon continue operating when any LLM provider's token budget runs low. The system detects quota exhaustion via sdp-cli's existing infrastructure, smoothly ramps down usage of degraded providers, redistributes tasks to healthy providers, and alerts the user via Telegram.

### Files Changed/Created

| File | Action | Status |
|------|--------|--------|
| `my-claw/tools/quota_monitor.py` | **CREATED** | 323 lines — QuotaMonitor class with polling, degradation cascade, alerts |
| `my-claw/tools/agent_selector.py` | **MODIFIED** | Added `quota_monitor` param, `disabled_agents`, headroom bonus, `_resolve_agents()` |
| `my-claw/tools/cypherclaw_daemon.py` | **MODIFIED** | Wired QuotaMonitor, `/quota` command, runtime failure detection, agent fallback |
| `my-claw/tools/sdp_runtime.py` | **MODIFIED** | Added `get_provider_headroom()` helper |
| `my-claw/tools/sdp_bridge.py` | **MODIFIED** | Quota-aware agent filtering in `run_next()` |
| `tests/test_quota_monitor.py` | **CREATED** | 16 tests — thresholds, alerts, fallback, observatory, polling |
| `tests/test_agent_selector_quota.py` | **CREATED** | 6 tests — exclusion, headroom bonus, disabled agents, status summary |
| `tests/test_daemon_fallback.py` | **CREATED** | 5 tests — retry on quota error, routing fallback, /quota command |

### Key Design Decisions

- **Degradation cascade**: healthy (>30%) → warn (15-30%) → degraded (5-15%) → paused (<5%)
- **Never fully dead**: If all providers are paused, the one with highest headroom is used
- **Runtime failure detection**: Parses stderr for quota error patterns (rate limit, 429, billing, etc.)
- **Automatic retry**: On quota error, marks provider as paused and retries with next available agent
- **Thread-safe**: `threading.Lock` protects all shared state in QuotaMonitor
- **sdp-cli Python API preferred**: Imports `sdp.state.db.get_quota_headroom` directly, falls back to CLI parsing
- **Observatory integration**: All degradation events recorded as healing events

## Verification Steps for Codex

```bash
# 1. Ensure on the correct branch
git checkout feat/graceful-degradation

# 2. Run the new tests
pytest tests/test_quota_monitor.py tests/test_agent_selector_quota.py tests/test_daemon_fallback.py -v

# 3. Run the full test suite — no regressions
pytest tests/ -v

# 4. If all pass, commit any uncommitted changes and push
git add my-claw/tools/quota_monitor.py my-claw/tools/agent_selector.py my-claw/tools/cypherclaw_daemon.py my-claw/tools/sdp_runtime.py my-claw/tools/sdp_bridge.py tests/test_quota_monitor.py tests/test_agent_selector_quota.py tests/test_daemon_fallback.py
git status
# Only commit if there are staged changes not yet committed
git diff --cached --stat
```

## Current Live Deployment State (as of 2026-03-31)

### Emergency measures in place on CypherClaw server:

1. **sdp-cli pipeline** (`/run/cypherclaw-tmp/workdir/cypherclaw-work/sdp.toml`):
   - `selector_claude_remaining_tokens = 0.0` / `selector_claude_token_limit = 1.0`
   - Forces selector to see Claude at 0% headroom → excluded from pipeline tasks
   - Pipeline running on Codex + Gemini only

2. **Daemon** (`/home/user/cypherclaw/tools/cypherclaw_daemon.py`):
   - Claude removed from all `available_agents` lists
   - Routing prompt updated: "Do NOT use claude — it is temporarily disabled"
   - Guard in execute_plan: if router outputs `"agent": "claude"`, redirected to codex

3. **Scheduled revert** (cron job on server):
   - `0 18 4 4 * /run/cypherclaw-tmp/revert_claude.sh`
   - April 4th at 11:00 AM PDT (18:00 UTC)
   - Reverts sdp.toml, reverts daemon, restarts daemon, sends Telegram notification

### Current provider quotas (as of 2026-03-31 13:00 PDT):
- **Anthropic**: 5h: 87% remaining, 7d: 14% remaining (TIGHT — resets Apr 4), sonnet: 89%
- **OpenAI**: short: 92%, long: 85%
- **Google**: daily: ~48% (725/1500 requests)

## Architecture Reference

### QuotaMonitor (`my-claw/tools/quota_monitor.py`)
- `poll_once()` — collect headroom snapshot for all providers
- `get_available_agents(agents)` — filter to healthy/warn agents
- `get_provider_status()` — full status dict
- `get_agent_headroom(agent)` — headroom for specific agent
- `force_status(provider, status)` — runtime override after live failure
- `is_quota_error(text)` — detect quota errors in stderr

### AgentSelector changes (`my-claw/tools/agent_selector.py`)
- `__init__(observatory, quota_monitor, state_file)` — accepts QuotaMonitor
- `_resolve_agents(available, disabled)` — filters by quota + disabled set
- `_headroom_bonus(agent)` — 0.0-0.15 score bonus scaled by headroom
- `select(task_desc, available_agents, disabled_agents)` — quota-aware selection
- `select_pair(task_desc, available_agents, disabled_agents)` — lead+verify with single-agent fallback

### Daemon integration (`my-claw/tools/cypherclaw_daemon.py`)
- `AgentCommandResult` dataclass for structured agent output
- `_invoke_agent_process()` — extracted subprocess call
- `_invoke_router_agent()` — extracted router subprocess call
- `run_agent()` — detects quota errors, retries with different agent
- `route_message()` — iterates available agents for routing
- `handle_builtin("/quota")` — Telegram status command
- Signal handlers call `quota_monitor.stop()`

### Error patterns detected:
```
rate_limit, quota_exceeded, insufficient_credits, billing,
token_limit_exceeded, 429, resource_exhausted, capacity, overloaded
```
