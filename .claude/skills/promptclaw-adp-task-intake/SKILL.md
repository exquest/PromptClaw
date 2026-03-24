---
name: promptclaw-adp-task-intake
description: Classify a coding task under ADP, decide the lane, and choose whether to run T1, T2, or T3 workflow next.
---

# PromptClaw adp-task-intake

## Workflow
1. Read `.promptclaw/ADP.md`.
2. Classify the task:
   - T1 light
   - T2 standard
   - T3 full
3. Use this heuristic:
   - auth / permissions / payments / schema changes / broad integrations -> prefer T3
   - single-module feature or moderate refactor -> usually T2
   - small bug/config/lint/test fix -> usually T1
4. Decide the lane:
   - Gemini if live external research is needed first
   - Claude for preflight/specification
   - Codex for direct implementation
5. If T3:
   - run a preflight interview
   - produce `SPEC.md`
   - stop after plan creation
6. If T2:
   - produce or request a spec
   - then continue via the T2 workflow
7. If T1:
   - produce a concise execution brief and proceed
8. Log ambiguity to `ESCALATIONS.md`, not to endless chat questions.
