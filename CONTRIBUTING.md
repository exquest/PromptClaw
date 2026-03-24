# Contributing to PromptClaw

Thanks for your interest in PromptClaw. This guide covers how to set up, extend, and contribute back.

## Setup

1. Fork and clone the repo.
2. Open the project in Codex, Claude Code, or Gemini.
3. On first run, PromptClaw will ask a persona onboarding interview. This is expected — it configures your local instance.

No build step or dependency install is required. The Python scripts under `.promptclaw/scripts/` use only the standard library.

## Running tests

```bash
cd /path/to/PromptClaw
python3 -m pytest tests/
```

Tests must be run from the repo root since they use relative paths.

## Project structure

- **Adapter files** (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`) — Entry points for each agent. They include the shared PromptClaw core.
- **Core files** (`.promptclaw/CORE.md`, `ROUTER.md`, `ADP.md`) — Framework rules shared across all agents.
- **User state** (`.promptclaw/PERSONA.md`, `MEMORY.md`, `STATE.json`, etc.) — Populated per-user during onboarding. Do not commit personal state to upstream.
- **Skills** (`.agents/skills/`, `.claude/skills/`, `.gemini/commands/`) — Provider-specific implementations of shared workflows.
- **Prompts** (`.promptclaw/PROMPTS/`) — Lightweight system prompts for each workflow phase.

## Adding a new skill

1. Create `.agents/skills/promptclaw-your-skill/SKILL.md` with YAML front matter (`name`, `description`) and a markdown body describing the workflow.
2. Mirror it in `.claude/skills/promptclaw-your-skill/SKILL.md`.
3. Create `.gemini/commands/promptclaw/your-skill.toml` with a `description` and `prompt` field.
4. If the skill uses a shared prompt, add it to `.promptclaw/PROMPTS/`.

## Commit style

Use [conventional commits](https://www.conventionalcommits.org/):

```
feat(promptclaw): add new research workflow
fix(scripts): handle missing registry gracefully
docs: update README with integration guide
```

## What not to commit

- Personal state files (persona, memory, journal entries, backlog items)
- Secrets, tokens, or credentials
- `__pycache__/` directories

The `.gitignore` includes commented-out patterns for user state files. Uncomment them if you want git to ignore your local state.

## Code of conduct

Be respectful and constructive. PromptClaw is a collaborative project — treat contributors the way you'd want to be treated.
