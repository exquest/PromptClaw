---
name: promptclaw-journal-update
description: Append a structured PromptClaw journal entry, update state, and keep memory/backlog in sync with the work that just happened.
---

# PromptClaw journal-update

## Journal entry format
Append to `.promptclaw/JOURNAL/YYYY-MM-DD.md`:

## HH:MM — <title>
- Mission:
- Lane:
- Files touched:
- Commands run:
- Decisions:
- Sources:
- Follow-ups:

## Rules
- Keep entries compact but useful.
- Update `.promptclaw/STATE.json` with `session.last_task_at` and `session.last_task_summary`.
- Update `.promptclaw/MEMORY.md` only with stable preferences or enduring facts.
- Update `.promptclaw/BACKLOG.md` when follow-up items appear.
- Avoid vanity commits for no-op entries.
