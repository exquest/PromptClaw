# Handoff Protocol

PromptClaw v2.1 uses **artifact handoffs** rather than agent-to-agent chat.

## Rule

One agent never directly passes work to another. The orchestrator does.

## Mechanism

For each step, the orchestrator writes:

- the task input
- the route decision
- the handoff brief
- the prompt given to the next agent
- the output returned by that agent
- optional verification output
- the final summary

For live `command` agents, the orchestrator invokes the local CLI from the project root and passes an absolute `{prompt_file}` path for the prompt artifact it just wrote.

In CypherClaw live operations, those handoffs only begin after the bootstrap and preflight gates pass. The runner launcher refuses to start if maintenance mode is active, if the workdir layout is incomplete, or if the authoritative SQLite files fail integrity checks.

The operator-facing health check now follows the same split: `promptclaw doctor` validates PromptClaw config for every project and automatically adds runtime preflight when the project root includes live CypherClaw runtime markers.

## Files

```text
.promptclaw/runs/<run-id>/
├── input/task.md
├── routing/route.json
├── routing/route.md
├── prompts/lead-<agent>.md
├── outputs/lead-<agent>.md
├── handoffs/lead-to-verify.md
├── prompts/verify-<agent>.md
├── outputs/verify-<agent>.md
├── summary/final-summary.md
└── logs/events.jsonl
```

## Benefits

- deterministic transfer point
- reproducible history
- resumable runs
- better debugging
- compatible with mixed local tools

## Startup handoff

Before runtime handoffs begin, the startup wizard can generate the initial routing documents and agent lanes. That gives the orchestrator a cleaner starting point than raw placeholder prompts.

## Clarification flow

If the route decision marks the task as ambiguous, the orchestrator writes:

```text
summary/clarification-request.md
```

Then run status becomes `awaiting_user`.

To continue:

```bash
promptclaw resume . --run-id <run-id> --answer "your answer"
```

## Verification contract

Verification prompts instruct the chosen verifier to emit:

```text
VERDICT: PASS
```

or

```text
VERDICT: PASS_WITH_NOTES
```

or

```text
VERDICT: FAIL
```

PromptClaw parses that marker and decides whether to complete, retry, or fail.

## Retry policy

By default:

- one lead pass
- one verifier pass
- one retry after fail

You can change this in `promptclaw.json`.

For CypherClaw live command runs, provider availability can also change the handoff path. When quota telemetry marks a provider as degraded or paused, the orchestrator can swap to another provider for lead/verify work, and in single-agent degraded mode it can temporarily assign the same available agent to both roles until headroom recovers.

The runtime transport itself is also guarded now:

- `my-claw/tools/init_workdir.sh` prepares the tmpfs workdir and symlinks authority DBs back to disk.
- `my-claw/tools/sdp_runner_launcher.sh` runs preflight before `sdp-cli run`.
- `my-claw/tools/safe_reboot.sh prepare` checkpoints and enters maintenance mode before shutdown.
- `my-claw/tools/safe_reboot.sh resume` validates the latest checkpoint before reopening the runner.
