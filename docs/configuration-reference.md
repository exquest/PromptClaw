# Configuration Reference

Each project uses `promptclaw.json`.

## Top-level keys

### `project`

```json
{
  "name": "My PromptClaw",
  "description": "Short description"
}
```

The startup wizard updates `description` from your project pitch.

### `artifacts`

```json
{
  "root": ".promptclaw"
}
```

### `control_plane`

```json
{
  "mode": "heuristic",
  "agent": "claude",
  "allow_fallback": true
}
```

- `mode=heuristic`: built-in router
- `mode=agent`: ask the named agent for routing JSON

### `routing`

```json
{
  "verification_enabled": true,
  "max_retries": 1,
  "ask_user_on_ambiguity": true,
  "default_task_type": "general"
}
```

The startup wizard may update `verification_enabled` and `ask_user_on_ambiguity`.

### `agents`

Each agent has:

```json
{
  "enabled": true,
  "kind": "mock",
  "shell_command": "",
  "command": [],
  "env": {},
  "capabilities": ["coding", "implementation", "testing"],
  "instruction_file": "prompts/agents/codex.md"
}
```

## Agent kinds

- `mock`: deterministic fake output
- `echo`: returns the prompt as output
- `command`: run a local command

## Wizard behavior

The startup wizard can:

- disable agents that are not in the chosen roster
- add custom agents
- infer capability tags from your answers
- create prompt files under `prompts/agents/`

## Live mode notes

For live mode, set:

- `kind` = `command`
- either `shell_command` or `command`
- optional `env`

Use the exact invocation syntax your machine already uses.
PromptClaw renders `{prompt_file}` and `{project_root}` as absolute paths and runs the process from the project root.

## Capability tags

Capability tags drive heuristic routing. Common tags:

- `coding`
- `implementation`
- `testing`
- `architecture`
- `specification`
- `verification`
- `analysis`
- `research`
- `writing`
- `docs`
- `synthesis`

## Prompt files

Generated projects use:

- `prompts/control/routing.md`
- `prompts/control/review.md`
- `prompts/control/summarize.md`
- `prompts/agents/codex.md`
- `prompts/agents/claude.md`
- `prompts/agents/gemini.md`

Custom agent files can be added automatically by the startup wizard.
