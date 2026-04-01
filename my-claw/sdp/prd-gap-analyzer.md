# PRD: System Gap Analyzer — Automated Quality Enforcement

## Core Philosophy

No task is done until it's verified working end-to-end. No PRD is complete until all its pieces are integrated and tested together. The Gap Analyzer is the system's quality gate — it catches fake completions, missing integrations, broken dependencies, and untested code before they compound into systemic failures.

**Strict TDD:** Every new module must have tests written BEFORE or alongside the implementation. No code ships without tests. E2E tests verify that components work together, not just in isolation.

## Overview

An automated gap analysis system that runs after every pipeline batch, every 6 hours on schedule, and on-demand via `/gaps` Telegram command. It scans three dimensions (code, infrastructure, integration), verifies task completions are real, and either auto-fixes simple gaps or creates pipeline tasks for complex ones.

**Depends on:** `prd-introspector.md` (shares the verify/scan/fix philosophy), `prd-verification-system.md` (risk classification)

## Design Decisions

1. **Three gap categories** — code gaps (missing files, broken imports), infrastructure gaps (services down, packages missing, config drift), integration gaps (modules exist but aren't wired together)
2. **Triple trigger** — after every pipeline batch completion, every 6 hours on schedule, on-demand via `/gaps`
3. **Auto-fix simple gaps** immediately (missing packages, file sync, service restart), create sdp-cli tasks for complex gaps (new code needed, integration work)
4. **Deep completion verification** — file existence + clean import + behavioral check (key classes/functions callable)
5. **Strict TDD enforcement** — flag any module without corresponding tests as a gap. Flag any test file that doesn't pass.
6. **E2E integration tests** — per-PRD integration test that verifies all components from that PRD work together

## Architecture

```
tools/gap_analyzer.py              # Main analyzer — can run standalone or be called by introspector
tools/gap_analyzer/
├── __init__.py
├── code_scanner.py                # Code gap detection — files, imports, callables
├── infra_scanner.py               # Infrastructure gap detection — services, packages, config
├── integration_scanner.py         # Integration gap detection — wiring between modules
├── completion_verifier.py         # Verify "complete" tasks actually produced working code
├── tdd_enforcer.py                # Check test coverage, flag untested modules
├── e2e_runner.py                  # Run per-PRD end-to-end integration tests
├── reporter.py                    # Generate findings report + Telegram summary
└── auto_fixer.py                  # Fix simple gaps immediately
```

## Requirements

| ID | Description | Tier |
|----|-------------|------|
| GA-001 | Create `tools/gap_analyzer.py` as standalone entry point. Three triggers: (1) called by pipeline watchdog after each batch completes, (2) cron job every 6 hours, (3) `/gaps` Telegram command in daemon. Returns structured findings report. | T1 |
| GA-002 | Create `gap_analyzer/code_scanner.py` — scan all PRDs in `sdp/`, extract file paths and class/function names mentioned in task descriptions, verify each exists on disk. For every "complete" task: check that files referenced in the description exist, import without error, and key classes/functions are callable. Flag as gap if any check fails. | T2 |
| GA-003 | Create `gap_analyzer/infra_scanner.py` — verify infrastructure state matches expectations: (1) all systemd services running (cypherclaw-daemon, cypherclaw-gallery, redis, ollama, nginx), (2) all venv packages installed in BOTH main and workdir venvs, (3) workdir in sync with main codebase (no files in main missing from workdir), (4) all database files exist and are valid SQLite, (5) Ollama models loaded, (6) disk/tmpfs space adequate. | T2 |
| GA-004 | Create `gap_analyzer/integration_scanner.py` — verify cross-module wiring: (1) daemon imports and uses modules it should (observatory, healer, agent_selector, etc.), (2) art pipeline connected end-to-end (art_engine -> gallery/renders/ -> gallery_display), (3) pet system wired into daemon, (4) for each PRD, check that its modules reference each other as specified. Use AST parsing to check imports without executing code. | T2 |
| GA-005 | Create `gap_analyzer/completion_verifier.py` — for every task with status "complete", run tiered verification: (1) file existence — does every file mentioned in the task description exist? (2) import check — does `python -c "import module"` succeed? (3) behavioral check — do the key classes/functions mentioned exist and have the right signatures? Mark tasks that fail verification as "needs_review" with a detailed failure reason. | T2 |
| GA-006 | Create `gap_analyzer/tdd_enforcer.py` — scan `tools/` for all Python modules. For each module, check if a corresponding test file exists in `tests/`. Flag modules without tests as a gap. Run all existing tests and flag failures. Calculate test coverage percentage. Generate a "test debt" report listing untested modules ordered by importance (daemon modules > utility modules). | T2 |
| GA-007 | Create `gap_analyzer/e2e_runner.py` — per-PRD end-to-end integration tests. For each PRD, define a smoke test that exercises the full workflow: (1) Art Studio: call art_engine.generate_art() and verify output file exists in gallery/renders/. (2) Pet System: create a pet, feed it, check stats update. (3) Gallery: verify service running, art directory has files, framebuffer accessible. (4) Narrative Engine: instantiate engine, verify world state DB created. Tests use real local resources (Ollama, SQLite) but mock external APIs (Telegram, cloud agents). | T2 |
| GA-008 | Create `gap_analyzer/reporter.py` — generate structured findings report as JSON + human-readable markdown. Categories: CRITICAL (system broken), WARNING (gap found but system works), INFO (suggestion for improvement). Telegram summary under 300 chars for immediate notification. Full report saved to `sdp/gap-reports/gap_YYYYMMDD_HHMMSS.md`. | T1 |
| GA-009 | Create `gap_analyzer/auto_fixer.py` — immediately fix simple gaps without creating tasks: (1) missing venv package -> pip install, (2) file not synced to workdir -> cp, (3) service not running -> systemctl restart, (4) stale lock file -> rm, (5) missing directory -> mkdir. Log all auto-fixes. Complex gaps (missing code, broken integration) -> create sdp-cli tasks automatically. | T2 |
| GA-010 | Implement the 6-hour cron schedule. Add cron job: `0 */6 * * * /home/user/cypherclaw/.venv/bin/python /home/user/cypherclaw/tools/gap_analyzer.py --scheduled`. Also hook into pipeline_watchdog.sh to run after each batch completion. | T1 |
| GA-011 | Add `/gaps` Telegram command to the daemon. Calls gap_analyzer.py, sends Telegram summary of findings. If auto-fixes were applied, list them. If tasks were created, list them. | T1 |
| GA-012 | Create E2E test suite in `tests/test_e2e_integration.py`. One test per PRD that's marked "complete" in the database. Each test exercises the full workflow for that PRD's feature set. Tests must pass in the gate alongside unit tests. Start with: test_glyphweave_dsl_renders, test_gallery_display_loads, test_pet_system_lifecycle, test_observatory_records. | T2 |
| GA-013 | Implement task auto-creation for complex gaps. When the analyzer finds a gap that needs code (missing module, broken integration), automatically create an sdp-cli task with: description from the gap finding, tier T1 for simple or T2 for complex, reference to the PRD that specified the missing piece. Deduplicate — don't create tasks for gaps that already have pending tasks. | T2 |
| GA-014 | Enforce TDD in the pipeline gate. Update `gate_commands` in `sdp.toml` to include a test coverage check: every new .py file in tools/ added by a task run must have a corresponding test file, or the gate fails. This prevents future fake completions — agents can't mark a task done without tests. | T2 |
