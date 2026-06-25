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

### `coherence`

```json
{
  "enabled": true,
  "database_url": "",
  "redis_url": "",
  "constitution_path": "constitution.yaml",
  "enforcement_mode": "monitor",
  "auto_graduate": true,
  "graduation_confidence_threshold": 0.85,
  "graduation_false_positive_threshold": 0.05
}
```

The coherence engine preserves decisions, held tensions, constitutional verdicts,
trust scores, and the re-entry digest for each project.

- `enabled`: turns the runtime coherence hooks on or off. When `false`, PromptClaw
  uses the no-op coherence engine and external `open_session(...)` callers get a
  no-op session.
- `database_url`: event-store backend. Leave empty for the default SQLite store at
  `.promptclaw/coherence.db`; use a `postgresql://...` URL with the `coherence-pg`
  extra for PostgreSQL-backed events.
- `redis_url`: optional Redis URL passed to the PostgreSQL event-store backend.
  It is unused by the default SQLite path.
- `constitution_path`: project-root-relative YAML or JSON file loaded by the
  constitution evaluator. Fresh projects use `constitution.yaml`.
- `enforcement_mode`: one of `monitor`, `soft`, or `full`.
  - `monitor`: evaluate and record violations, but never block.
  - `soft`: block hard-severity violations only.
  - `full`: block any hard or soft violation.
- `auto_graduate`: lets the engine promote enforcement modes when observed
  detection quality clears the thresholds below.
- `graduation_confidence_threshold`: minimum true-positive confidence for
  promotion from `monitor` to `soft`, after at least 20 observations.
- `graduation_false_positive_threshold`: maximum false-positive rate for
  promotion from `soft` to `full`, after at least 10 runs in soft mode.

### `pal`

```json
{
  "enabled": true,
  "base_url": "http://pal-cloud-a6000:8000",
  "default_model": "llama3.3:70b-instruct-q4_K_M",
  "timeout_s": 300.0,
  "health_timeout_s": 10.0
}
```

- `enabled`: include PAL router health in `promptclaw doctor`.
- `base_url`: FastAPI router endpoint, usually the Tailscale hostname.
- `default_model`: model sent to `/query` when a command does not override it.
- `timeout_s`: request timeout for inference calls.
- `health_timeout_s`: request timeout for `/health` checks.

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
