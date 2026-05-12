# Routing Rules

For PAL 2026 cloud deployment work, prefer `pal-setup` as lead.

Use Codex when files, scripts, Docker Compose, FastAPI code, local validation, or
Git operations are involved. Use Claude as verifier for architecture, security,
and handoff quality. Use Gemini only for research or documentation synthesis.

Stay in Phase 1 unless Anthony explicitly asks for Phase 2. Do not execute Phase
2 appendix work by implication.

Ask one question at a time. Ask only for the next blocked checkpoint or required
operator confirmation. Do not re-verify prerequisites Anthony has already
confirmed: funded Vast.ai account, SSH client on MacBook, Tailscale auth token
and admin access, and knowledge of his tailnet name.

If a cloud checkpoint fails, run the troubleshooting block for that phase before
asking Anthony to abandon the path. Record the failure and recovery in
`ops/deviation-log.md`.

Stop cleanly when Anthony pauses. Record the last completed step, current
provider/host state if known, and the next step to resume.
