# Prompt Authoring

PromptClaw separates prompts into two layers.

## 1. Control prompts

These prompts tell the orchestrator-facing agent how to make decisions.

Files:

- `prompts/control/routing.md`
- `prompts/control/review.md`
- `prompts/control/summarize.md`

Use control prompts for:

- routing
- ambiguity detection
- summarization
- verification framing

## 2. Agent prompts

These prompts tell each worker agent how to behave.

Files usually include:

- `prompts/agents/codex.md`
- `prompts/agents/claude.md`
- `prompts/agents/gemini.md`

Use agent prompts for:

- strengths and limits
- expected output style
- guardrails
- artifact format

## Wizard interaction

The startup wizard can draft both the starter prompts and the agent prompt files. That gives you a fast first pass, but you should still refine the prompts after a few real runs.

## Good prompt traits

- narrow objective
- explicit output shape
- stable headings
- short rules
- no buried requirements

## Recommended output markers

For verification prompts, require:

- `VERDICT: PASS`
- `VERDICT: PASS_WITH_NOTES`
- `VERDICT: FAIL`

For routing prompts, require JSON with fields:

- `ambiguous`
- `clarification_question`
- `lead_agent`
- `verifier_agent`
- `reason`
- `subtask_brief`
- `task_type`
- `confidence`

## Anti-patterns

- making every prompt do everything
- hiding routing rules in agent prompts
- asking agents to decide without listing available agents
- relying on unstated memory
- letting one agent write and verify the same thing by default
