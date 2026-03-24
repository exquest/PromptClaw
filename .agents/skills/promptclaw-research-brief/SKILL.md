---
name: promptclaw-research-brief
description: Run a research-first mission with citations, save notes, and update the journal/backlog.
---

# PromptClaw research-brief

## Purpose
Answer a research question with current evidence, save the work product, and record the decision trail.

## Workflow
1. Restate the question.
2. If the active lane is not Gemini and current/live information matters:
   - create a delegation packet for Gemini under `.promptclaw/delegations/`
   - provide a short local preview
   - stop
3. Otherwise research now:
   - prefer official docs and primary sources
   - note conflicts between sources explicitly
   - keep a decision-useful tone
4. Produce:
   - executive summary
   - key findings
   - risks / unknowns
   - recommended next steps
   - citations
5. Save the full brief under `.promptclaw/NOTES/YYYY-MM-DD__<slug>.md`.
6. Append `Research mission` to today's journal with topic, sources, and decisions.
7. Update backlog if research creates follow-up work.
8. Update memory only if a stable workflow fact emerges.
