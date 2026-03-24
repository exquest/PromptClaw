---
name: promptclaw-startup-checklist
description: Run the PromptClaw startup checklist, enforce first-run onboarding, summarize state, and update the session journal/state.
---

# PromptClaw startup-checklist

## Purpose
Start a new PromptClaw session cleanly.

## Workflow
1. Read:
   - `.promptclaw/CORE.md`
   - `.promptclaw/ROUTER.md`
   - `.promptclaw/PERSONA.md`
   - `.promptclaw/ADP.md`
   - `.promptclaw/MEMORY.md`
   - `.promptclaw/BACKLOG.md`
   - `.promptclaw/INBOX.md`
   - `.promptclaw/STATE.json`
   - latest `.promptclaw/JOURNAL/*.md`
2. Ensure today's journal file exists.
3. If `persona.initialized` is not true:
   - state that PromptClaw is not onboarded yet
   - invoke persona onboarding immediately
   - ask the interview below in **one numbered message**
   - stop normal work until the user answers

## First-run interview
1. What should I call you? Include pronouns if you want.
2. Should I keep the assistant name `PromptClaw`, or do you want a distinct persona name? If distinct, what vibe should it have?
3. What default tone should I use?
   - crisp / professional
   - friendly / technical
   - strategic / coach-like
   - minimalist
   - other
4. What answer shape do you prefer by default?
   - short bullets first
   - narrative explanation
   - checklist + next actions
   - mixed
5. For research, what output should I default to?
   - executive bullets
   - decision memo
   - detailed brief
   - mixed
6. What citation style do you want?
   - inline links
   - references at end
   - both
7. What should I be most useful for? Name your top 3 domains.
8. Give 3 example tasks you want me to handle often.
9. Give 2 example tasks you do NOT want me to handle.
10. What should I always remember about your preferences or workflow?
11. What should I never store in memory?
12. When should I pause instead of acting automatically?
13. Confirm routing defaults:
    - Gemini for research?
    - Claude for planning/specification?
    - Codex for implementation?
    - Any overrides?
14. Do you want a heartbeat, daily brief, and weekly retro? If yes, when?
15. Ignore voice for now, or keep placeholders for STT/TTS?

4. If onboarding is already complete:
   - summarize persona name and style
   - summarize top backlog items
   - summarize new inbox items
   - if `.promptclaw/STATE.json` has `integrations.workspace.enabled = true`, run `python3 .promptclaw/scripts/workspace_snapshot.py --json`
   - summarize the highest-priority workspace repos with branch, status source, and the most useful progress or session-note headline
   - identify stale or blocked work
   - recommend the next 1–3 actions with routing notes
5. Update `.promptclaw/STATE.json` session timestamps.
6. Append a `Startup checklist` entry to today's journal.
7. Keep the output to about one screen unless the user asks for more detail.

## Workspace integration notes

- Use the workspace snapshot when `integrations.workspace.enabled` is true in `.promptclaw/STATE.json`.
- The snapshot should come from:
  - `python3 .promptclaw/scripts/workspace_snapshot.py --json`
- Prefer the workspace registry and repo-local progress/session files over ad hoc directory spelunking during normal startup.
