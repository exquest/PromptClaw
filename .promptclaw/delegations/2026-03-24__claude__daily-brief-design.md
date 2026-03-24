# Delegation Packet: Claude — Daily Brief Design

## Mission
Define Anthony's `8:00 AM` local daily brief format, required inputs, prioritization logic, and output template.

## Why This Lane Owns It
This is a planning and specification task. It needs structure, scope discipline, and a strong output design before any implementation or automation work starts.

## Context Files To Read
- `.promptclaw/CORE.md`
- `.promptclaw/ROUTER.md`
- `.promptclaw/PERSONA.md`
- `.promptclaw/MEMORY.md`
- `.promptclaw/BACKLOG.md`
- `.promptclaw/STATE.json`
- `.promptclaw/JOURNAL/2026-03-24.md`
- `.promptclaw/NOTES/templates/daily_brief.template.md`

## Required Deliverable
Produce a design brief that defines:

1. The purpose of the daily brief and what decisions it should help Anthony make each morning.
2. The exact sections and ordering of the brief.
3. The required input categories, including:
   - running servers and service health
   - websites and work infrastructure
   - active projects
   - `sdp-cli` process health
   - relevant current news and events
   - relevant local and regional event listings
4. The prioritization logic for what makes the top of the brief.
5. The default output style aligned to Anthony's persona preferences:
   - strategic tone
   - short bullets first, then mixed detail
   - Markdown-first
   - emojis and ASCII art when they improve readability
6. A ready-to-use daily brief template.
7. A short list of implementation notes for the later Codex workflow.

## Constraints
- Do not implement automation, scripts, or schedulers.
- Do not widen scope beyond the daily brief design.
- Keep the default morning brief to about one screen.
- Optimize for signal over exhaustiveness.
- Respect Anthony's pause rules and secrecy rules.
- If a claim depends on current external information, note that it will require research-first handling at execution time.

## Files To Update
- `.promptclaw/NOTES/2026-03-24__daily-brief-design.md`
- `.promptclaw/NOTES/templates/daily_brief.template.md`
- `.promptclaw/BACKLOG.md`
- `.promptclaw/JOURNAL/2026-03-24.md`
- `.promptclaw/STATE.json`

## Return Format
- `Summary:` 3 to 6 bullets
- `Files updated:`
- `Open questions:`
- `Recommended next route:` one short routing sentence
