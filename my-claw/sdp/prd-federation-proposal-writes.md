# PRD: Federation Proposal and Approval Writes

## Overview

Federation writes must obey one hard rule:

> cross-home mutations are proposals, never direct action.

Every home is sovereign. A home may read public/default-readable state from trusted peers, but any code, config, queue, memory, or runtime mutation on another home must be approved by the target home first.

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| FEDWRITE-001 | Define proposal-based mutation types for cross-home writes: code/config changes, task delegation, memory import, bundle import, publication changes, and runtime actions. | MUST | T1 | - Mutation classes are enumerated in one protocol schema<br/>- Each proposal has type, scope, reason, source, and requested effects<br/>- Proposal types map cleanly to target-home approval policies |
| FEDWRITE-002 | Implement target-home approval gating for every cross-home mutation. No mutation request may execute until the target home approves it locally. | MUST | T1 | - Unapproved proposals cannot mutate local state<br/>- Approved proposals execute locally on the target home<br/>- Approval decision is auditable |
| FEDWRITE-003 | Add proposal inbox/outbox state so homes can receive, inspect, approve, reject, and expire mutation requests. | MUST | T1 | - Received proposals are persisted locally<br/>- Operators/agents can inspect proposal state<br/>- Expired/rejected proposals do not execute |
| FEDWRITE-004 | Separate read trust from write trust. Readable descendants/peers must not gain write power automatically. | MUST | T1 | - Descendant auto-trust grants read only<br/>- Write proposals still require target approval<br/>- Revoking read trust does not corrupt proposal history |
| FEDWRITE-005 | Add signed proposal transport and signed target-home responses with replay protection and expiry. | MUST | T2 | - Proposals and responses are signed<br/>- Replay attempts are rejected<br/>- Expired proposals are ignored safely |
| FEDWRITE-006 | Implement explicit task delegation as a proposal type rather than direct queue mutation. Delegated tasks must land in the target home’s approval flow before they enter its local queue. | SHOULD | T2 | - Delegated work is inspectable before acceptance<br/>- Accepted work lands in the target queue as local work<br/>- Rejected work never enters the target queue |
| FEDWRITE-007 | Add tests for proposal creation, transmission, approval, rejection, expiration, replay protection, and delegated-task approval behavior. | MUST | T2 | - Test suite covers full proposal lifecycle<br/>- Replay protection is enforced in tests<br/>- Delegation tests prove no unapproved queue mutation |

## Notes

- This PRD replaces the earlier “full collaboration by default” framing with a sovereignty-first write model.
- Target-home approval is the defining boundary of healthy federation behavior.
