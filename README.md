# PromptClaw

*No claw needed, just prompts.*

PromptClaw is a prompt-native, multi-agent operating layer for software and research work. It lives entirely inside your repo as instruction files, state files, and reusable workflows — no separate app or daemon required. It works across **Codex**, **Claude Code**, and **Gemini**.

## Quick start

### 1. Get the repo

Clone it into your project directory, or use it as a GitHub template:

```bash
git clone https://github.com/exquest/PromptClaw.git my-project
cd my-project
```

Alternatively, click **Use this template** on GitHub to create your own copy.

### 2. Pick your agent and launch

PromptClaw works with three AI coding agents. Pick whichever you already have installed:

**Codex (OpenAI)**
```bash
codex
```
Then run:
```
$promptclaw-startup-checklist
```

**Claude Code (Anthropic)**
```bash
claude
```
PromptClaw starts automatically — `CLAUDE.md` is read on launch.

**Gemini (Google)**
```bash
gemini
```
Then run:
```
/promptclaw:startup
```

### 3. Complete the onboarding interview

On first run, PromptClaw sees that no persona is configured and asks you 15 questions:

- What to call you and the assistant
- Tone and communication style
- Research output preferences
- Your top domains and example tasks
- Autonomy boundaries (when to pause vs. act)
- Routing preferences across agents
- Routine preferences (daily brief, heartbeat, weekly retro)

Answer in one message. PromptClaw writes your persona to `PERSONA.md`, saves stable preferences to `MEMORY.md`, updates `STATE.json`, and logs the session to `JOURNAL/`.

### 4. Start working

After onboarding, every new session opens with a startup checklist that shows:
- Your persona summary
- Top backlog items and inbox
- Workspace status (if configured)
- Suggested next actions with routing

From there, use skills to drive work:

```
$promptclaw-adp-task-intake     # classify and route a coding task
$promptclaw-research-brief      # run a research mission
$promptclaw-heartbeat           # maintenance cycle
```

Drop quick ideas into `.promptclaw/INBOX.md` — the heartbeat skill picks them up and converts them into backlog items or delegation packets.

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
