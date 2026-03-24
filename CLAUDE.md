# CLAUDE.md

<!-- PROMPTCLAW:BEGIN -->
## PromptClaw

PromptClaw is enabled for this repository.

@./.promptclaw/CORE.md
@./.promptclaw/ROUTER.md
@./.promptclaw/PERSONA.md
@./.promptclaw/ADP.md
@./.promptclaw/MEMORY.md
@./.promptclaw/BACKLOG.md

Additional startup instructions:

- Read `.promptclaw/INBOX.md`, `.promptclaw/STATE.json`, and the latest journal entry before doing other work.
- If `.promptclaw/STATE.json` does not show `"persona": {"initialized": true}`, stop and run `/promptclaw-persona-onboarding`.
- On normal session start, run `/promptclaw-startup-checklist`.
- Use `/promptclaw-research-brief` for evidence-gathering work, `/promptclaw-adp-task-intake` for new coding tasks, and `/promptclaw-heartbeat` for maintenance cycles.
- Do not impersonate another lane. If Gemini or Codex should own the work, create a delegation packet under `.promptclaw/delegations/`.
- Journal every meaningful task in `.promptclaw/JOURNAL/YYYY-MM-DD.md`.
- Update `.promptclaw/MEMORY.md` only with stable facts and preferences.
- Log ambiguities or policy conflicts to `ESCALATIONS.md` and continue where safe.
- Preserve any host instructions outside this block.
<!-- PROMPTCLAW:END -->
