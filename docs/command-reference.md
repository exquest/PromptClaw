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
- if the project root also contains live CypherClaw runtime markers, runtime preflight is run too

For CypherClaw live deployments, the repo also ships runtime safety tools that sit beneath `promptclaw doctor` until the unified doctor/preflight path lands:

- `python my-claw/tools/preflight.py --project-root PROJECT_ROOT`
- `python my-claw/tools/runtime_checkpoint.py --project-root PROJECT_ROOT`
- `python my-claw/tools/maintenance_mode.py --project-root PROJECT_ROOT status`
- `bash my-claw/tools/safe_reboot.sh prepare --actor operator --dry-run`
- `bash my-claw/tools/safe_reboot.sh resume --checkpoint PATH --actor operator --dry-run`

If `PROJECT_ROOT` looks like a live CypherClaw runtime, `promptclaw doctor PROJECT_ROOT` now runs the same preflight automatically and reports it as a separate doctor check.

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

In CypherClaw live command deployments, `run` can also honor `sdp-cli` quota telemetry. Healthy and warn providers stay eligible for routing, degraded providers stop receiving new work, and full exhaustion falls back to the provider with the best remaining headroom so runs continue in degraded mode.

Before the long-running queue starts, the runtime launcher also enforces:

- maintenance mode must be inactive
- preflight must pass
- the tmpfs workdir must be present and correctly linked to disk-authoritative DBs

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

## CypherClaw runtime utilities

These are repo-managed operational tools for the live CypherClaw home:

```bash
bash my-claw/tools/init_workdir.sh
python my-claw/tools/preflight.py --project-root .
python my-claw/tools/runtime_checkpoint.py --project-root .
python my-claw/tools/maintenance_mode.py --project-root . enter --reason "planned reboot"
bash my-claw/tools/safe_reboot.sh prepare --actor anthony
bash my-claw/tools/safe_reboot.sh resume --checkpoint .sdp/recovery/checkpoint-<stamp>.json --actor anthony
```

Systemd units shipped with this repo:

- `my-claw/systemd/cypherclaw-bootstrap.service`
- `my-claw/systemd/cypherclaw-sdp-runner.service`

Daemon status utility:

```bash
python my-claw/tools/cypherclaw_daemon.py --status
```

This probe is platform-aware: it checks `launchctl` on macOS homes and `systemctl` on Linux homes so status checks do not crash when the local service manager is absent.
