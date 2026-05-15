# PAL 2026 Agentic Operations Platform PRD — Implementation Plan

**Generated:** 2026-05-15T21:42:33.416942+00:00
**Source:** PRD v1.0
**Total tasks:** 45
**Estimated effort:** ~192 hours

---

## Execution Order

Sprints are sequential. Tasks within a sprint can run in parallel unless a dependency is noted.

### Sprint 1: Versioning System

**Depends on:** Sprint 0 (Versioning System)

- **T-001** [T1] Harden `restart_router` for host-managed PAL. (~3h)
- **T-002** [T1] Keep Docker restart as fallback only. (~3h)
- **T-003** [T1] Add fake SSH runner support for PAL tests. (~3h)
- **T-004** [T2] Create PAL source discovery function. (~6h)
- **T-005** [T2] Add deterministic PAL knowledge chunking. (~6h)
- **T-006** [T2] Add PAL knowledge index writer. (~6h)
- **T-007** [T2] Add PAL knowledge query command. (~6h)
- **T-008** [T2] Inject PAL knowledge into workflow prompts. (~6h)
- **T-009** [T2] Add slow-inference context collection. (~6h)
- **T-010** [T2] Add slow-inference diagnosis CLI. (~6h)

*Subtotal: ~51 hours*

### Sprint 2: Quality Scoring

**Depends on:** Sprint 0 (Versioning System), Sprint 1 (Quality Scoring)

- **T-011** [T2] Add Vast connector stub boundary. (~6h) → deps: T-001
- **T-012** [T1] Add Vast secret redaction tests. (~3h) → deps: T-001
- **T-013** [T1] Update architecture documentation. (~3h) → deps: T-001
- **T-014** [T1] Update command reference documentation. (~3h) → deps: T-001

*Subtotal: ~15 hours*

### Sprint 3: Improvement Engine Hardening

**Depends on:** Sprint 0 (Versioning System), Sprint 2 (Improvement Engine Hardening)

- **T-015** [T2] Add restart-validation workflow. (~6h) → deps: T-011
- **T-016** [T2] Add shutdown-audit workflow. (~6h) → deps: T-011
- **T-017** [T2] Add Phase 2 readiness workflow. (~6h) → deps: T-011
- **T-018** [T1] Standardize PAL workflow `run-summary.json`. (~3h) → deps: T-011
- **T-019** [T1] Add PAL workflow artifact verifier. (~3h) → deps: T-011
- **T-020** [T1] Add PAL secret redaction verifier. (~3h) → deps: T-011
- **T-021** [T1] Add PAL escalation artifact helper. (~3h) → deps: T-011
- **T-022** [T2] Create repo-managed PAL deployment manifest. (~6h) → deps: T-011
- **T-023** [T2] Implement deploy diff model. (~6h) → deps: T-011
- **T-024** [T2] Implement deploy-plan CLI. (~6h) → deps: T-011

*Subtotal: ~48 hours*

### Sprint 4: Public REST API

**Depends on:** Sprint 0 (Versioning System), Sprint 2 (Improvement Engine Hardening), Sprint 3 (Public REST API)

- **T-025** [T1] Update PAL project guide. (~3h) → deps: T-011, T-015
- **T-026** [T2] Add fake-client CLI tests for PAL workflows. (~6h) → deps: T-011, T-015
- **T-027** [T1] Add opt-in live PAL verification marker or script. (~3h) → deps: T-011, T-015
- **T-028** [T1] Document live PAL verification commands. (~3h) → deps: T-011, T-015
- **T-029** [T1] Create SDP handoff page. (~3h) → deps: T-011, T-015
- **T-030** [T1] Update changelog for PAL agentic ops. (~3h) → deps: T-011, T-015

*Subtotal: ~21 hours*

### Sprint 5: Library & CRUD Polish

**Depends on:** Sprint 0 (Versioning System), Sprint 1 (Quality Scoring)

- **T-031** [T1] Document the current PAL product surface. (~3h) → deps: T-001
- **T-032** [T1] Add JSON export for PAL action metadata. (~3h) → deps: T-001
- **T-033** [T1] Add `promptclaw pal agent approve` parser wiring. (~3h) → deps: T-001
- **T-034** [T1] Load saved PAL action plans by run id. (~3h) → deps: T-001
- **T-035** [T1] Reject approvals for actions absent from the saved plan. (~3h) → deps: T-001
- **T-036** [T1] Reject approvals for unknown action ids. (~3h) → deps: T-001
- **T-037** [T1] Execute an approved saved action without a model call. (~3h) → deps: T-001
- **T-038** [T1] Write approval execution artifacts. (~3h) → deps: T-001
- **T-039** [T1] Link approval execution artifacts to the source plan. (~3h) → deps: T-001

*Subtotal: ~27 hours*

### Sprint 6: Stretch Goals

**Depends on:** Sprint 0 (Versioning System)

- **T-040** [T2] Implement deploy backup primitive. (~6h)
- **T-041** [T2] Implement approved deploy-apply CLI. (~6h)
- **T-042** [T2] Implement rollback primitive. (~6h)
- **T-043** [T2] Add `promptclaw pal deploy rollback --approve-rollback`. (~6h)
- **T-044** [T1] Add PAL deployment metadata model. (~3h)
- **T-045** [T1] Add `promptclaw pal cost`. (~3h)

*Subtotal: ~30 hours*

---

## Requirements Coverage

- **MUST requirements:** 39/39 covered
- **SHOULD requirements:** 6 included as stretch

**✓ All MUST requirements covered.**

---

## Critical Path

The critical path runs through: Sprint 0 (Infrastructure) → Sprint 1 (Versioning) → Sprint 2 (Scoring) → Sprint 3 (Improvement) → Sprint 4 (API). Sprint 5 (Polish) can overlap with Sprints 2–4. Sprint 6 (Stretch) is fully deferrable.
