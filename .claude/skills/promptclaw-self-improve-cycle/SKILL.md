---
name: promptclaw-self-improve-cycle
description: Run one bounded PromptClaw self-improvement cycle on the system itself, route it correctly, and leave a clean paper trail.
---

# PromptClaw self-improve-cycle

## Goal
Improve PromptClaw itself without turning maintenance into chaos.

## Workflow
1. Read `.promptclaw/BACKLOG.md`, `.promptclaw/STATE.json`, and recent journal entries.
2. Choose one PromptClaw-internal P0 or P1 item.
3. Decide the best lane:
   - Gemini for research
   - Claude for planning/spec design
   - Codex for implementation
4. If this lane is wrong for the chosen item:
   - create a delegation packet
   - stop after summarizing the handoff
5. If this lane is right:
   - do one bounded cycle of work
   - verify coherence with `.promptclaw/CORE.md`, `.promptclaw/ROUTER.md`, and `.promptclaw/PERSONA.md`
6. Update backlog, state, and journal.
7. Commit only if meaningful files changed.
