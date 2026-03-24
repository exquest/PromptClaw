# State and Memory

PromptClaw keeps three kinds of durable context.

## 1. Run state

Run state lives per execution:

```text
.promptclaw/runs/<run-id>/state.json
```

It includes:

- status
- current phase
- selected agents
- route decision
- clarification question, if any
- final summary path
- timestamps

## 2. Project memory

Project memory is cross-run context:

```text
.promptclaw/memory/project-memory.md
```

The orchestrator appends a short summary after each completed or paused run.

## 3. Startup memory

Startup capture lives in:

```text
docs/STARTUP_PROFILE.md
docs/STARTUP_TRANSCRIPT.md
.promptclaw/onboarding/startup-session.md
```

These files document how the claw was initially configured.

## Why all three exist

- run state is for recovery
- project memory is for continuity
- startup memory is for intent and baseline behavior

## When to reset memory

Consider pruning or resetting when:

- the claw has changed purpose
- agent roles have been redesigned
- old context is causing bad routing
- you want a clean baseline

## Safe cleanup

- delete one run directory: remove `.promptclaw/runs/<run-id>/`
- keep memory, delete all runs: remove `.promptclaw/runs/`
- reset runtime only: remove `.promptclaw/`
- refresh startup intent: rerun `promptclaw wizard .`

## Recommendation

Keep memory concise. The orchestrator is better when it gets:

- important decisions
- unresolved issues
- durable preferences

and worse when it gets:

- raw transcripts from every task
- giant dumps
- repeated boilerplate
