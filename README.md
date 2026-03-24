# PromptClaw

*No claw needed, just prompts.*

PromptClaw is a prompt-native, multi-agent operating layer for software and research work. It lives entirely inside your repo as instruction files, state files, and reusable workflows — no separate app or daemon required. It works across **Codex**, **Claude Code**, and **Gemini**.

## Quick start

1. Clone or use this repo as a template:

   ```bash
   git clone https://github.com/exquest/PromptClaw.git my-project
   cd my-project
   ```

2. Open the project in your preferred agent:

   | Agent | Command |
   |-------|---------|
   | Codex | `codex` then `$promptclaw-startup-checklist` |
   | Claude Code | `claude` (startup runs automatically) |
   | Gemini | `gemini` then `/promptclaw:startup` |

3. On first run, PromptClaw detects that no persona is configured and asks a 15-question onboarding interview. Answer the questions and it configures itself — persona, memory, routing, and routines.

4. After onboarding, every new session starts with a startup checklist that summarizes your state, backlog, and inbox.

## How it works

PromptClaw uses three ideas:

- **Persona first.** The assistant has a name, tone, routines, and autonomy boundaries that are configured once and persist across sessions.
- **Right lane, right task.** Research goes to Gemini, planning goes to Claude, implementation goes to Codex. When the current agent isn't the best lane, PromptClaw creates a delegation packet instead of pretending.
- **Paper trail over vibes.** Journals, backlog updates, research notes, and state changes are part of the work, not afterthoughts.

## Supported agents

| Agent | Adapter file | Skills/commands |
|-------|-------------|-----------------|
| Codex | `AGENTS.md` | `.agents/skills/promptclaw-*/SKILL.md` |
| Claude Code | `CLAUDE.md` | `.claude/skills/promptclaw-*/SKILL.md` |
| Gemini | `GEMINI.md` | `.gemini/commands/promptclaw/*.toml` |

Each agent reads its adapter file on startup, which points to the shared PromptClaw core files under `.promptclaw/`.

## Architecture

```
.promptclaw/
  CORE.md              Core principles and required files
  ROUTER.md            Lane ownership and delegation rules
  ADP.md               Agent Development Protocol (T1/T2/T3)
  PERSONA.md           Assistant persona (populated during onboarding)
  MEMORY.md            Stable preferences and facts
  STATE.json           Machine-readable operational state
  BACKLOG.md           Durable work queue
  INBOX.md             Quick-capture inbox
  JOURNAL/             Dated session journals
  NOTES/               Research briefs, specs, decision memos
    templates/         Reusable note templates (daily brief, weekly retro)
  delegations/         Cross-lane handoff packets
  PROMPTS/             System prompts for each workflow phase
  scripts/             Optional Python integrations
```

## Skills reference

| Skill | Description |
|-------|-------------|
| `startup-checklist` | Run the startup checklist, enforce onboarding, summarize state |
| `persona-onboarding` | Interview the user and configure persona, memory, state, and journal |
| `adp-task-intake` | Classify a coding task as T1/T2/T3 and choose the right lane |
| `adp-t2-run` | Run the full ADP Tier 2 workflow end to end |
| `research-brief` | Run a research mission with citations and save notes |
| `heartbeat` | Process inbox, groom backlog, complete one bounded action |
| `backlog-manager` | Triage inbox and backlog, convert items into prioritized actions |
| `journal-update` | Append a structured journal entry and sync state |
| `self-improve-cycle` | Run one bounded self-improvement cycle on the system itself |

Invoke with `$promptclaw-<name>` in Codex, `/promptclaw-<name>` in Claude Code, or `/promptclaw:<name>` in Gemini.

## Optional integrations

### sdp-cli bridge

If you use [sdp-cli](https://github.com/cascadiantech/sdp-cli) for coding-agent project management, enable the bridge in `STATE.json`:

```json
"integrations": {
  "sdp_cli": {
    "enabled": true,
    "repo_path": "~/path/to/sdp-cli"
  }
}
```

The bridge script (`.promptclaw/scripts/sdp_cli_bridge.py`) pulls task queue, approval, and escalation state into the startup and heartbeat workflows.

### Workspace snapshot

To track multiple repos, populate `.promptclaw/workspace_registry.json` with your projects and enable the integration in `STATE.json`:

```json
"integrations": {
  "workspace": {
    "enabled": true,
    "priority_project_ids": ["my-project", "another-project"]
  }
}
```

The snapshot script (`.promptclaw/scripts/workspace_snapshot.py`) summarizes git branch, progress, and status across your workspace.

## Customization

- **Add a skill:** Create a `SKILL.md` in `.agents/skills/your-skill/` and `.claude/skills/your-skill/`, and a `.toml` in `.gemini/commands/promptclaw/`.
- **Add a prompt template:** Add a markdown file to `.promptclaw/PROMPTS/` and reference it from your skills.
- **Modify routing:** Edit `.promptclaw/ROUTER.md` to change lane ownership or add custom overrides in `STATE.json`.
- **Add a note template:** Add a `.template.md` file to `.promptclaw/NOTES/templates/`.

## License

MIT. See [LICENSE](LICENSE).
