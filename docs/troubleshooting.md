# Troubleshooting

## Problem: the run pauses immediately

Check `summary/clarification-request.md`.

The orchestrator detected ambiguity and is waiting for a clarification answer.

Resume with:

```bash
promptclaw resume . --run-id <run-id> --answer "..."
```

## Problem: the startup prompts feel generic

Rerun the wizard:

```bash
promptclaw wizard .
```

Then review:

- `docs/STARTUP_PROFILE.md`
- `prompts/00-project-vision.md`
- `prompts/01-agent-roles.md`
- `prompts/02-routing-rules.md`

## Problem: no live agents run

Check `promptclaw.json`.

Common causes:

- agents are still in `mock` mode
- `shell_command` is empty
- local CLI tool is not installed
- control plane is set to `agent` but the named agent is disabled

Run:

```bash
promptclaw doctor .
```

## Problem: the wrong lead agent gets selected

Improve one or more of:

- `prompts/01-agent-roles.md`
- `prompts/02-routing-rules.md`
- agent capability lists in `promptclaw.json`
- `prompts/control/routing.md`
- `docs/STARTUP_PROFILE.md`

## Problem: verifier keeps failing good work

Adjust:

- verification prompt wording
- retry policy
- verifier agent choice
- expected output shape

## Problem: memory is making routing worse

Reset project memory:

```bash
rm .promptclaw/memory/project-memory.md
```

Or rerun the startup wizard if the problem is really stale intent rather than stale runtime memory.

## Problem: route JSON is malformed

If control plane mode is `agent`, the agent returned bad JSON.

Options:

- tighten `prompts/control/routing.md`
- switch temporarily to `heuristic`
- use a different control-plane agent

## Problem: run directories are too noisy

Turn long-form artifacts into shorter summaries, but keep these:

- `state.json`
- `routing/route.json`
- `outputs/*.md`
- `summary/final-summary.md`
