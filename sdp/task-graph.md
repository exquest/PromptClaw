# Deniable Asset Bus — Producer Side PRD — Task Graph

**Generated:** 2026-05-30T00:28:46.953089+00:00
**Total tasks:** 23
**Estimated effort:** ~84 hours

---

## Sprint 0 — Infrastructure & Billing

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 1 | T-001 | Path-bearing request fields are sanitized; produced files always land under `deliverables/<request_id>/`; path traversal and absolute paths are rejected. | T1 | 5 | 3 | DAB-070 | — | Test with `../` and an absolute `target_path` is rejected; output stays inside the sandbox dir. |
| 2 | T-002 | Render arguments derived from request fields are passed as argv only; shell metacharacters are not interpreted. | T1 | 3 | 3 | DAB-071 | — | An injection fixture in a prompt is passed literally and not interpreted. |
| 3 | T-003 | Bounded work: per-request ceilings on image count, music duration, and total output bytes; requests over a ceiling return `error`. | T1 | 4 | 3 | DAB-072 | — | Over-limit fixtures produce an `error` manifest stating the exceeded ceiling. |

**Sprint 0 total:** ~9 hrs

---

## Sprint 1 — Versioning System

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 4 | T-004 | `store.py` resolves the bus root from `$DENIABLE_ASSET_BUS` (default `~/deniable-asset-bus`) and lists pending requests (those with no result manifest). | T1 | 4 | 3 | DAB-010 | T-001 | Unit test over a temp bus lists exactly the unfulfilled request ids. |
| 5 | T-005 | All manifest and produced-file writes are atomic (`*.tmp` then `os.replace`). | T1 | 6 | 3 | DAB-011 | T-001 | Test asserts writes go through a temp path and `os.replace`; no partial file is observable. |
| 6 | T-006 | `store.py` computes `sha256` and byte size per produced asset and records bus-root-relative paths in the manifest. | T1 | 4 | 3 | DAB-012 | T-001 | Test compares recorded `sha256`/`bytes` against known fixture bytes; recorded paths are relative. |
| 7 | T-007 | Re-processing a `request_id` that already has a result manifest is a no-op. | T1 | 3 | 3 | DAB-013 | T-001 | Idempotency test: a second pass performs no render work and does not rewrite the manifest. |

**Sprint 1 total:** ~12 hrs

---

## Sprint 2 — Quality Scoring

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 8 | T-008 | `runner.py` defines a `BoxRunner` protocol with a `FakeBoxRunner` returning configured artifacts and exit status; no real SSH in unit tests. | T1 | 7 | 3 | DAB-030 | T-001, T-004 | All unit tests use `FakeBoxRunner`; no network calls occur. |
| 9 | T-009 | `SSHBoxRunner` builds its remote command as an argv list and transfers output files back; no request-derived string is interpolated into a shell command. | T2 | 4 | 6 | DAB-031 | T-001, T-004 | Test asserts the command is constructed as an argv list and an injection fixture is passed verbatim, never via a shell string. |

**Sprint 2 total:** ~9 hrs

---

## Sprint 3 — Improvement Engine Hardening

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 10 | T-010 | `capabilities.py` is the single source of truth: image=supported, music=supported, sfx=experimental, voiceover=deferred. | T1 | 3 | 3 | DAB-020 | T-001, T-008 | Unit test asserts each matrix value. |
| 11 | T-011 | A `voiceover` request yields a `deferred` manifest with explanatory `notes` and no renderer call; the same `request_id` can be fulfilled later. | T1 | 4 | 3 | DAB-021 | T-001, T-008 | Test: a voiceover request produces status `deferred` and the fake renderer records zero calls. |
| 12 | T-012 | Routing dispatches each request to the renderer named by the capability matrix for its `asset_type`. | T1 | 3 | 3 | DAB-022 | T-001, T-008 | Test asserts image routes to the image renderer and music routes to the music renderer. |

**Sprint 3 total:** ~9 hrs

---

