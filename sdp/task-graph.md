# PAL 2026 Agentic Operations Platform PRD — Task Graph

**Generated:** 2026-05-15T21:42:33.416942+00:00
**Total tasks:** 45
**Estimated effort:** ~192 hours

---

## Sprint 1 — Versioning System

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 1 | T-001 | Harden `restart_router` for host-managed PAL. | T1 | 2 | 3 | PAL-010 | — | Unit test verifies `/opt/pal/scripts/start_router.sh` is preferred. |
| 2 | T-002 | Keep Docker restart as fallback only. | T1 | 2 | 3 | PAL-011 | — | Unit test verifies Docker is selected only when host script is absent. |
| 3 | T-003 | Add fake SSH runner support for PAL tests. | T1 | 2 | 3 | PAL-012 | — | Tests run remote-action code without a real SSH connection. |
| 4 | T-004 | Create PAL source discovery function. | T2 | 2 | 6 | PAL-013 | — | Test returns configured sample files. |
| 5 | T-005 | Add deterministic PAL knowledge chunking. | T2 | 2 | 6 | PAL-014 | — | Test proves stable chunk ids for unchanged input files. |
| 6 | T-006 | Add PAL knowledge index writer. | T2 | 2 | 6 | PAL-015 | — | `pal kb build` creates `.promptclaw/pal-kb/index.jsonl` or SQLite equivalent. |
| 7 | T-007 | Add PAL knowledge query command. | T2 | 2 | 6 | PAL-016 | — | Query returns ranked snippets with source paths. |
| 8 | T-008 | Inject PAL knowledge into workflow prompts. | T2 | 2 | 6 | PAL-017 | — | Prompt artifact includes a bounded `Knowledge Context` section. |
| 9 | T-009 | Add slow-inference context collection. | T2 | 2 | 6 | PAL-018 | — | Workflow captures health, baseline token/s, GPU hints, and logs when available. |
| 10 | T-010 | Add slow-inference diagnosis CLI. | T2 | 2 | 6 | PAL-019 | — | Command writes a diagnosis run artifact and performs no mutation. |

**Sprint 1 total:** ~51 hrs

---

## Sprint 2 — Quality Scoring

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 11 | T-011 | Add Vast connector stub boundary. | T2 | 2 | 6 | PAL-036 | T-001 | No rent/destroy/start/stop action is callable by default. |
| 12 | T-012 | Add Vast secret redaction tests. | T1 | 2 | 3 | PAL-037 | T-001 | Tests reject persisted Vast API key values. |
| 13 | T-013 | Update architecture documentation. | T1 | 2 | 3 | PAL-038 | T-001 | Docs include a PAL platform section. |
| 14 | T-014 | Update command reference documentation. | T1 | 4 | 3 | PAL-039 | T-001 | Docs list all new `promptclaw pal` commands. |

**Sprint 2 total:** ~15 hrs

---

## Sprint 3 — Improvement Engine Hardening

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 15 | T-015 | Add restart-validation workflow. | T2 | 2 | 6 | PAL-020 | T-011 | Command runs health, direct query, smoke, Tailscale, and process checks. |
| 16 | T-016 | Add shutdown-audit workflow. | T2 | 2 | 6 | PAL-021 | T-011 | Summary states shutdown enabled state, override state, and next shutdown window. |
| 17 | T-017 | Add Phase 2 readiness workflow. | T2 | 2 | 6 | PAL-022 | T-011 | Report scores each prerequisite and exposes no Phase 2 execution action. |
| 18 | T-018 | Standardize PAL workflow `run-summary.json`. | T1 | 2 | 3 | PAL-023 | T-011 | Every workflow writes required workflow/status/tool/action keys. |
| 19 | T-019 | Add PAL workflow artifact verifier. | T1 | 2 | 3 | PAL-024 | T-011 | Test fails a run missing required artifacts. |
| 20 | T-020 | Add PAL secret redaction verifier. | T1 | 2 | 3 | PAL-025 | T-011 | Test fails artifacts containing `PAL_SSH_KEY` or token-like values. |
| 21 | T-021 | Add PAL escalation artifact helper. | T1 | 2 | 3 | PAL-026 | T-011 | Missing SSH env and pending approval write `summary/escalation.md`. |
| 22 | T-022 | Create repo-managed PAL deployment manifest. | T2 | 2 | 6 | PAL-027 | T-011 | Manifest lists intended `/opt/pal` files and contains no secrets. |
| 23 | T-023 | Implement deploy diff model. | T2 | 2 | 6 | PAL-028 | T-011 | Fake remote test reports diff sets. |
| 24 | T-024 | Implement deploy-plan CLI. | T2 | 2 | 6 | PAL-029 | T-011 | Command prints plan with no remote writes. |

