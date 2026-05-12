# PRD: Agent Runtime Substrate — Persistent Sessions, Streaming Output, Unified Execution

## Overview

CypherClaw currently executes agents through a mix of direct subprocess calls, ad hoc shell invocations, and daemon-specific wrappers. That works, but it creates avoidable fragility:

- every task starts cold
- stdout/stderr handling differs by caller
- interrupts and retries are inconsistent
- verification, research, daemon chat, and web streaming all need similar plumbing
- process failures are often hard to classify as provider failure vs infrastructure failure

This PRD creates a shared runtime substrate for all agent execution. The goal is one execution layer with durable session semantics, consistent streaming, clear interrupts, and observable process health.

This is not a UI PRD. It is the execution machinery that makes the rest of the organism feel continuous rather than stateless.

**Depends on:** `prd-home-resilience.md` (runner/process authority), `prd-restructure.md` (stable package layout), `prd-model-awareness.md` (provider/model-aware command construction)

## Execution Role

This is **Stage 4** of the execution spine.

It should land before broad verification and introspection work, because those systems need a shared execution model instead of each inventing their own subprocess wrapper.

It directly supports:

- `prd-verification-system.md`
- `prd-context-engine.md`
- `prd-introspector.md`
- `prd-web-platform.md`

## Design Principles

1. **One runtime API**  
   Daemon chat, verification, research, and pipeline helpers should all execute agents through the same layer.

2. **Sessions, not one-off shells**  
   Repeated work in the same workspace should be able to reuse a live shell/session when appropriate.

3. **Streaming is first-class**  
   Stdout/stderr chunks, lifecycle events, and timing must be observable while the process runs, not only after it exits.

4. **Interrupts must be explicit**  
   Timeout, operator cancel, and quota/provider failure are distinct outcomes and should be recorded separately.

5. **Fail classification matters**  
   A verifier crash, CLI auth failure, quota exhaustion, and bad code output are not the same class of failure.

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| RTS-001 | Create `cypherclaw.runtime.session_manager` as the shared execution entrypoint. It owns shell/session lifecycle, queueing, environment assembly, cwd tracking, and per-run session IDs. | MUST | T1 | - One importable runtime module exists<br/>- Session IDs are stable within a run<br/>- cwd is tracked correctly across commands<br/>- Module is used by daemon and helper tools |
| RTS-002 | Implement a persistent shell/session abstraction for shell-backed work. It must support serial command queueing, current-directory tracking, timeouts, graceful interruption, and restart when the shell dies. | MUST | T2 | - Commands can execute in the same live shell<br/>- `cd` persists within session scope<br/>- Timeout and cancel terminate child processes cleanly<br/>- Dead shell auto-restarts without corrupting caller state |
| RTS-003 | Implement a unified `run_agent()` interface that returns structured lifecycle data: `started_at`, `completed_at`, `stdout`, `stderr`, `exit_code`, `timed_out`, `interrupted`, `provider_failure`, `quota_failure`, `session_id`. | MUST | T1 | - All runtime callers receive the same result shape<br/>- Provider/quota failure flags are set correctly<br/>- Exit classification is consistent across providers |
| RTS-004 | Add real-time streaming callbacks/events for agent output. The runtime must emit `agent_started`, `agent_output`, `agent_error`, `agent_finished`, and `agent_interrupted` events with timestamps and task labels. | MUST | T2 | - Streaming callbacks fire during execution<br/>- Both stdout and stderr are surfaced<br/>- Multiple consumers can subscribe without double-running the command |
| RTS-005 | Add provider-specific command builders under the shared runtime. Command construction for Claude, Codex, Gemini, and local models must be centralized so timeout, model flags, TMPDIR, ionice/nice, and auth-env behavior are not duplicated. | MUST | T1 | - Provider commands are built in one place<br/>- Daemon no longer hardcodes model/provider flags inline<br/>- Runtime honors model-awareness configuration |
| RTS-006 | Add explicit interruption semantics. Operator cancel, timeout, maintenance-mode drain, and queue shutdown should each map to a distinct runtime reason code. | MUST | T2 | - Callers can distinguish timeout from operator cancel<br/>- Maintenance drain uses graceful stop first<br/>- Interrupt reason is logged to Observatory |
| RTS-007 | Add crash/failure classification. Detect and tag: CLI auth failure, quota exhaustion, transport error, missing executable, shell bootstrap failure, syntax/runtime failure in produced code. | MUST | T1 | - Failure class is attached to every non-success result<br/>- Verifier infrastructure failures can be separated from logical verification failures |
| RTS-008 | Integrate runtime events with Observatory. Record per-run provider, model, session ID, duration, bytes streamed, interruption reason, and failure class. | SHOULD | T1 | - Runtime events queryable in Observatory<br/>- Slow/failing sessions visible on dashboard and diagnostics |
| RTS-009 | Add tests with fake processes/shells. Cover: session reuse, cwd persistence, timeout, cancellation, dead-shell recovery, stream ordering, and failure classification. | MUST | T1 | - Tests exist before/with implementation<br/>- All core runtime behaviors are covered<br/>- No live provider dependency in tests |
| RTS-010 | Refactor current daemon/runtime call sites to use the substrate. At minimum: daemon `run_agent()`, researcher shell/agent execution, verification engine, and any future web-stream execution path. | MUST | T2 | - Main execution paths use the shared runtime<br/>- Duplicate subprocess wrappers are removed or deprecated |

## Implementation Phases

### Phase 1: Runtime Core
RTS-001, RTS-003, RTS-005, RTS-007

Create the unified execution interface and centralize provider command construction and failure classification.

### Phase 2: Persistent Sessions
RTS-002, RTS-006

Add shell/session persistence, cwd tracking, and explicit interruption semantics.

### Phase 3: Streaming + Observability
RTS-004, RTS-008

Emit live runtime events and capture them in Observatory.

### Phase 4: Adoption
RTS-009, RTS-010

Test the runtime thoroughly and migrate the main callers onto it.

## Success Metrics

| Metric | Target |
|--------|--------|
| Duplicate subprocess wrappers removed | >80% |
| Runtime failure classification accuracy | >95% on known cases |
| Stream delivery delay | <500ms |
| Shell/session restart success after crash | 100% in tests |
| Caller migration coverage | daemon + verification + research paths |

## Definition of Done

This PRD is done when:

1. CypherClaw has one shared runtime API for agent execution.
2. Long-lived shell/session execution works and is tested.
3. Streaming output is available as structured runtime events.
4. Provider/auth/quota/infrastructure failures are distinguishable.
5. The daemon and other core callers no longer rely on bespoke subprocess wrappers.
