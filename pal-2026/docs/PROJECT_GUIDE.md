# Project Guide

PAL 2026 is a dedicated PromptClaw project for Anthony's Phase 1 cloud
deployment.

## Primary Files

- `ops/phase-1-checkpoints.md`: live deployment runbook.
- `ops/session-state.md`: pause/resume state.
- `ops/deviation-log.md`: errors and deviations for guide v2.
- `examples/tasks/phase-1-deployment.md`: PromptClaw task entry point.
- `prompts/agents/pal-setup.md`: dedicated setup lane.

## Current Mode

Agents are configured as `mock` so this project can be validated without
launching external CLIs. The live deployment guidance happens in the active
Codex chat unless Anthony later chooses to wire live command agents.

## Validation

```bash
python -m promptclaw.cli doctor pal-2026
```
