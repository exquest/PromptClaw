# Requirements Register — PAL 2026 Agentic Operations Platform PRD

**Extracted:** 2026-05-15T21:42:33.417472+00:00
**Total requirements:** 45

| ID | Description | Priority | Tier | Section |
|----|-------------|----------|------|---------|
| PAL-001 | Document the current PAL product surface. | MUST | T1 |  |
| PAL-002 | Add JSON export for PAL action metadata. | MUST | T1 |  |
| PAL-003 | Add `promptclaw pal agent approve` parser wiring. | MUST | T1 |  |
| PAL-004 | Load saved PAL action plans by run id. | MUST | T1 |  |
| PAL-005 | Reject approvals for actions absent from the saved plan. | MUST | T1 |  |
| PAL-006 | Reject approvals for unknown action ids. | MUST | T1 |  |
| PAL-007 | Execute an approved saved action without a model call. | MUST | T1 |  |
| PAL-008 | Write approval execution artifacts. | MUST | T1 |  |
| PAL-009 | Link approval execution artifacts to the source plan. | MUST | T1 |  |
| PAL-010 | Harden `restart_router` for host-managed PAL. | MUST | T1 |  |
| PAL-011 | Keep Docker restart as fallback only. | MUST | T1 |  |
| PAL-012 | Add fake SSH runner support for PAL tests. | MUST | T1 |  |
| PAL-013 | Create PAL source discovery function. | MUST | T2 |  |
| PAL-014 | Add deterministic PAL knowledge chunking. | MUST | T2 |  |
| PAL-015 | Add PAL knowledge index writer. | MUST | T2 |  |
| PAL-016 | Add PAL knowledge query command. | MUST | T2 |  |
| PAL-017 | Inject PAL knowledge into workflow prompts. | MUST | T2 |  |
| PAL-018 | Add slow-inference context collection. | MUST | T2 |  |
| PAL-019 | Add slow-inference diagnosis CLI. | MUST | T2 |  |
| PAL-020 | Add restart-validation workflow. | MUST | T2 |  |
| PAL-021 | Add shutdown-audit workflow. | MUST | T2 |  |
| PAL-022 | Add Phase 2 readiness workflow. | MUST | T2 |  |
| PAL-023 | Standardize PAL workflow `run-summary.json`. | MUST | T1 |  |
| PAL-024 | Add PAL workflow artifact verifier. | MUST | T1 |  |
| PAL-025 | Add PAL secret redaction verifier. | MUST | T1 |  |
| PAL-026 | Add PAL escalation artifact helper. | MUST | T1 |  |
| PAL-027 | Create repo-managed PAL deployment manifest. | MUST | T2 |  |
| PAL-028 | Implement deploy diff model. | MUST | T2 |  |
| PAL-029 | Implement deploy-plan CLI. | MUST | T2 |  |
| PAL-030 | Implement deploy backup primitive. | SHOULD | T2 |  |
| PAL-031 | Implement approved deploy-apply CLI. | SHOULD | T2 |  |
| PAL-032 | Implement rollback primitive. | SHOULD | T2 |  |
| PAL-033 | Add `promptclaw pal deploy rollback --approve-rollback`. | SHOULD | T2 |  |
| PAL-034 | Add PAL deployment metadata model. | SHOULD | T1 |  |
| PAL-035 | Add `promptclaw pal cost`. | SHOULD | T1 |  |
| PAL-036 | Add Vast connector stub boundary. | MUST | T2 |  |
| PAL-037 | Add Vast secret redaction tests. | MUST | T1 |  |
| PAL-038 | Update architecture documentation. | MUST | T1 |  |
| PAL-039 | Update command reference documentation. | MUST | T1 |  |
| PAL-040 | Update PAL project guide. | MUST | T1 |  |
| PAL-041 | Add fake-client CLI tests for PAL workflows. | MUST | T2 |  |
| PAL-042 | Add opt-in live PAL verification marker or script. | MUST | T1 |  |
| PAL-043 | Document live PAL verification commands. | MUST | T1 |  |
| PAL-044 | Create SDP handoff page. | MUST | T1 |  |
| PAL-045 | Update changelog for PAL agentic ops. | MUST | T1 |  |