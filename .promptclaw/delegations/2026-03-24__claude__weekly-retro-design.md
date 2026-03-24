# Delegation Packet: Claude — Weekly Retro Design

## Mission
Define Anthony's Sunday `6:00 PM` local weekly retro format, required review inputs, synthesis logic, and output template.

## Why This Lane Owns It
This is a planning and specification task. It needs a clear review structure, prioritization framework, and useful output design before any implementation or automation work starts.

## Context Files To Read
- `.promptclaw/CORE.md`
- `.promptclaw/ROUTER.md`
- `.promptclaw/PERSONA.md`
- `.promptclaw/MEMORY.md`
- `.promptclaw/BACKLOG.md`
- `.promptclaw/STATE.json`
- `.promptclaw/JOURNAL/2026-03-24.md`
- `.promptclaw/NOTES/templates/weekly_retro.template.md`

## Required Deliverable
Produce a design brief that defines:

1. The purpose of the weekly retro and what decisions it should help Anthony make each Sunday evening.
2. The exact sections and ordering of the retro.
3. The required review inputs, including:
   - infrastructure and service status over the week
   - websites and work infrastructure progress
   - active project movement and outcomes
   - `sdp-cli` process reliability and issues
   - important research findings gathered during the week
   - relevant external events or context worth carrying forward
4. The synthesis logic for:
   - wins
   - misses
   - risks
   - backlog changes
   - next week's priorities
5. The default output style aligned to Anthony's persona preferences:
   - strategic tone
   - short bullets first, then mixed detail
   - Markdown-first
   - emojis and ASCII art when they improve readability
6. A ready-to-use weekly retro template.
7. A short list of implementation notes for the later Codex workflow.

## Constraints
- Do not implement automation, scripts, or schedulers.
- Do not widen scope beyond the weekly retro design.
- Keep the standard retro concise enough to scan quickly, with optional deeper detail where useful.
- Optimize for decisions and carry-forward actions, not generic reflection.
- Respect Anthony's pause rules and secrecy rules.
- If a section depends on current external information, note that it will require research-first handling at execution time.

## Files To Update
- `.promptclaw/NOTES/2026-03-24__weekly-retro-design.md`
- `.promptclaw/NOTES/templates/weekly_retro.template.md`
- `.promptclaw/BACKLOG.md`
- `.promptclaw/JOURNAL/2026-03-24.md`
- `.promptclaw/STATE.json`

## Return Format
- `Summary:` 3 to 6 bullets
- `Files updated:`
- `Open questions:`
- `Recommended next route:` one short routing sentence
