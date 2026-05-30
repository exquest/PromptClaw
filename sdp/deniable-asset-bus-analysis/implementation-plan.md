# Deniable Asset Bus — Producer Side PRD — Implementation Plan

**Generated:** 2026-05-30T00:27:30.964206+00:00
**Source:** PRD v1.0
**Total tasks:** 23
**Estimated effort:** ~84 hours

---

## Execution Order

Sprints are sequential. Tasks within a sprint can run in parallel unless a dependency is noted.

### Sprint 0: Infrastructure & Billing

- **T-001** [T1] Path-bearing request fields are sanitized; produced files always land under `deliverables/<request_id>/`; path traversal and absolute paths are rejected. (~3h)
- **T-002** [T1] Render arguments derived from request fields are passed as argv only; shell metacharacters are not interpreted. (~3h)
- **T-003** [T1] Bounded work: per-request ceilings on image count, music duration, and total output bytes; requests over a ceiling return `error`. (~3h)

*Subtotal: ~9 hours*

### Sprint 1: Versioning System

**Depends on:** Sprint 0 (Infrastructure & Billing)

- **T-004** [T1] `store.py` resolves the bus root from `$DENIABLE_ASSET_BUS` (default `~/deniable-asset-bus`) and lists pending requests (those with no result manifest). (~3h) → deps: T-001
- **T-005** [T1] All manifest and produced-file writes are atomic (`*.tmp` then `os.replace`). (~3h) → deps: T-001
- **T-006** [T1] `store.py` computes `sha256` and byte size per produced asset and records bus-root-relative paths in the manifest. (~3h) → deps: T-001
- **T-007** [T1] Re-processing a `request_id` that already has a result manifest is a no-op. (~3h) → deps: T-001

*Subtotal: ~12 hours*

### Sprint 2: Quality Scoring

**Depends on:** Sprint 0 (Infrastructure & Billing), Sprint 1 (Versioning System)

- **T-008** [T1] `runner.py` defines a `BoxRunner` protocol with a `FakeBoxRunner` returning configured artifacts and exit status; no real SSH in unit tests. (~3h) → deps: T-001, T-004
- **T-009** [T2] `SSHBoxRunner` builds its remote command as an argv list and transfers output files back; no request-derived string is interpolated into a shell command. (~6h) → deps: T-001, T-004

*Subtotal: ~9 hours*

### Sprint 3: Improvement Engine Hardening

**Depends on:** Sprint 0 (Infrastructure & Billing), Sprint 2 (Quality Scoring)

- **T-010** [T1] `capabilities.py` is the single source of truth: image=supported, music=supported, sfx=experimental, voiceover=deferred. (~3h) → deps: T-001, T-008
- **T-011** [T1] A `voiceover` request yields a `deferred` manifest with explanatory `notes` and no renderer call; the same `request_id` can be fulfilled later. (~3h) → deps: T-001, T-008
- **T-012** [T1] Routing dispatches each request to the renderer named by the capability matrix for its `asset_type`. (~3h) → deps: T-001, T-008

*Subtotal: ~9 hours*

### Sprint 4: Public REST API

**Depends on:** Sprint 0 (Infrastructure & Billing), Sprint 2 (Quality Scoring), Sprint 3 (Improvement Engine Hardening)

- **T-013** [T2] `producer.py` processes all pending requests in one pass, writing one manifest per request, never aborting the batch on a single failure. (~6h) → deps: T-001, T-008, T-010
- **T-014** [T1] On renderer/runner failure write an `error` manifest with the reason; on partial success write `partial`. (~3h) → deps: T-001, T-008, T-010
- **T-015** [T2] A continuous `run` mode polls the bus on an interval and processes newly arrived requests. (~6h) → deps: T-001, T-008, T-010

*Subtotal: ~15 hours*

### Sprint 5: Model Comparison Hardening

**Depends on:** Sprint 0 (Infrastructure & Billing), Sprint 1 (Versioning System)

- **T-016** [T1] `promptclaw/asset_bus/schema.py` defines request and manifest models matching `docs/deniable-asset-bus-spec.md` v0.1. (~3h) → deps: T-001, T-004
- **T-017** [T1] `validate_request()` accepts conforming requests and rejects malformed ones with specific errors; unknown extra fields are ignored. (~3h) → deps: T-001, T-004
- **T-018** [T1] `promptclaw asset-bus validate --request FILE` validates one request file and prints the normalized result or the validation error. (~3h) → deps: T-001, T-004
- **T-019** [T1] `promptclaw asset-bus once` processes every pending request and writes its deliverable and manifest. (~3h) → deps: T-001, T-004
- **T-020** [T1] `promptclaw asset-bus run` runs the continuous loop; `promptclaw asset-bus doctor` reports bus paths, configured runner, and capability matrix without doing work. (~3h) → deps: T-001, T-004

*Subtotal: ~15 hours*

### Sprint 6: Stretch Goals

**Depends on:** Sprint 0 (Infrastructure & Billing)

- **T-021** [T2] `tools/asset_render_image.py` accepts prompt/size/seed/count args and writes PNG(s) to an output directory. (~6h) → deps: T-001
- **T-022** [T2] `tools/asset_render_music.py` accepts mood/scene/duration/loopable args and writes a WAV to an output path; the documented contract is exercised in-repo via `FakeBoxRunner`. (~6h) → deps: T-001
- **T-023** [T1] `docs/deniable-asset-bus-spec.md` gains a "Producer (CypherClaw side)" section. (~3h) → deps: T-001

*Subtotal: ~15 hours*

---

## Requirements Coverage

- **MUST requirements:** 20/20 covered
- **SHOULD requirements:** 3 included as stretch

**✓ All MUST requirements covered.**

---

## Critical Path

The critical path runs through: Sprint 0 (Infrastructure) → Sprint 1 (Versioning) → Sprint 2 (Scoring) → Sprint 3 (Improvement) → Sprint 4 (API). Sprint 5 (Polish) can overlap with Sprints 2–4. Sprint 6 (Stretch) is fully deferrable.
