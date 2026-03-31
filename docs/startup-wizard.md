# Startup Wizard

```text
 /\_/\\
( o.o )  startup wizard 🦀✨🎠
 > ^ <
```

PromptClaw v2.1 adds an interactive wizard for creating a new claw.

## What it does

The wizard asks startup questions **one at a time** and translates the answers into:

- starter prompts
- agent instructions
- project description
- enabled agent roster
- capability tags in `promptclaw.json`
- a startup profile and transcript

## How to run it

### Automatically during init

```bash
promptclaw init my-claw --name "My PromptClaw"
```

### Manually later

```bash
promptclaw wizard my-claw
```

## What the wizard asks

Core topics:

- project mission
- task families
- usual outputs
- agent roster
- routing rules
- verification style
- autonomy level
- ambiguity handling
- hard boundaries

## Smart follow-ups

The wizard adds follow-up questions when it detects missing signal.

Examples:

- vague task families → asks for the top 3 priorities
- code-heavy outputs without testing guidance → asks whether code should include tests
- autonomous workflow → asks what still requires approval
- weak ambiguity policy → asks what the first follow-up question should pin down
- vague boundaries → asks for two hard red lines

## Files it writes

- `prompts/00-project-vision.md`
- `prompts/01-agent-roles.md`
- `prompts/02-routing-rules.md`
- `prompts/agents/*.md`
- `docs/STARTUP_PROFILE.md`
- `docs/STARTUP_TRANSCRIPT.md`
- `.promptclaw/onboarding/startup-session.md`
- `promptclaw.json`

## Design notes

- The wizard is **heuristic-first** so it works in mock mode and before live agents are configured.
- Custom agent names are supported; new prompt files are created automatically.
- Agents not selected in the wizard are disabled in `promptclaw.json`.
- When you later switch an agent to live `command` mode, PromptClaw runs it from the project root and fills `{prompt_file}` with an absolute path to the generated prompt artifact.
- CypherClaw live command projects can layer quota-aware routing on top of those rules, redistributing work away from providers with degraded headroom and collapsing to single-agent mode when only one provider remains viable.

## Typical loop

```bash
promptclaw init my-claw --name "Research Claw"
cd my-claw
promptclaw doctor .
promptclaw bootstrap .
promptclaw run . --task "Compare orchestration patterns and propose an implementation plan."
```
