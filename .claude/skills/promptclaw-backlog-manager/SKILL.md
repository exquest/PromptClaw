---
name: promptclaw-backlog-manager
description: Triage the PromptClaw inbox and backlog, convert raw items into prioritized actions, and keep the queue clean.
---

# PromptClaw backlog-manager

## Workflow
1. Read `.promptclaw/INBOX.md` and `.promptclaw/BACKLOG.md`.
2. Convert raw inbox items into structured backlog entries.
3. Use priorities:
   - P0 urgent / blocking
   - P1 important / next
   - P2 useful / later
   - P3 someday / nice-to-have
4. Keep sections tidy:
   - INBOX
   - NEXT
   - DOING
   - BLOCKED
   - DONE
5. Add acceptance criteria when a task is vague.
6. Append processed items to the inbox processed log.
7. Journal any substantial grooming decisions.
