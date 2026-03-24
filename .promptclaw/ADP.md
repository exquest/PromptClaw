# Agent Development Protocol (ADP) v3.0

**Effective:** February 2026
**Scope:** All AI coding agent work across project repositories

## 1. Purpose

This protocol governs how AI coding agents produce code for software projects. It exists to prevent common failure modes of agent-generated code — circular test validation, spec drift, hallucinated dependencies, convention conflicts, and context degradation — while enabling agents to execute autonomously with minimal human interruption.

The protocol is enforced through:
1. Agent instruction files
2. Automated quality gates
3. Human review at defined boundaries

## 2. Task Classification

Classify every coding task before work begins.

### Tier 1 — Light
Bug fixes with known root cause, typo corrections, config changes, dependency bumps, formatting/linting fixes, and missing tests.

Phases:
Implement → Verify → Commit

### Tier 2 — Standard
New features in one module, moderate refactors, new endpoints, UI changes, or pattern-following integrations.

Phases:
Explore → Specify → Test → Implement → Verify → Document → Commit

### Tier 3 — Full
Architectural changes, new external integrations, security-sensitive code, multi-component changes, and schema-altering migrations.

Phases:
Pre-Flight Interview → Explore → Specify → Test → Implement → Security Review → Verify → Document → Commit

## 3. Core Rules

- When in doubt, choose the higher tier.
- T3 planning and execution must be separate sessions.
- No code may be written during Explore.
- Every T2/T3 spec must include machine-verifiable acceptance criteria with VERIFY commands.
- Tests for T2/T3 are written before implementation.
- Locked tests must not have assertions changed during implementation.
- Use explicit scope boundaries: ALWAYS DO / ASK FIRST / NEVER DO.
- Prefer standard library, then existing dependencies, then well-established packages.
- Never fabricate package names.
- Log ambiguity, new dependencies, test disputes, security findings, and spec questions to `ESCALATIONS.md`.
- Commit often. Use conventional commit style.
- Preserve a paper trail in `progress.md` and `SESSION_NOTES.md`.

## 4. Minimum Gate Expectations

### Gate 1 — Spec Completeness
- acceptance criteria present
- VERIFY commands present
- no TBD / TODO / PLACEHOLDER text
- scope boundaries present

### Gate 2 — Test Readiness
- tests compile
- tests fail before implementation
- every acceptance criterion maps to at least one test
- tests are locked after the red phase

### Gate 3 — Implementation Quality
- tests pass
- coverage does not decrease when coverage tooling exists
- lint and type checks pass when configured
- no debug prints
- no secrets
- locked tests remain intact

### Gate 4 — Documentation Completeness
- public changes documented
- README / CHANGELOG / session notes updated when relevant

## 5. Autonomy Model

### Always act
- file operations within scope
- approach decisions
- running tools
- phase transitions
- git commits
- interpreting ambiguity with best effort

### Log and continue
- new dependencies
- test disputes
- spec questions
- security findings
- architectural concerns

### Never do
- modify locked tests
- add unverified dependencies
- commit secrets
- push to main
- modify files outside scope
- force-push

## 6. Recovery

- Stuck after multiple failed approaches: revert to last passing state, log, move on.
- If behavior seems wrong but tests pass: log escalation and continue other work.
- If context degrades: commit passing state, update progress, note a fresh session is needed.

## 7. PromptClaw Execution Notes

PromptClaw must:
- classify tier first
- route specification-heavy work to Claude by default
- route implementation-heavy work to Codex by default
- route current-info research to Gemini by default
- create delegation packets when the active lane is not the best owner
- update the journal, backlog, and state after meaningful work
