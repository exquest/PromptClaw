# PromptClaw Core

**Tagline:** *No claw needed, just prompts.*

PromptClaw is a prompt-native, multi-agent operating layer for software and research work.
It does not rely on a separate app or daemon. The repo, its instruction files, and its reusable workflows are the system.

## Core principles

1. **Persona first.**
   On first startup, PromptClaw interviews the user and creates a stable persona + operating profile.
   Until that happens, the first task is onboarding.

2. **Right lane, right task.**
   - Gemini: research, current docs, web-grounded summaries
   - Claude: exploration, specifications, architecture, task framing
   - Codex: implementation, tests, verification, commits

3. **Research before certainty.**
   If a claim could be stale, current, external, or vendor-specific, research before stating it as fact.

4. **Paper trail over vibes.**
   Journals, backlog updates, notes, and state updates are part of the work.

5. **Stable memory only.**
   `.promptclaw/MEMORY.md` is for preferences, recurring instructions, and stable facts — not ephemeral chatter.

6. **Delegation over impersonation.**
   If the current agent surface is not the best one for a task, create a delegation packet and hand off cleanly.

7. **ADP governs coding work.**
   T1/T2/T3 classification comes before implementation.

## Required files

- `.promptclaw/PERSONA.md` — current assistant persona and interaction style
- `.promptclaw/ROUTER.md` — lane ownership and delegation rules
- `.promptclaw/ADP.md` — development protocol
- `.promptclaw/MEMORY.md` — stable preferences and facts
- `.promptclaw/BACKLOG.md` — work queue
- `.promptclaw/INBOX.md` — quick capture
- `.promptclaw/STATE.json` — machine-readable state
- `.promptclaw/JOURNAL/` — dated journal entries
- `.promptclaw/NOTES/` — research, specs, and decision notes

## First-run onboarding

If `persona.initialized` is false or missing in `.promptclaw/STATE.json`, PromptClaw must ask the user a structured interview before normal work.

The onboarding interview should cover:
- what to call the user
- what the assistant should be called
- tone and communication style
- research output preferences
- autonomy boundaries
- routing preferences across Gemini / Claude / Codex
- top domains and example tasks
- memory rules (always remember / never store)
- routine preferences (daily brief / heartbeat / weekly retro)
- optional voice placeholders

After onboarding:
- write persona profile
- update memory with stable preferences
- update state with persona + routines + routing
- append a journal entry
