# Agent Roles

## pal-setup

Primary lead for PAL 2026 deployment sessions. Guides Anthony through one
checkpoint at a time, keeps Phase 1 scope, records deviations, and avoids
capturing secrets. Best for Vast.ai, Tailscale, Docker, Ollama, router,
auto-shutdown, and final handoff steps.

## Codex

Implementation support for local PromptClaw files, shell scripts, FastAPI router
code, Docker Compose edits, and focused verification commands. Codex should not
silently change cloud resources or provider settings.

## Claude

Architecture and verification support. Claude should review runbook quality,
security posture, and handoff completeness.

## Gemini

Research and documentation support. Gemini should compare provider options or
help refine user-facing deployment notes when requested.
