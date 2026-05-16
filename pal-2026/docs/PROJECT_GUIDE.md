# Project Guide

PAL 2026 is a dedicated PromptClaw project for Anthony's Phase 1 cloud
deployment.

## Primary Files

- `ops/phase-1-checkpoints.md`: live deployment runbook.
- `ops/deployment-manifest.json`: repo-managed intended `/opt/pal` file list.
- `ops/session-state.md`: pause/resume state.
- `ops/deviation-log.md`: errors and deviations for guide v2.
- `examples/tasks/phase-1-deployment.md`: PromptClaw task entry point.
- `prompts/agents/pal-setup.md`: dedicated setup lane.

## Current Mode

Agents are configured as `mock` so this project can be validated without
launching external CLIs. The live deployment guidance happens in the active
Codex chat unless Anthony later chooses to wire live command agents.

## Operator Loop: Local-First Build → Query → Plan

The PAL 2026 operator loop is called the **Local-First Build → Query → Plan
loop**. Every step runs against local artifacts only; none of these commands
contact the live PAL router or write to the remote host.

1. **Build** the local PAL knowledge index after docs, ops files, smoke reports,
   or run artifacts change:

```bash
promptclaw pal kb build pal-2026
```

2. **Query** the local index before asking PAL to reason about deployment
   state:

```bash
promptclaw pal kb query pal-2026 --query "router restart"
```

The query command returns ranked snippets with source paths and line ranges and
does not contact the live PAL router.

3. **Plan** the deploy from `ops/deployment-manifest.json`, the local
   deployment-file source of truth. `promptclaw.pal_deploy` compares that
   manifest to remote snapshots and reports deploy diff sets for added, changed,
   missing, unchanged, and unmanaged remote files. Operators print the dry-run
   deploy plan without remote writes:

```bash
promptclaw pal deploy plan pal-2026
```

Use `--remote-inventory PATH --json` when comparing against a saved local remote
snapshot. This is still dry-run planning only: apply, backup, rollback, service
restarts, and approval flags remain separate future approval-gated work.

## Live PAL Verification Commands

Operators verifying a live PAL router run these checks in order. Every command
below contacts the configured router; none of them apply, restart, or otherwise
mutate remote infrastructure.

1. **Health**: confirm the router is reachable and reporting status.

```bash
promptclaw pal health pal-2026
```

Pair with the opt-in pytest gate when validating router connectivity from the
test suite:

```bash
pytest tests/test_pal_live.py --run-live-pal
```

2. **Smoke**: run the restart smoke suite and write the report under
   `.promptclaw/pal-smoke/`.

```bash
promptclaw pal smoke pal-2026
```

3. **Triage**: bounded PAL ops triage that surfaces findings as a handoff
   artifact without proposing or executing actions.

```bash
promptclaw pal agent triage pal-2026
```

4. **Proposal-only actions**: propose approval-gated actions without executing
   any of them. Omit `--approve` to keep the run proposal-only.

```bash
promptclaw pal agent actions pal-2026
```

5. **Read-only action checks**: scoped workflows that report state without
   mutating PAL.

```bash
promptclaw pal diagnose slow-inference pal-2026
promptclaw pal validate restart pal-2026
promptclaw pal audit shutdown pal-2026
promptclaw pal report phase2-readiness pal-2026
```

## Validation

```bash
python -m promptclaw.cli doctor pal-2026
```
