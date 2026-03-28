# Command Reference

## `promptclaw init`

Create a new project scaffold.

```bash
promptclaw init PATH [--name NAME] [--no-wizard]
```

Creates:

- `promptclaw.json`
- `prompts/`
- `docs/`
- `.promptclaw/`
- example tasks

When running in an interactive terminal, `init` launches the startup wizard unless `--no-wizard` is passed.

## `promptclaw wizard`

Run the startup wizard again for an existing project.

```bash
promptclaw wizard PROJECT_ROOT
```

Use this when:

- the claw’s purpose has changed
- you want to refine routing
- you want to change the agent roster
- you want a fresh startup transcript

## `promptclaw doctor`

Validate a project.

```bash
promptclaw doctor PROJECT_ROOT
```

Checks:

- config file exists
- prompts directory exists
- artifact root exists
- agents are configured
- command agents have executable commands
- control plane agent exists if `mode=agent`

## `promptclaw bootstrap`

Run the bootstrap task using the startup materials.

```bash
promptclaw bootstrap PROJECT_ROOT
```

Equivalent to composing a task from:

- `prompts/00-project-vision.md`
- `prompts/01-agent-roles.md`
- `prompts/02-routing-rules.md`
- `docs/STARTUP_PROFILE.md` if present

## `promptclaw run`

Run a task.

```bash
promptclaw run PROJECT_ROOT --task-file FILE
promptclaw run PROJECT_ROOT --task "free text"
```

For live `command` agents, PromptClaw executes from `PROJECT_ROOT` and renders `{prompt_file}` and `{project_root}` as absolute paths.

## `promptclaw resume`

Resume an ambiguous task.

```bash
promptclaw resume PROJECT_ROOT --run-id RUN_ID --answer "clarification answer"
```

## `promptclaw status`

Show project status.

```bash
promptclaw status PROJECT_ROOT
promptclaw status PROJECT_ROOT --run-id RUN_ID
```

## `promptclaw show-config`

Print resolved config.

```bash
promptclaw show-config PROJECT_ROOT
```