**Sprint 3 total:** ~48 hrs

---

## Sprint 4 — Public REST API

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 25 | T-025 | Update PAL project guide. | T1 | 2 | 3 | PAL-040 | T-011, T-015 | `pal-2026/docs/PROJECT_GUIDE.md` names the new operator loop. |
| 26 | T-026 | Add fake-client CLI tests for PAL workflows. | T2 | 2 | 6 | PAL-041 | T-011, T-015 | Tests cover kb, approve, workflow, and deploy-plan commands. |
| 27 | T-027 | Add opt-in live PAL verification marker or script. | T1 | 2 | 3 | PAL-042 | T-011, T-015 | Default test run skips live checks. |
| 28 | T-028 | Document live PAL verification commands. | T1 | 2 | 3 | PAL-043 | T-011, T-015 | Handoff lists health, smoke, triage, proposal-only, and read-only action checks. |
| 29 | T-029 | Create SDP handoff page. | T1 | 2 | 3 | PAL-044 | T-011, T-015 | Page lists analyze and run-loop commands. |
| 30 | T-030 | Update changelog for PAL agentic ops. | T1 | 2 | 3 | PAL-045 | T-011, T-015 | Changelog entry names approval replay, KB, workflows, and deploy plan. |

**Sprint 4 total:** ~21 hrs

---

## Sprint 5 — Library & CRUD Polish

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 31 | T-031 | Document the current PAL product surface. | T1 | 2 | 3 | PAL-001 | T-001 | Docs list PAL commands, modules, artifacts, and host-managed `/opt/pal` layout. |
| 32 | T-032 | Add JSON export for PAL action metadata. | T1 | 2 | 3 | PAL-002 | T-001 | Test reads every action id with mutating and approval fields. |
| 33 | T-033 | Add `promptclaw pal agent approve` parser wiring. | T1 | 2 | 3 | PAL-003 | T-001 | CLI help shows `approve PROJECT_ROOT --run-id --action`. |
| 34 | T-034 | Load saved PAL action plans by run id. | T1 | 2 | 3 | PAL-004 | T-001 | Test loads `outputs/action-results.json` from a fixture run. |
| 35 | T-035 | Reject approvals for actions absent from the saved plan. | T1 | 2 | 3 | PAL-005 | T-001 | CLI returns nonzero and writes no execution artifact. |
| 36 | T-036 | Reject approvals for unknown action ids. | T1 | 2 | 3 | PAL-006 | T-001 | Test proves unknown ids never reach the action runner. |
| 37 | T-037 | Execute an approved saved action without a model call. | T1 | 2 | 3 | PAL-007 | T-001 | Fake PAL client records zero `query()` calls during replay. |
| 38 | T-038 | Write approval execution artifacts. | T1 | 2 | 3 | PAL-008 | T-001 | Artifact contains action id, status, timestamp, and redacted command output. |
| 39 | T-039 | Link approval execution artifacts to the source plan. | T1 | 2 | 3 | PAL-009 | T-001 | Artifact stores source run id and source action-plan path. |

**Sprint 5 total:** ~27 hrs

---

## Sprint 6 — Stretch Goals

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 40 | T-040 | Implement deploy backup primitive. | T2 | 2 | 6 | PAL-030 | — | Fake remote test stores changed files. |
| 41 | T-041 | Implement approved deploy-apply CLI. | T2 | 2 | 6 | PAL-031 | — | Fake remote test requires approval flag. |
| 42 | T-042 | Implement rollback primitive. | T2 | 2 | 6 | PAL-032 | — | Fake remote test restores backed-up files. |
| 43 | T-043 | Add `promptclaw pal deploy rollback --approve-rollback`. | T2 | 2 | 6 | PAL-033 | — | Command refuses rollback without approval flag. |
| 44 | T-044 | Add PAL deployment metadata model. | T1 | 2 | 3 | PAL-034 | — | Metadata stores hourly rate, runtime estimate, and optional Vast instance id. |
| 45 | T-045 | Add `promptclaw pal cost`. | T1 | 2 | 3 | PAL-035 | — | Command prints hourly, daily, and monthly burn estimates. |

**Sprint 6 total:** ~30 hrs

---

## Summary

- **Sprint 1 (Versioning System):** 10 tasks, ~51 hrs
- **Sprint 2 (Quality Scoring):** 4 tasks, ~15 hrs
- **Sprint 3 (Improvement Engine Hardening):** 10 tasks, ~48 hrs
- **Sprint 4 (Public REST API):** 6 tasks, ~21 hrs
- **Sprint 5 (Library & CRUD Polish):** 9 tasks, ~27 hrs
- **Sprint 6 (Stretch Goals):** 6 tasks, ~30 hrs

**Total: 45 tasks, ~192 hours**
