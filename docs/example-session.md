# Example Session

## Project creation

```bash
promptclaw init my-claw --name "My Claw"
cd my-claw
```

## Wizard vibe

```text
 /\_/\\
( o.o )  PromptClaw Startup Wizard 🦀✨🎉
 > ^ <
```

The wizard then asks one question at a time.

Example:

```text
Question 1 🪄
What kind of PromptClaw are we building?
Hint: Name the domain, mission, and what makes this claw useful.
```

A vague answer can trigger a follow-up such as:

```text
Follow-up sparkle ✨
Name the top 3 task families that matter most on day one.
```

## Bootstrap

```bash
promptclaw doctor .
promptclaw bootstrap .
```

## Run

```bash
promptclaw run . --task "Analyze this feature request, choose the best agent, and produce a plan."
```

## Result layout

```text
.promptclaw/runs/20260313-120001-example/
├── input/task.md
├── routing/route.json
├── routing/route.md
├── prompts/lead-claude.md
├── outputs/lead-claude.md
├── handoffs/lead-to-verify.md
├── prompts/verify-codex.md
├── outputs/verify-codex.md
├── summary/final-summary.md
└── state.json
```

## Clarification example

If the task is unclear, you might see:

```text
summary/clarification-request.md
```

with content like:

```md
# Clarification Needed

The orchestrator paused because the task is ambiguous.

## Question
Should PromptClaw produce implementation code, a plan, tests, or some combination of those?
```

Resume with:

```bash
promptclaw resume . --run-id <run-id> --answer "Produce code plus tests."
```
