# PromptClaw v2.1

```text
 /\_/\\
( o.o )  PromptClaw v2.1 🦀✨🎉
 > ^ <   playful startup wizard + smart follow-ups
```

PromptClaw v2.1 is a markdown-first, artifact-driven, multi-agent orchestrator scaffold.

This update adds the onboarding flow you asked for:

- **startup questions one at a time** via an interactive wizard
- **smart follow-up questions** when answers are vague or underspecified
- **playful terminal UX** with ASCII + emoji styling
- richer startup artifacts for building a custom claw faster
- better clarification questions for ambiguous tasks

The orchestrator still keeps the same core model:

- agent selection is based on content need
- handoffs happen through artifacts, not agent-to-agent chat
- state and memory persist across runs
- the user is interrupted only for genuine ambiguity
- the project can self-bootstrap from starter prompts

## Quick start

### 1) Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2) Create a new PromptClaw project

```bash
promptclaw init my-claw --name "My PromptClaw"
cd my-claw
```

In an interactive terminal, `promptclaw init` now launches the startup wizard automatically. The wizard asks one question at a time and writes your answers into the starter prompts.

To skip it:

```bash
promptclaw init my-claw --name "My PromptClaw" --no-wizard
```

To run it later:

```bash
promptclaw wizard .
```

### 3) Let the wizard build your starter prompts

The wizard fills:

- `prompts/00-project-vision.md`
- `prompts/01-agent-roles.md`
- `prompts/02-routing-rules.md`
- `docs/STARTUP_PROFILE.md`
- `docs/STARTUP_TRANSCRIPT.md`

### 4) Decide how to run agents

Generated projects start in **mock mode** so the full orchestration flow is testable immediately.

When you are ready for live agents, edit `promptclaw.json` and switch each agent from `mock` to `command`, then add the exact local command your machine uses to invoke that agent.

### 5) Let the orchestrator bootstrap your custom claw

```bash
promptclaw doctor .
promptclaw bootstrap .
```

That command turns your startup materials into a bootstrap task and runs the orchestrator against it.

### 6) Run real work

```bash
promptclaw run . --task-file examples/tasks/sample-task.md
promptclaw status .
```

## Commands

```bash
promptclaw init PATH [--name NAME] [--no-wizard]
promptclaw wizard PROJECT_ROOT
promptclaw doctor PROJECT_ROOT
promptclaw bootstrap PROJECT_ROOT
promptclaw run PROJECT_ROOT --task-file FILE
promptclaw run PROJECT_ROOT --task "free text task"
promptclaw resume PROJECT_ROOT --run-id RUN_ID --answer "clarification answer"
promptclaw status PROJECT_ROOT [--run-id RUN_ID]
promptclaw show-config PROJECT_ROOT
```

## What is in this repo

```text
promptclaw-v2.1/
├── promptclaw/                     # CLI + runtime + startup wizard
├── docs/                           # manuals
├── examples/
│   ├── starter-claw/               # generated project example
│   └── tasks/                      # sample tasks
├── tests/                          # unit tests
├── README.md
├── AGENTS.md
├── CHANGELOG.md
└── pyproject.toml
```

## Design summary

PromptClaw v2.1 uses these core ideas:

- **artifact-based handoffs**: the orchestrator writes task input, route decisions, handoff briefs, agent prompts, agent outputs, verification reports, clarification requests, and final summaries into a run directory.
- **control plane routing**: the orchestrator can call an agent to choose the best lead/verifier pair, or fall back to a built-in heuristic router if no control-plane agent is configured.
- **startup wizard**: the project can collect requirements one question at a time and translate them into starter prompts and config.
- **resumable runs**: if a task is ambiguous, the run pauses and can be resumed with a clarification answer.
- **memory**: after each run, a summary is appended into `.promptclaw/memory/project-memory.md` and fed back into future routing.
- **bootstrap flow**: the project includes starter prompts and a `bootstrap` command so a user can begin with a few answers and let the orchestrator build the rest.

## Recommended reading order

- `docs/build-your-own-promptclaw.md`
- `docs/startup-wizard.md`
- `docs/architecture.md`
- `docs/handoff-protocol.md`
- `docs/configuration-reference.md`
- `docs/command-reference.md`
- `docs/troubleshooting.md`

## Notes

- The generated project uses mock agents until you wire in live commands.
- The startup wizard is heuristic-first, so it works out of the box without a live LLM.
- All runtime state lives under `.promptclaw/` inside each generated project.
