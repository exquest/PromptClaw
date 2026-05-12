# Bug Report: Gemini Task Ran 7 Hours Past Timeout

## Summary

Task `T-008@20260402T175505Z` (T1, timeout=600s) ran for **6 hours 49 minutes** with Gemini as lead before being manually killed. The sdp-cli timeout enforcement did not terminate the stuck agent process.

## Evidence

```sql
-- The stuck run
SELECT started_at, completed_at, lead_agent, duration_seconds, verdict, work_result
FROM task_runs WHERE task_id = 'T-008@20260402T175505Z'
ORDER BY started_at DESC LIMIT 1;

-- Result:
-- started:    2026-04-11T23:52:25Z
-- completed:  2026-04-12T06:41:53Z  (6h 49m later — manual kill via systemctl restart)
-- lead:       gemini
-- duration:   0  (not recorded — probably because it was killed externally)
-- verdict:    (empty)
-- work_result: no_work
```

### Configured Timeouts

```toml
# sdp.toml
gemini_command = "gemini -p -m gemini-3.1-pro-preview --output-format stream-json --yolo"
timeouts = "{'T1': 600, 'T2': 1800, 'T3': 2700, 'default': 900, 'auto_tune': False}"
timeout_auto_tune = true
```

T1 timeout is 600 seconds (10 minutes). The task ran **41x longer** than the timeout.

### systemd Resource Usage

When the service was restarted after 7 hours:
```
Consumed 6h 17min 40.409s CPU time, 48.6G memory peak, 1.5G memory swap peak.
```

48.6 GB peak memory from a single Gemini task on a 62GB machine. This nearly exhausted system RAM.

### Monitor Output at Time of Discovery

```
Task:     T-008@20260402T175505Z (T1) Map typing input into gallery response stat… [running]
Timing:   task 6h 48m 43s / est 19m 46s
```

The monitor correctly showed the task had been running for 6h 48m against an estimate of 19m. However, the runner did not enforce the timeout.

## Root Cause Hypothesis

The `gemini` CLI with `--yolo` flag and `--output-format stream-json` may behave differently from claude/codex in how it handles process termination:

1. **`--output-format stream-json`**: Gemini streams JSON events rather than returning a single response. The sdp-cli timeout may be waiting for the stream to end rather than enforcing a wall-clock kill.

2. **`--yolo` flag**: Auto-approves all tool calls. If Gemini entered a tool-call loop (e.g., repeatedly running tests that fail, or exploring the filesystem), each tool call might reset the "activity" timer even though the overall task is stuck.

3. **Memory behavior**: 48.6 GB peak suggests Gemini was loading/indexing large amounts of data (perhaps the full gallery directory, the 10TB archive mount, or recursive file discovery). The `gemini_all_files = true` setting we added may have caused it to index more than expected.

## Impact

- **7 hours of lost pipeline time** — the runner was stuck on one task while 6 others waited
- **48.6 GB memory consumed** — risked OOM-killing other CypherClaw services
- **No automatic recovery** — the circuit breaker didn't trip, the timeout didn't fire, the task wasn't escalated. It took a human noticing the monitor to discover and fix it.

## Questions for Investigation

1. **Does the stream-json output format bypass the wall-clock timeout?** The timeout enforcement might be waiting for EOF on stdout rather than enforcing `SIGTERM` after N seconds.

2. **Does `--yolo` tool-call activity reset the timeout timer?** If so, a Gemini session that's actively calling tools (but making no progress) would never time out.

3. **Is the timeout enforcement even watching the Gemini subprocess?** The Gemini CLI spawns a child process — is the timeout applied to the parent `gemini` process or the actual model inference?

4. **Should `gemini_all_files = true` be scoped?** With a 10TB archive mount, Gemini might be trying to index everything, consuming memory and time on file discovery before even starting the task.

## Recommended Fixes

### Fix 1: Hard wall-clock kill (highest priority)

Regardless of stream activity or tool calls, kill the agent subprocess after `timeout * 1.5` wall-clock seconds. No exceptions.

```python
# pseudocode
import signal
def enforce_wall_clock(process, timeout_seconds):
    """Kill the process after timeout regardless of activity."""
    def _kill(signum, frame):
        process.terminate()
        time.sleep(5)
        process.kill()
    signal.alarm(int(timeout_seconds * 1.5))
    signal.signal(signal.SIGALRM, _kill)
```

This is defense-in-depth against any agent that doesn't respect the normal timeout.

### Fix 2: Memory limit per agent

Add a memory ceiling so a stuck agent can't consume 48GB:

```ini
# In the systemd unit or in sdp-cli's subprocess invocation
MemoryMax=8G  # per agent subprocess
```

### Fix 3: Scope gemini_all_files

Exclude large directories from Gemini's file indexing:

```toml
gemini_all_files = true
gemini_exclude_dirs = "/mnt/archive,/home/user/cypherclaw-data/gallery"
```

Or set the working directory to the tmpfs workdir (which is already scoped) rather than the full project root.

### Fix 4: Monitor-based escalation

The sdp-cli monitor correctly showed the task at 6h 48m. If the monitor can detect `task_duration > timeout * 3`, it should auto-escalate rather than requiring a human to notice.

## Environment

- CypherClaw (Dell OptiPlex 7090, 62GB RAM, Ubuntu 24.04)
- sdp-cli on branch `feature/monitor-compact-audit-grouping` (commit 73ebb2c42)
- Gemini CLI 0.35.1 with `--yolo --output-format stream-json`
- Task: T-008@20260402T175505Z "Map typing input into gallery response state" (T1)
- Pipeline: cypherclaw-sdp-runner.service (bash loop launcher)

## Evidence Files

```sql
-- Reproduce the query
SELECT * FROM task_runs
WHERE task_id = 'T-008@20260402T175505Z'
ORDER BY started_at DESC LIMIT 5;

-- Find other long-running tasks
SELECT task_id, lead_agent, CAST(duration_seconds AS INTEGER), verdict
FROM task_runs WHERE duration_seconds > 3600
ORDER BY duration_seconds DESC;
```
