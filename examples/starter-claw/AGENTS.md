# AGENTS.md

This is the single source of truth for all agents working on PromptClaw projects. CLAUDE.md points here. All agents (Claude, Codex, Gemini, local LLMs) read this file.

## Core Tenets

### 1. Test-Driven Development (TDD)
- Write tests BEFORE or ALONGSIDE implementation — never after
- No module ships without corresponding tests
- If fixing a bug, write a failing test first, then fix
- Mock external services in tests

### 2. Verify/Scan/Fix Loop
After every action: verify it worked, scan for side effects, fix anything found, repeat until clean. Never leave broken things behind.

### 3. Read Before You Write
Read existing code and the relevant PRD before modifying anything.

## Working rules

- Prefer the standard library.
- Keep new modules small and typed.
- Treat `README.md` and `docs/` as product-facing documentation.
- Treat `.promptclaw/` as runtime state, not source.
- Do not hardcode provider secrets or agent commands in source files.
- When changing orchestration behavior, update:
  - `docs/architecture.md`
  - `docs/handoff-protocol.md`
  - `docs/command-reference.md`
  - `docs/startup-wizard.md`
  - `CHANGELOG.md`

## Runtime contract

- Handoffs happen through files inside `.promptclaw/runs/<run-id>/`.
- The orchestrator may ask the user questions only when the task is ambiguous.
- Startup onboarding happens through the wizard or the starter prompts.
- Lead and verifier should be different agents whenever possible.
