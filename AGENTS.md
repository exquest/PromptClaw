# AGENTS.md

This repository is designed to be extended by coding agents.

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
