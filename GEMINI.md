# GEMINI.md

<!-- PROMPTCLAW:BEGIN -->
## PromptClaw

PromptClaw is enabled for this repository.

@./.promptclaw/CORE.md
@./.promptclaw/ROUTER.md
@./.promptclaw/PERSONA.md
@./.promptclaw/ADP.md
@./.promptclaw/MEMORY.md
@./.promptclaw/BACKLOG.md

Startup behavior:
- Read `.promptclaw/INBOX.md`, `.promptclaw/STATE.json`, and the latest journal entry.
- If persona is not initialized, run `/promptclaw:persona` before anything else and wait for the user's answers.
- Otherwise run `/promptclaw:startup` at the start of the session.

Operating rules:
- Use `/promptclaw:research` for current-info research missions.
- Use `/promptclaw:specify` when a task needs planning, exploration, or a spec.
- Use `/promptclaw:execute` only when Gemini is intentionally being used to implement a change.
- Use `/promptclaw:heartbeat` for inbox triage, backlog grooming, and bounded maintenance.
- If another provider should own the task, create a delegation packet under `.promptclaw/delegations/` instead of role-playing that provider.
- Keep `.promptclaw/JOURNAL/`, `.promptclaw/BACKLOG.md`, `.promptclaw/MEMORY.md`, and `.promptclaw/STATE.json` current.
<!-- PROMPTCLAW:END -->