## Sprint 4 — Public REST API

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 13 | T-013 | `producer.py` processes all pending requests in one pass, writing one manifest per request, never aborting the batch on a single failure. | T2 | 6 | 6 | DAB-040 | T-001, T-008, T-010 | Test with a batch containing one failing request: every other request still gets a manifest. |
| 14 | T-014 | On renderer/runner failure write an `error` manifest with the reason; on partial success write `partial`. | T1 | 3 | 3 | DAB-041 | T-001, T-008, T-010 | Tests force failure and partial outcomes and assert the manifest status and reason. |
| 15 | T-015 | A continuous `run` mode polls the bus on an interval and processes newly arrived requests. | T2 | 3 | 6 | DAB-042 | T-001, T-008, T-010 | Test drives one poll iteration via an injected clock and processes a newly added request. |

**Sprint 4 total:** ~15 hrs

---

## Sprint 5 — Model Comparison Hardening

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 16 | T-016 | `promptclaw/asset_bus/schema.py` defines request and manifest models matching `docs/deniable-asset-bus-spec.md` v0.1. | T1 | 4 | 3 | DAB-001 | T-001, T-004 | Models round-trip a fixture request and manifest; field set matches the spec. |
| 17 | T-017 | `validate_request()` accepts conforming requests and rejects malformed ones with specific errors; unknown extra fields are ignored. | T1 | 5 | 3 | DAB-002 | T-001, T-004 | Unit tests: a valid request passes; missing `request_id`/`asset_type`/`spec`, wrong `schema`, and unknown `asset_type` each raise a distinct error; an extra field is tolerated. |
| 18 | T-018 | `promptclaw asset-bus validate --request FILE` validates one request file and prints the normalized result or the validation error. | T1 | 3 | 3 | DAB-050 | T-001, T-004 | CLI test on valid and invalid fixtures asserts the printed output and exit code. |
| 19 | T-019 | `promptclaw asset-bus once` processes every pending request and writes its deliverable and manifest. | T1 | 3 | 3 | DAB-051 | T-001, T-004 | CLI test produces a manifest for each pending request in a temp bus. |
| 20 | T-020 | `promptclaw asset-bus run` runs the continuous loop; `promptclaw asset-bus doctor` reports bus paths, configured runner, and capability matrix without doing work. | T1 | 4 | 3 | DAB-052 | T-001, T-004 | `doctor` test asserts the report content and that no files are written. |

**Sprint 5 total:** ~15 hrs

---

## Sprint 6 — Stretch Goals

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 21 | T-021 | `tools/asset_render_image.py` accepts prompt/size/seed/count args and writes PNG(s) to an output directory. | T2 | 3 | 6 | DAB-060 | T-001 | A smoke test parses the documented argv and asserts the resolved render parameters. |
| 22 | T-022 | `tools/asset_render_music.py` accepts mood/scene/duration/loopable args and writes a WAV to an output path; the documented contract is exercised in-repo via `FakeBoxRunner`. | T2 | 5 | 6 | DAB-061 | T-001 | The arg contract is documented and parsed; the fake runner reproduces it. |
| 23 | T-023 | `docs/deniable-asset-bus-spec.md` gains a "Producer (CypherClaw side)" section. | T1 | 3 | 3 | DAB-080 | T-001 | The section is present and the `schema` version string is unchanged. |

**Sprint 6 total:** ~15 hrs

---

## Summary

- **Sprint 0 (Infrastructure & Billing):** 3 tasks, ~9 hrs
- **Sprint 1 (Versioning System):** 4 tasks, ~12 hrs
- **Sprint 2 (Quality Scoring):** 2 tasks, ~9 hrs
- **Sprint 3 (Improvement Engine Hardening):** 3 tasks, ~9 hrs
- **Sprint 4 (Public REST API):** 3 tasks, ~15 hrs
- **Sprint 5 (Model Comparison Hardening):** 5 tasks, ~15 hrs
- **Sprint 6 (Stretch Goals):** 3 tasks, ~15 hrs

**Total: 23 tasks, ~84 hours**
