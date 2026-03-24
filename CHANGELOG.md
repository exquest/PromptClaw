# Changelog

## 2.1.0

- Added an interactive startup wizard that asks onboarding questions one at a time.
- Added heuristic follow-up questions when startup answers are vague or underspecified.
- Added playful terminal styling with ASCII and emoji output for project creation and wizard flows.
- Added startup artifacts: `docs/STARTUP_PROFILE.md`, `docs/STARTUP_TRANSCRIPT.md`, and `.promptclaw/onboarding/startup-session.md`.
- Added agent roster customization and capability inference during startup.
- Improved heuristic clarification questions for ambiguous runtime tasks.
- Updated docs and manuals to reflect the new onboarding flow.

## 2.0.0

- Added an LLM-driven orchestrator control plane with heuristic fallback.
- Added artifact-based handoff flow for lead, verify, and clarification phases.
- Added project bootstrap commands for creating custom PromptClaw projects.
- Added rolling project memory, run state, and resumable clarification flow.
- Added markdown-first docs and starter prompt packs for building new claws.
