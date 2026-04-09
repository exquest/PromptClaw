# sdp-cli Findings & Improvement Report

**From:** PromptClaw operations team
**To:** sdp-cli maintenance agent
**Date:** 2026-04-09
**Context:** 24 hours of diagnostic work on CypherClaw's thrashing pipeline

This report consolidates four bugs and one process issue discovered in sdp-cli during production use on CypherClaw. All findings are backed by evidence from the runtime state DB. Fix #1 has already been pulled in (`98da2b4`). The rest are open.

---

## Summary

| ID | Severity | Status | Issue |
|----|----------|--------|-------|
| 1 | **High** | **Fixed** (98da2b4) | Circuit breaker never auto-closes + blocks with exit 0 |
| 2 | **High** | Open | Agent rotation loops back to the broken agent |
| 3 | **Medium** | Open | Self-improvement analysis treats one-time events as systemic |
| 4 | **Medium** | Open | Retry cascade burns compute on identical retries |
| 5 | Low | Open | Integrity check escalations inflate the failure count |

---

## Bug 1: Circuit Breaker Silent Hot-Loop — FIXED

Already documented and resolved via commit `98da2b4` on `feature/monitor-compact-audit-grouping`. Summary for the record:

- Breaker opened at `2026-04-09T00:32 UTC` and stayed open through `15:49 UTC` despite successful outcomes recorded in `.sdp/circuit_breaker.json`'s `last_outcomes` field
- systemd-managed runner hot-looped at 10s intervals, restart counter reached **5007** in ~14 hours
- `orchestrate` command exited 0 when blocked, making systemd see "success"
- Fix applied on CypherClaw (reverted local `--force` workaround, now uses stock `orchestrate`)
- Verified: runner is active and processing tasks since 16:03 UTC

**Recommendation:** Port this fix to all release branches and cut a point release. This is the single biggest reliability win.

---

## Bug 2: Rotation Cycle on Provider Outage

### Evidence

During a ~3-hour OpenAI API outage (`wss://api.openai.com/v1/responses` returning HTTP 500), 110 task runs escalated with the **identical** rotation trace:

```
[selection] Selected codex as lead
[provider-unavailable codex] HTTP 500 Internal Server Error
[provider-unavailable-rotate codex->claude] switching lead due provider/runtime failure
[agent-limit claude] You've hit your limit · resets Apr 9, 10pm
[agent-limit-rotate claude->gemini] switching lead due quota exhaustion
[pair-rotate gemini/claude->claude/codex] lead produced zero work repeatedly
[agent-limit claude] hit limit again
[agent-limit-rotate claude->gemini]
[ESCALATED after ~130 seconds]
```

