# PRD: Capability and Approval Framework — Explicit Tool Governance

## Overview

CypherClaw already behaves as if some actions are low-risk and some require caution, but the boundaries are still scattered across prompts, heuristics, and human convention. That is workable for a prototype, but not for a long-running artistic home that modifies code, restarts services, and operates unattended.

This PRD makes those boundaries explicit.

The framework defines what kinds of actions exist, which tools/commands belong to which class, when approval is required, how grants are recorded, and how those decisions are surfaced to verification, daemon routing, and future web controls.

The purpose is not to make the system timid. The purpose is to make autonomy legible and safe.

**Depends on:** `prd-home-resilience.md` (stable operational state), `prd-restructure.md` (clean module boundaries), `prd-model-awareness.md` (provider-aware action routing), `prd-agent-runtime-substrate.md` (shared execution hooks)

## Execution Role

This is **Stage 5** of the execution spine.

It should land before broad verification and before the introspector begins applying autonomous repairs. Verification needs stable action classes and bypass rules. The introspector needs a trustworthy approval ceiling for destructive operations.

## Design Principles

1. **Capabilities are explicit**  
   Read, write, exec, network, deploy, db, service-control, and destructive actions must be modeled directly.

2. **Command families matter**  
   `git status` and `git push` are not the same thing just because both are shell commands.

3. **Approval is stateful**  
   A grant may be per-command, per-prefix, per-session, per-project, or never allowed.

4. **Bypass rules must be narrow**  
   Emergency actions can bypass verification, but only from a small, named whitelist.

5. **Every grant leaves an audit trail**  
   If the system is allowed to act, that decision should be visible later.

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CAF-001 | Create a capability registry module that classifies actions and tools into explicit classes: `read`, `write`, `exec`, `network`, `deploy`, `db`, `service_control`, `destructive`. | MUST | T1 | - Registry exists and is importable<br/>- Core tool and action types are mapped to capability classes<br/>- New actions can be added without editing prompts |
| CAF-002 | Create command-prefix policy evaluation for shell commands. Support exact command grants and prefix grants such as `git status`, `pytest`, `systemctl restart`, and `sqlite3`. | MUST | T2 | - Prefix and exact grants both supported<br/>- Dangerous subcommands do not inherit from harmless prefixes by accident<br/>- Policy evaluator is test-covered |
| CAF-003 | Add project/session/run-scoped grant storage. Grants should be recordable per session, per run, or persistently for the project, with clear expiration semantics. | MUST | T2 | - Grant scope is explicit<br/>- Session-scoped approvals expire automatically<br/>- Persistent grants survive restart when intended |
| CAF-004 | Integrate capability evaluation with the risk classifier and verification engine. Risk level and capability class should jointly determine whether an action runs immediately, requires verification, or requires Anthony approval. | MUST | T1 | - Risk classifier consumes capability class<br/>- High/critical capability classes route into verification/approval correctly |
| CAF-005 | Create a narrow emergency-bypass whitelist for time-sensitive actions such as distress shutdowns, I/O protection, or lock cleanup. Bypassed actions must still be logged. | MUST | T1 | - Bypass list is explicit and configurable<br/>- Bypassed actions execute without human wait<br/>- Every bypassed action is logged with reason |
| CAF-006 | Add Anthony approval workflow primitives for destructive actions. Approval requests should be serializable for Telegram and future web UI use, with approve/reject outcomes recorded. | SHOULD | T2 | - Approval payload is structured and reusable<br/>- Approve/reject state is stored and queryable |
| CAF-007 | Integrate the framework into `doctor/preflight`. Configuration errors such as missing policy, ambiguous grants, or dangerous blanket permissions should be reported before the runner starts. | SHOULD | T1 | - Preflight flags invalid or over-broad policies<br/>- Human-readable remediation guidance exists |
| CAF-008 | Record capability grants and denials in Observatory. Track which action classes are most common, which approvals are pending, and which commands are frequently blocked. | SHOULD | T1 | - Observatory receives grant/deny events<br/>- Pending approvals and blocked actions are queryable |
| CAF-009 | Add tests for policy evaluation, scope expiry, bypass rules, and destructive-action gating. | MUST | T1 | - Tests exist for exact/prefix grants<br/>- Tests cover safe vs unsafe command families<br/>- Expiry and approval paths are validated |

## Implementation Phases

### Phase 1: Policy Core
CAF-001, CAF-002, CAF-003

Define the capability model and make grants storable and enforceable.

### Phase 2: Risk + Approval Integration
CAF-004, CAF-005, CAF-006

Wire capability classes into verification, bypass, and approval decisions.

### Phase 3: Visibility + Validation
CAF-007, CAF-008, CAF-009

Expose policy health in preflight and Observatory, and cover the framework with tests.

## Success Metrics

| Metric | Target |
|--------|--------|
| Unclassified action types in core runtime | 0 |
| Dangerous blanket permission rules | 0 |
| Emergency bypass false positives | <1% |
| Approval audit coverage for destructive actions | 100% |

## Definition of Done

This PRD is done when:

1. CypherClaw can explain why an action was allowed, denied, verified, or escalated.
2. Shell command families are governed by explicit policy instead of prompt convention alone.
3. Emergency bypasses are narrow and visible.
4. Verification and future web controls can rely on one shared approval model.
