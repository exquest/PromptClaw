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

## Operator Loop

Build the local PAL knowledge index after docs, ops files, smoke reports, or run
artifacts change:

```bash
promptclaw pal kb build pal-2026
```

Query the local index before asking PAL to reason about deployment state:

```bash
promptclaw pal kb query pal-2026 --query "router restart"
```

The query command returns ranked snippets with source paths and line ranges and
does not contact the live PAL router.

Use `ops/deployment-manifest.json` as the local deployment file source of truth.
`promptclaw.pal_deploy` can compare that manifest to fake remote snapshots and
report deploy diff sets for added, changed, missing, unchanged, and unmanaged
remote files. Operators can print the dry-run deploy plan without remote writes:

```bash
promptclaw pal deploy plan pal-2026
```

Use `--remote-inventory PATH --json` when comparing against a saved local remote
snapshot. This is still dry-run planning only: apply, backup, rollback, service
restarts, and approval flags remain separate future approval-gated work.

## Validation

```bash
python -m promptclaw.cli doctor pal-2026
```
