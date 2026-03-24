# Build Your Own PromptClaw

```text
 /\_/\\
( o.o )  build mode 🧱✨
 > ^ <
```

This is the fastest path from “I have an idea” to “I have an orchestrated claw.”

## The bootstrap contract

PromptClaw still bootstraps from these three markdown files:

1. `prompts/00-project-vision.md`
2. `prompts/01-agent-roles.md`
3. `prompts/02-routing-rules.md`

The difference in v2.1 is that you no longer have to fill those manually unless you want to. The startup wizard can write them for you.

## Fast path

### Step 1 — Initialize

```bash
promptclaw init my-claw --name "Music Ops Claw"
cd my-claw
```

In an interactive shell, the wizard starts automatically.

### Step 2 — Answer the wizard

The wizard asks one question at a time about:

- what the claw is for
- what tasks matter most
- what outputs it should produce
- which agents are on the team
- how routing should work
- what counts as ambiguity
- what the claw must never do

If your answers are vague, it asks targeted follow-ups.

### Step 3 — Review the generated startup files

After the wizard, inspect:

- `docs/STARTUP_PROFILE.md`
- `docs/STARTUP_TRANSCRIPT.md`
- `prompts/00-project-vision.md`
- `prompts/01-agent-roles.md`
- `prompts/02-routing-rules.md`

You can edit any of them directly.

### Step 4 — Test the local project in mock mode

```bash
promptclaw doctor .
promptclaw bootstrap .
promptclaw run . --task-file examples/tasks/sample-task.md
```

This proves the state flow, artifacts, and handoff structure.

### Step 5 — Switch to live agents

Edit `promptclaw.json`:

- change agent `kind` from `mock` to `command`
- add the exact local command used on your machine
- keep `capabilities` and `instruction_file` accurate

Then rerun:

```bash
promptclaw doctor .
promptclaw bootstrap .
```

## Manual path

If you prefer to skip the wizard:

```bash
promptclaw init my-claw --name "Music Ops Claw" --no-wizard
cd my-claw
```

Then edit the three bootstrap prompts yourself.

## The self-build pattern

Once configured, the intended pattern is:

1. user provides startup answers or starter prompts
2. orchestrator turns them into a bootstrap task
3. control plane routes that task to the best available agents
4. artifacts are created for the custom claw
5. user reviews outputs and refines routing if needed

## What gets generated over time

A healthy claw gradually builds:

- better agent instructions
- richer routing prompts
- stronger verification prompts
- project-specific docs
- durable memory
- reusable example tasks

## Recommended conventions

- Keep prompts small and explicit.
- Put system-level rules in markdown, not code, whenever possible.
- Keep agent-specific instructions separate from routing instructions.
- Store all reasoning handoffs as files.
- Let the orchestrator own execution order.
- Let agents own the content of the work.
- Use the wizard again when the claw’s purpose changes materially.

## Minimal manual bootstrap prompt example

### `prompts/00-project-vision.md`

```md
Build an orchestration claw for software, research, and writing tasks.
Use content-based routing.
Ask the user questions only when the task blocks execution.
Store all handoffs as markdown files.
```

### `prompts/01-agent-roles.md`

```md
Codex: implementation, refactors, test fixes
Claude: architecture, specification, review
Gemini: research, documentation, synthesis
```

### `prompts/02-routing-rules.md`

```md
If the task is code-heavy, prefer Codex as lead.
If the task is architecture-heavy, prefer Claude as lead.
If the task is research-heavy, prefer Gemini as lead.
Use a different verifier unless only one agent is available.
If requirements are missing, ask a blocking clarification question.
```
