# CypherClaw Execution Roadmap

This document turns the current PRD set into one ordered program instead of a pile of parallel ambitions.

The goal is simple:

1. make the home durable
2. make the codebase operable
3. make the agents trustworthy
4. make continuity and autonomy real
5. only then build richer surfaces and art-first expansions on top

## Non-Negotiable Rules

1. Do not schedule late-stage surface work ahead of foundational runtime work.
2. Do not start cross-provider autonomy features before provider/runtime behavior is explicit.
3. Do not rely on tmpfs, ad hoc shells, or raw chat history as operational memory.
4. Do not let one blocked task halt the whole organism.

## Execution Spine

| Stage | PRD | Why it is here | Unlocks |
|---|---|---|---|
| 1 | [prd-home-resilience.md](./prd-home-resilience.md) | Durable state, safe reboot, continuous queue | Everything else |
| 2 | [prd-restructure.md](./prd-restructure.md) | Stable imports, packaging, service paths | Reliable tests, runtime reuse, future services |
| 3 | [prd-model-awareness.md](./prd-model-awareness.md) | Explicit provider/model routing and observability | Cost control, graceful degradation, correct agent choice |
| 4 | [prd-agent-runtime-substrate.md](./prd-agent-runtime-substrate.md) | Shared execution, streaming, sessions, failure classes | Verification, web streaming, introspector |
| 5 | [prd-capability-approval-framework.md](./prd-capability-approval-framework.md) | Explicit action classes and approval boundaries | Safe autonomy, approval UX, verification bypass rules |
| 6 | [prd-verification-system.md](./prd-verification-system.md) | Trustworthy lead/verify/fix behavior | Introspector, safe code changes, reliable high-risk action flow |
| 7 | [prd-context-engine.md](./prd-context-engine.md) | Compaction, handoff briefs, operational memory | Session continuity, web UX, proactive memory |
| 8 | [prd-introspector.md](./prd-introspector.md) | Autonomous diagnosis and repair | Self-healing runtime |
| 9 | [prd-web-platform.md](./prd-web-platform.md) | Rich operator surface | Mission control UI |

## Immediate Priority Slice

These items should be treated as the current P0:

1. Finish the remaining Home Resilience core:
   - checkpoint exporter
   - preflight validator
   - maintenance mode
   - safe reboot
   - post-boot reconciliation
   - blocked-task continuation
2. Complete Restructure so the runtime no longer pays a flat-layout tax.
3. Finish the Model Awareness core:
   - registry
   - selector
   - runtime command construction
   - observatory logging
4. Land the Agent Runtime Substrate core.
5. Land the Capability and Approval Framework core.
6. Then finish the Verification System core.

## Existing PRDs That Should Be Deferred Until the Spine Is Stable

These are important, but they should not outrun the spine:

- [prd-web-platform.md](./prd-web-platform.md)
- [prd-proactive-intelligence.md](./prd-proactive-intelligence.md)
- [prd-local-llm-integration.md](./prd-local-llm-integration.md)
- [prd-federation.md](./prd-federation.md)

They become dramatically easier once the runtime, permissions, verification, and context layers exist.

## Art-Driven Work Order

The art-facing PRDs should follow once the organism itself is stable:

1. [prd-glyphweave-art-studio.md](./prd-glyphweave-art-studio.md)
2. [prd-pet-system-v2.md](./prd-pet-system-v2.md)
3. [prd-narrative-engine.md](./prd-narrative-engine.md)
4. SenseWeave and later physical-output work

Reason: the artistic layers benefit most from a stable home, truthful monitoring, reliable provider degradation, and compacted memory.

## Research-to-Implementation Mapping

The `claude-code-sourcemap` research pass suggests four concrete adoptions:

| Research Pattern | PromptClaw Home |
|---|---|
| `doctor` | Home Resilience preflight + unified doctor |
| `PersistentShell` | Agent Runtime Substrate |
| `compact` | Context Engine |
| tool/permission registry | Capability and Approval Framework |

Use the research repo as a pattern library, not as code to transplant wholesale.

## Task Loading Guidance

When turning this roadmap into `sdp-cli` work:

1. promote the spine tasks above surface/UI work
2. keep later-stage PRDs queued but dependency-gated
3. batch by stage, not by novelty
4. never mix foundation refactors with broad feature work in the same active slice

## Definition of Success

The roadmap is succeeding when:

1. The queue can run unattended through ordinary failures and reboots.
2. A new session can orient from generated context, not archaeology.
3. Agent execution, approval boundaries, and verification are consistent everywhere.
4. The web platform becomes a natural expression of the system, not a compensating layer for instability underneath.
