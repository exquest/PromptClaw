# PRD: Context Engine — Compaction, Session Briefs, and Operational Memory

## Overview

CypherClaw currently carries context through a shallow rolling conversation buffer, scattered status helpers, and whatever the active agent can infer from the workspace. That is not enough for a long-running artistic system that must remember what changed, what failed, what is in progress, and what still matters after a restart or a handoff.

This PRD creates an operational context engine.

The context engine is not long-term semantic memory or RAG. That larger historical memory belongs in the proactive/memory systems. The context engine is the short-to-medium horizon layer that keeps active work coherent:

- startup context snapshots
- compacted conversation state
- run handoff briefs
- active queue and provider state summaries
- durable "what changed / what failed / what is next" records

**Depends on:** `prd-home-resilience.md` (durable state), `prd-restructure.md` (stable package layout), `prd-agent-runtime-substrate.md` (shared runtime events), `prd-verification-system.md` (verified summaries and recovery actions)

## Execution Role

This is **Stage 7** of the execution spine.

It follows the runtime and verification layers because it should summarize stable execution events, not raw improvisation. Once in place, it becomes a multiplier for daemon continuity, web UX, and future proactive memory.

## Design Principles

1. **Summaries over transcripts**  
   Active operational memory should keep decisions, files touched, failures, and next steps, not just a raw wall of messages.

2. **Context is generated at known boundaries**  
   Session start, run completion, verification failure, and compaction are natural moments to write durable context.

3. **Snapshots are cached, not recomputed constantly**  
   Build rich context at run/session start, then refresh selectively.

4. **Handoffs are first-class artifacts**  
   Every meaningful run should leave behind a brief that another agent or session can pick up.

5. **Operational memory is not RAG**  
   This layer should be deterministic, legible, and directly tied to active execution state.

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CX-001 | Create a context snapshot builder for run/session start. The snapshot should include: git status, active branch, current PRD/task, AGENTS/CLAUDE instructions, project README summary, queue state, provider/quota state, and recent verified changes. | MUST | T1 | - Snapshot artifact is generated at run/session start<br/>- Snapshot covers repo, queue, and provider state<br/>- Output is readable by both humans and agents |
| CX-002 | Create a run handoff brief writer under `.promptclaw/runs/<run-id>/`. Each brief should summarize: objective, actions taken, files touched, verification status, failures/retries, and the next best step. | MUST | T1 | - Every completed or blocked run has a handoff brief<br/>- Brief includes next-step guidance<br/>- Brief path is stable and referenced in run state |
| CX-003 | Implement conversation compaction. Old conversation should be summarized into durable structured context instead of simply being dropped from a rolling deque. Preserve: decisions made, open questions, pending tasks, and assumptions. | MUST | T2 | - Compaction reduces raw prompt size<br/>- Key decisions and next steps survive compaction<br/>- No essential run state is lost when old messages age out |
| CX-004 | Add a daemon-visible context cache with invalidation rules. Refresh when: a run completes, queue status materially changes, provider availability changes, or a compaction event occurs. | MUST | T2 | - Context cache refreshes on important state changes<br/>- Cache avoids recomputing large context on every message |
| CX-005 | Create a session brief artifact for new sessions/operators. Write `session_brief.md` or equivalent from current operational state so a new agent session can orient quickly without replaying everything manually. | MUST | T2 | - New sessions get a current brief<br/>- Brief is updated while active work continues |
| CX-006 | Add `/compact` and `/context` style operator commands to the daemon or CLI surface. `/compact` should summarize and trim active conversation state. `/context` should show the current operational brief. | SHOULD | T2 | - Compaction can be triggered explicitly<br/>- Current brief can be inspected on demand |
| CX-007 | Record context artifacts and compaction events in Observatory. Track snapshot generation time, compaction frequency, and brief freshness. | SHOULD | T1 | - Context generation and compaction are visible in Observatory |
| CX-008 | Add tests for snapshot generation, compaction behavior, brief writing, and cache invalidation. | MUST | T1 | - Tests cover active-state summarization and compaction semantics<br/>- Brief artifacts are validated without live provider calls |

## Implementation Phases

### Phase 1: Snapshot + Handoff Core
CX-001, CX-002

Generate useful operational context at run/session boundaries.

### Phase 2: Compaction + Cache
CX-003, CX-004, CX-005

Preserve active meaning while reducing raw conversational load.

### Phase 3: Operator Surface + Observability
CX-006, CX-007, CX-008

Expose the context system to operators and cover it with tests.

## Success Metrics

| Metric | Target |
|--------|--------|
| New-session orientation time | <2 minutes |
| Prompt context size after compaction | Reduced by >50% without loss of next-step clarity |
| Completed/blocked runs with handoff briefs | 100% |
| Stale session brief age during active work | <30 minutes |

## Definition of Done

This PRD is done when:

1. A new session can pick up active work from a generated brief instead of reconstructing it from logs.
2. Conversation state can be compacted without losing decisions and next steps.
3. Run handoffs are durable artifacts, not just implied memory.
4. Queue/provider/recent-change state is available as structured operational context.