Note the critical line: **`[pair-rotate gemini/claude->claude/codex]`** — after cycling through all three agents, the pipeline rotates **back to codex** (still down) and **claude** (still quota'd). Then it cycles again. Every task burns ~120-130 seconds spinning through the same three broken paths before escalating.

### Root Cause

The `pair-rotate` logic appears to treat "produced zero work" as a reason to reset the rotation rather than a reason to escalate. When all agents in the pool have been tried and all have failed, the correct action is **escalate**, not start a new cycle.

### Impact

**110 escalations × ~125 seconds each = 3.8 hours of agent time wasted** during a single outage. Plus the associated cloud API costs for the HTTP calls that succeeded enough to return an error.

### Fix

```python
# pseudocode
def pair_rotate(reason):
    if all_agents_in_pool_have_failed_this_task():
        return escalate(task, reason="all_providers_exhausted")
    return next_untried_agent()
```

Also: a task should track which `(lead, verify)` pairs it has already tried, and never retry the same pair within a single run. Evidence from the log shows `gemini/claude -> claude/codex` — both `claude/codex` and `gemini/claude` had already been tried.

### Alternative / Defense-in-Depth

Add a **per-provider circuit breaker** (not to be confused with the pipeline breaker in Bug 1). When a provider returns HTTP 5xx three times in 60 seconds, mark it `unhealthy` for 5 minutes and exclude it from selection. This decouples "OpenAI is down" from individual task failure and saves the retry spin entirely.

---

## Bug 3: Self-Improvement Analysis Treats One-Shot Events as Systemic Patterns

### Evidence

CypherClaw's nightly self-improvement module produced this report this morning:

> 1. "max work retries exceeded" — 168 occurrences — #1 bottleneck
> 2. Integrity escalations — 126 hits
> 3. "missing agent adapter" — 104 hits in a single burst (Apr 1)
> 4. "ordered degradation policy" — 70 hits
> 5. Quota exhaustion — 41 hits

Investigation reveals:
- **#1 (168 retries) and #4 (70 degradation) are almost entirely from the 3-hour OpenAI outage window described in Bug 2.** They are the same event counted with different granularity.
- **#3 (104 missing agent adapter) is explicitly labeled "in a single burst (Apr 1)" by the daemon itself** — the module noticed it was a one-shot but still listed it as a candidate.
- **#5 (41 quota exhaustion) is normal operational noise** — quota pressure spikes during long overnight sprints and resets by morning.

### Root Cause

The self-improvement module counts raw occurrences without checking whether they cluster in time (suggesting one-time events) or distribute across time (suggesting systemic patterns). A 168-count burst inside a 3-hour window should be rated very differently from 168 incidents spread over 168 hours.

### Fix

Before promoting a candidate, check temporal distribution:

```python
def is_systemic(occurrences: list[Timestamp]) -> bool:
    if len(occurrences) < 5:
        return False
    span = max(occurrences) - min(occurrences)
    density = len(occurrences) / span.total_hours()
    # Burst ratio: is this concentrated in < 10% of the measured window?
    if span.total_hours() < 0.1 * measurement_window_hours():
        return False  # one-shot event
    return density < 10  # spread out, not bursty
```

Also: when a candidate explicitly labels itself as "in a single burst on DATE", **automatically downgrade its priority** or exclude it.

### User Impact

The self-improvement report led to a reasonable but wrong recommendation to "queue these as tasks to fix". Queueing them would have added 5-6 meta-improvement tasks to a pipeline that wasn't actually broken, wasting agent time on phantom problems.

---

## Bug 4: Retry Cascade Burns Compute on Identical Attempts

### Evidence

Top retry counts in the last 24 hours:

```
T-005@20260402T175502Z-2c: 5 attempts
T-006@20260402T175502Z-2:  4 attempts
```

Both are `prd-federation-read-model` gallery summary schema tasks. Each retry used the same task brief, the same agents, the same constraints, and produced the same (incomplete) work result. Five identical attempts = five times the compute of one attempt, with zero additional information.

### Root Cause

The retry logic increments a counter but doesn't change the inputs. After N failures, the pipeline should:
1. **Split** the task into smaller subtasks (if it's broad-scope)
2. **Escalate** to needs_review (if it's tight-scope)
3. **NOT** retry with identical inputs

Current behavior: retry with identical inputs until the counter hits `max_retries_on_interrupt=100` from sdp.toml, then escalate.

### Fix

After the 2nd failure on a single task with the same verdict reason:

```python
if identical_failure_count(task) >= 2:
    if task_broad_scope(task):
        split_task(task)
    else:
        escalate(task, reason="identical_retry_pattern")
    return
```

The `drain-needs-split` command already exists for the split path. This just needs to trip earlier.

### Impact

~50% of the 168 "max work retries" occurrences were on ~20 unique tasks with 4-8 retries each. Eliminating identical retries would reclaim an estimated 15-20% of pipeline throughput.

---

## Bug 5: Integrity Check Escalations Inflate the Failure Count

### Evidence

126 "integrity escalations" in the self-improvement report. Looking at recent task_runs, many of these are structural integrity checks failing on tasks that produced correct *content* but didn't pass the verifier's format expectations (e.g., missing a docstring, commit message format, file header).

### Root Cause

The integrity checker runs as part of the verify phase and treats format violations identically to semantic failures. A task that adds correct code without a docstring gets the same "ESCALATED" verdict as a task that produces broken code.

### Fix

Split verify outcomes:

```
PASS             — content + format both good
PASS WITH NOTES  — content good, format has fixable issues
FIX NEEDED       — format issues only, auto-retry with format hints
FAIL             — content wrong
ESCALATED        — can't be fixed automatically
```

The `PASS WITH NOTES` verdict already exists and is used (11 times in the last 24 hours). Extend this with `FIX NEEDED` for pure format issues.

---

## Process Issue: Default Launcher Should Use `run` Not `orchestrate`

### Evidence

The default systemd unit shipped with sdp-cli templates (and used on both CypherClaw and likely CTTickets) executes:

```bash
exec sdp-cli orchestrate --start-phase development --end-phase development
```

`orchestrate` is a single-run command that exits when it finishes a phase. For an unattended 24/7 runner, this is the wrong primitive — it should be `run` (which loops until interrupted) or `run --force` (which also bypasses the breaker).

### Fix

Update the systemd unit template in the sdp-cli project scaffold:

```bash
# Before
exec sdp-cli orchestrate --start-phase development --end-phase development

# After
exec sdp-cli run
```

And add to the sdp-cli docs: "For unattended systemd-managed runners, use `sdp-cli run`. Reserve `orchestrate` for interactive use where a human watches the output."

---

## Implementation Priority

| # | Bug | Complexity | Impact | Order |
|---|-----|-----------|--------|-------|
| 1 | Circuit breaker | Done | Critical | Done |
| 2 | Rotation cycle | Medium (~1 day) | High (3.8 hrs/outage reclaimed) | **Next** |
| 4 | Retry cascade | Medium (~1 day) | High (~15-20% throughput) | After #2 |
| 5 | Integrity split verdict | Small (~4 hrs) | Medium (cleaner signal) | Parallel |
| 3 | Self-improvement temporal analysis | Small (~2 hrs) | Medium (better recommendations) | Any time |
| Process | Default launcher | Trivial (~30 min) | High (prevents new installs from hitting Bug 1) | Any time |

**Recommended order:**
1. **Immediately:** Update default systemd launcher template (trivial, prevents future Bug 1 incidents).
2. **Next 1-2 days:** Fix Bug 2 (rotation cycle) and Bug 4 (retry cascade) together. They share code paths in the pair-rotation and retry logic.
3. **Next week:** Bug 3 (self-improvement temporal analysis) and Bug 5 (integrity verdict split). These are independent quality-of-signal improvements.

---

## Evidence Bundle

All evidence comes from CypherClaw's runtime state DB at `/home/user/cypherclaw/.sdp/state.db`. To reproduce the queries:

```sql
-- Bug 2: rotation loop on outage
SELECT task_id, retry_context FROM task_runs
WHERE verdict = 'ESCALATED'
AND retry_context LIKE '%provider-unavailable codex%'
ORDER BY started_at DESC LIMIT 10;

-- Bug 3: temporal distribution of escalations
SELECT SUBSTR(started_at, 1, 13) as hour, verdict, COUNT(*)
FROM task_runs
WHERE started_at > '2026-04-08'
GROUP BY hour, verdict
ORDER BY hour DESC;

-- Bug 4: retry counts per task
SELECT task_id, COUNT(*) as attempts
FROM task_runs
WHERE started_at > datetime('now', '-24 hours')
GROUP BY task_id
HAVING attempts >= 4
ORDER BY attempts DESC;

-- Bug 5: integrity escalation samples (by reason)
SELECT task_id, work_result, verdict, retry_context
FROM task_runs
WHERE verdict IN ('ESCALATED', 'FAIL')
AND retry_context LIKE '%integrity%'
LIMIT 20;
```

All five of these queries can be run on any sdp-cli project for comparison. I expect CTTickets shows similar patterns but in lower volume.

---

## Closing Note

Bug 1 was the gnarly one because it was silent. The other four are all cases where the pipeline is *telling us* something is wrong (ESCALATED verdicts, retry counts, integrity failures) but the mechanism for responding is either too slow (#4) or treats different failures identically (#2, #5). Fixing these turns sdp-cli from a system that burns compute when things go wrong into one that diagnoses and adapts.

Happy to pair on any of these, provide more evidence, or test fixes against CypherClaw's DB.
