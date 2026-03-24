# Live Agent Setup

Generated projects start in `mock` mode so the orchestration flow is testable without any external tools.

## Step 1 — Open the config

Edit `promptclaw.json`.

## Step 2 — For each live agent

Set:

- `kind` to `command`
- either `shell_command` or `command`
- optional `env`

Example shell command pattern:

```json
{
  "kind": "command",
  "shell_command": "your-local-agent-cli --prompt-file {prompt_file}"
}
```

Example argv pattern:

```json
{
  "kind": "command",
  "command": ["your-local-agent-cli", "--prompt-file", "{prompt_file}"]
}
```

## Step 3 — Keep metadata accurate

Make sure these stay aligned with reality:

- `capabilities`
- `instruction_file`
- `enabled`

The startup wizard will draft these for you, but live use depends on keeping them accurate.

## Step 4 — Validate

```bash
promptclaw doctor .
```

## Control plane choices

- keep `control_plane.mode = "heuristic"` for deterministic routing
- switch to `control_plane.mode = "agent"` to let one configured agent perform routing

## Important

Use the exact invocation syntax that already works on your machine. PromptClaw does not assume any specific vendor CLI flag format.
