# Requirements Register — Deniable Asset Bus — Producer Side PRD

**Extracted:** 2026-05-30T00:28:46.953582+00:00
**Total requirements:** 23

| ID | Description | Priority | Tier | Section |
|----|-------------|----------|------|---------|
| DAB-001 | `promptclaw/asset_bus/schema.py` defines request and manifest models matching `docs/deniable-asset-bus-spec.md` v0.1. | MUST | T1 |  |
| DAB-002 | `validate_request()` accepts conforming requests and rejects malformed ones with specific errors; unknown extra fields are ignored. | MUST | T1 |  |
| DAB-010 | `store.py` resolves the bus root from `$DENIABLE_ASSET_BUS` (default `~/deniable-asset-bus`) and lists pending requests (those with no result manifest). | MUST | T1 |  |
| DAB-011 | All manifest and produced-file writes are atomic (`*.tmp` then `os.replace`). | MUST | T1 |  |
| DAB-012 | `store.py` computes `sha256` and byte size per produced asset and records bus-root-relative paths in the manifest. | MUST | T1 |  |
| DAB-013 | Re-processing a `request_id` that already has a result manifest is a no-op. | MUST | T1 |  |
| DAB-020 | `capabilities.py` is the single source of truth: image=supported, music=supported, sfx=experimental, voiceover=deferred. | MUST | T1 |  |
| DAB-021 | A `voiceover` request yields a `deferred` manifest with explanatory `notes` and no renderer call; the same `request_id` can be fulfilled later. | MUST | T1 |  |
| DAB-022 | Routing dispatches each request to the renderer named by the capability matrix for its `asset_type`. | MUST | T1 |  |
| DAB-030 | `runner.py` defines a `BoxRunner` protocol with a `FakeBoxRunner` returning configured artifacts and exit status; no real SSH in unit tests. | MUST | T1 |  |
| DAB-031 | `SSHBoxRunner` builds its remote command as an argv list and transfers output files back; no request-derived string is interpolated into a shell command. | MUST | T2 |  |
| DAB-040 | `producer.py` processes all pending requests in one pass, writing one manifest per request, never aborting the batch on a single failure. | MUST | T2 |  |
| DAB-041 | On renderer/runner failure write an `error` manifest with the reason; on partial success write `partial`. | MUST | T1 |  |
| DAB-042 | A continuous `run` mode polls the bus on an interval and processes newly arrived requests. | MUST | T2 |  |
| DAB-050 | `promptclaw asset-bus validate --request FILE` validates one request file and prints the normalized result or the validation error. | MUST | T1 |  |
| DAB-051 | `promptclaw asset-bus once` processes every pending request and writes its deliverable and manifest. | MUST | T1 |  |
| DAB-052 | `promptclaw asset-bus run` runs the continuous loop; `promptclaw asset-bus doctor` reports bus paths, configured runner, and capability matrix without doing work. | MUST | T1 |  |
| DAB-060 | `tools/asset_render_image.py` accepts prompt/size/seed/count args and writes PNG(s) to an output directory. | SHOULD | T2 |  |
| DAB-061 | `tools/asset_render_music.py` accepts mood/scene/duration/loopable args and writes a WAV to an output path; the documented contract is exercised in-repo via `FakeBoxRunner`. | SHOULD | T2 |  |
| DAB-070 | Path-bearing request fields are sanitized; produced files always land under `deliverables/<request_id>/`; path traversal and absolute paths are rejected. | MUST | T1 |  |
| DAB-071 | Render arguments derived from request fields are passed as argv only; shell metacharacters are not interpreted. | MUST | T1 |  |
| DAB-072 | Bounded work: per-request ceilings on image count, music duration, and total output bytes; requests over a ceiling return `error`. | MUST | T1 |  |
| DAB-080 | `docs/deniable-asset-bus-spec.md` gains a "Producer (CypherClaw side)" section. | SHOULD | T1 |  |