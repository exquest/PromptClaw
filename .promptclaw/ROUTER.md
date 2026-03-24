# PromptClaw Router

PromptClaw routes work to the best available lane. The current agent should not pretend to be another lane when a clean delegation is possible.

## Default routing

- **Gemini**
  - current docs
  - web research
  - vendor comparisons
  - quick source gathering
  - evidence-grounded summaries

- **Claude**
  - explore / understand
  - specify / plan
  - architectural reasoning
  - refactor design
  - preflight interviews for T3 tasks

- **Codex**
  - code implementation
  - writing / updating tests
  - verification
  - repository edits
  - commit workflow

## Delegation packet

If the current lane is not the best lane, create a file under:
`.promptclaw/delegations/YYYY-MM-DD__<lane>__<slug>.md`

Each packet must contain:

- **Mission**
- **Why this lane owns it**
- **Context files to read**
- **Exact deliverable**
- **Constraints**
- **What files to update**
- **What to report back**

## Fallback rules

- If Gemini is unavailable, Claude may do research but must label it as secondary-lane research.
- If Claude is unavailable, Codex may create a practical execution brief for T1/T2 work, but T3 planning should still be treated cautiously.
- If Codex is unavailable, Claude may draft implementation guidance, but repo-changing execution should be handed off when possible.

## Routing note format

When explaining a route, use one short sentence:
- `Route: Gemini — live-doc research and source-grounded summary.`
- `Route: Claude — task needs specification and edge-case framing.`
- `Route: Codex — task is implementation + verification inside the repo.`
