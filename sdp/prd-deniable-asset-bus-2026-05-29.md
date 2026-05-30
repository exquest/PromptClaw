# Deniable Asset Bus — Producer Side PRD

**Project:** PromptClaw / Deniable Asset Bus
**Version:** 1.0
**Date:** 2026-05-29
**SDP Protocol:** v1.0
**Primary repo:** `/Users/anthony/Programming/PromptClaw`
**Deploy target:** cypherclaw box at `/home/user/cypherclaw/` (reachable via Tailscale SSH) — render workers only
**Requester contract (frozen):** `docs/deniable-asset-bus-spec.md` (`schema: deniable-asset-bus/v0.1`)

---

## Overview

A sibling agent is building a game, **Deniable**, that needs generated assets — images,
music, voiceover, sfx — produced by CypherClaw. The **requester** contract is already
specified and frozen in `docs/deniable-asset-bus-spec.md`: the Deniable agent writes a JSON
request file to `requests/<request_id>.json` and polls for `deliverables/<request_id>.result.json`.

This PRD covers only the **producer side**: the CypherClaw-side machinery that picks up
requests, generates assets, and writes deliverables + manifests back. The producer must honor
the v0.1 contract exactly, hide its own internals from the requester, and degrade honestly when
a capability is missing (notably voiceover, for which there is no TTS today).

The design keeps a **single canonical bus on the laptop** (where both the Deniable agent and
this orchestrator live). The producer runs as a laptop-side loop that dispatches the actual
GPU/synthesis render to the cypherclaw box over an **injectable runner** (SSH in production, a
fake runner in tests). This mirrors the PAL "fake SSH runner" pattern so the whole producer can
be built and tested in-repo without a live box.

---

## Current State Snapshot

- **Requester contract:** `docs/deniable-asset-bus-spec.md` defines the bus layout
  (`$DENIABLE_ASSET_BUS` default `~/deniable-asset-bus`, with `requests/`, `deliverables/`,
  `status/`), the request JSON (`request_id`, `schema`, `asset_type`, `title`, `format`,
  `target_path`, `priority`, `acceptance`, type-specific `spec`), and the manifest JSON
  (`status` ∈ done|error|partial|deferred, `assets[]` with `path`/`bytes`/`sha256`/`meta`).
- **Package layout:** new code belongs in a `promptclaw/asset_bus/` subpackage (mirrors the
  existing `promptclaw/federation/` and `promptclaw/coherence/` subpackages). The CLI is wired
  in `promptclaw/cli.py` (mirror how `pal` is added). Tests are flat `tests/test_asset_bus_*.py`.
- **Box render capabilities (integration targets, NOT to be reimplemented):**
  - Images: DreamShaper 8 fp32 diffusion via `senseweave/pareidolia_diffusion.py` / `art_engine.py`
    (txt2img + img2img). PNG output. Native ~512–768 px.
  - Music: SuperCollider synthesis engine (`tools/duet_composer.py` + `senseweave/synthesis/*`).
    Generative-ambient strength; renders fixed-length WAV.
  - Voiceover: **none.** No TTS stack exists on the box today.
- **Transport:** Tailscale SSH from laptop to box already works. No two-way file sync exists.

---

## Goals

1. A working producer that fulfills `image` and `music` requests end-to-end against the v0.1 contract.
2. Honest capability handling: `voiceover` returns `deferred`; `sfx` is best-effort/experimental.
3. Fully testable in-repo with no live box and no GPU (fake runner at the boundary).
4. Idempotent and crash-safe: re-processing a request with an existing result is a no-op; all
   writes are atomic.
5. Safe: request fields are untrusted input; no shell injection, no path traversal, bounded work.
6. Operable: a single `promptclaw asset-bus` CLI to run the loop, process once, validate, and self-check.

## Non-Goals

- No requester-side code (that is the Deniable agent's job, per the frozen spec).
- No federation, no signed messages, no daemon-inbox integration (possible later; out of scope).
- No new TTS stack. Voiceover stays `deferred` until a separate decision.
- No GUI, no web service, no continuous two-way mirror beyond the per-request SSH dispatch.
- No changes to the v0.1 wire contract. Producer adapts to the spec, not vice versa.

## Operator Involvement Contract

- Anthony retains engineering authority (paths, deploy, timelines).
- The producer must never auto-deploy to the box; box render CLIs are deployed by the operator.
- The producer must run only against an explicitly configured `$DENIABLE_ASSET_BUS` root.

---

## Proposed Architecture

New subpackage `promptclaw/asset_bus/`:

- **`schema.py`** — typed models for request and manifest; a `parse_request()` /
  `validate_request()` that enforces `schema == deniable-asset-bus/v0.1`, required fields, and
  `asset_type` ∈ {image, music, voiceover, sfx}. Rejects unknown/missing fields with a clear error.
- **`store.py`** — bus directory resolution from `$DENIABLE_ASSET_BUS`, listing of pending
  requests, atomic write (`*.tmp` + `os.replace`), `sha256` + byte size of produced files,
  result-manifest read/write, and idempotency check (result already present for a `request_id`).
- **`capabilities.py`** — the capability matrix: image=supported, music=supported(style-constrained),
  sfx=experimental, voiceover=deferred. Single source of truth for routing/deferral decisions.
- **`runner.py`** — a `BoxRunner` protocol with `run(argv, *, files_out) -> RunResult`. Production
  impl `SSHBoxRunner` invokes deployed box CLIs over Tailscale SSH and pulls output files back
  (scp/rsync). `FakeBoxRunner` returns canned artifacts for tests. Arguments are passed as an argv
  list (never a shell string) to prevent injection.
- **`routers.py`** — one renderer per asset type behind a common interface; maps a validated
  request to a `BoxRunner` invocation (image → image render CLI; music → music render CLI;
  sfx → music render CLI in sfx mode; voiceover → immediate `deferred`).
- **`producer.py`** — the orchestration loop: scan `requests/`, skip already-fulfilled, validate,
  route, write produced files into `deliverables/<request_id>/`, write the manifest atomically,
  optionally update `status/`. Catches per-request errors and writes an `error` manifest rather
  than crashing the loop.
- **`cli.py`** — `promptclaw asset-bus {run|once|validate|doctor}` wired into `promptclaw/cli.py`.

Box-side render entrypoints (thin wrappers, deployed to `/home/user/cypherclaw/tools/`):

- **`asset_render_image.py`** — args in, one PNG out; wraps the existing DreamShaper pipeline.
- **`asset_render_music.py`** — args in, one WAV out of a given duration/mood/scene; wraps the
  existing synthesis render. These are tested in-repo only via the `FakeBoxRunner` contract; the
  real wrappers are operator-deployed.

---

## Requirements

Format: markdown table per SDP analyzer conventions. Tier T1 = small (~3 hrs); T2 = medium (~6 hrs).

### Schema & Validation

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| DAB-001 | `promptclaw/asset_bus/schema.py` defines request and manifest models matching `docs/deniable-asset-bus-spec.md` v0.1. | MUST | T1 | Models round-trip a fixture request and manifest; field set matches the spec. |
| DAB-002 | `validate_request()` accepts conforming requests and rejects malformed ones with specific errors; unknown extra fields are ignored. | MUST | T1 | Unit tests: a valid request passes; missing `request_id`/`asset_type`/`spec`, wrong `schema`, and unknown `asset_type` each raise a distinct error; an extra field is tolerated. |

### Store & Idempotency

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| DAB-010 | `store.py` resolves the bus root from `$DENIABLE_ASSET_BUS` (default `~/deniable-asset-bus`) and lists pending requests (those with no result manifest). | MUST | T1 | Unit test over a temp bus lists exactly the unfulfilled request ids. |
| DAB-011 | All manifest and produced-file writes are atomic (`*.tmp` then `os.replace`). | MUST | T1 | Test asserts writes go through a temp path and `os.replace`; no partial file is observable. |
| DAB-012 | `store.py` computes `sha256` and byte size per produced asset and records bus-root-relative paths in the manifest. | MUST | T1 | Test compares recorded `sha256`/`bytes` against known fixture bytes; recorded paths are relative. |
| DAB-013 | Re-processing a `request_id` that already has a result manifest is a no-op. | MUST | T1 | Idempotency test: a second pass performs no render work and does not rewrite the manifest. |

### Capability Matrix & Routing

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| DAB-020 | `capabilities.py` is the single source of truth: image=supported, music=supported, sfx=experimental, voiceover=deferred. | MUST | T1 | Unit test asserts each matrix value. |
| DAB-021 | A `voiceover` request yields a `deferred` manifest with explanatory `notes` and no renderer call; the same `request_id` can be fulfilled later. | MUST | T1 | Test: a voiceover request produces status `deferred` and the fake renderer records zero calls. |
| DAB-022 | Routing dispatches each request to the renderer named by the capability matrix for its `asset_type`. | MUST | T1 | Test asserts image routes to the image renderer and music routes to the music renderer. |

### Runner Boundary

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| DAB-030 | `runner.py` defines a `BoxRunner` protocol with a `FakeBoxRunner` returning configured artifacts and exit status; no real SSH in unit tests. | MUST | T1 | All unit tests use `FakeBoxRunner`; no network calls occur. |
| DAB-031 | `SSHBoxRunner` builds its remote command as an argv list and transfers output files back; no request-derived string is interpolated into a shell command. | MUST | T2 | Test asserts the command is constructed as an argv list and an injection fixture is passed verbatim, never via a shell string. |

### Producer Loop

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| DAB-040 | `producer.py` processes all pending requests in one pass, writing one manifest per request, never aborting the batch on a single failure. | MUST | T2 | Test with a batch containing one failing request: every other request still gets a manifest. |
| DAB-041 | On renderer/runner failure write an `error` manifest with the reason; on partial success write `partial`. | MUST | T1 | Tests force failure and partial outcomes and assert the manifest status and reason. |
| DAB-042 | A continuous `run` mode polls the bus on an interval and processes newly arrived requests. | MUST | T2 | Test drives one poll iteration via an injected clock and processes a newly added request. |

### CLI

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| DAB-050 | `promptclaw asset-bus validate --request FILE` validates one request file and prints the normalized result or the validation error. | MUST | T1 | CLI test on valid and invalid fixtures asserts the printed output and exit code. |
| DAB-051 | `promptclaw asset-bus once` processes every pending request and writes its deliverable and manifest. | MUST | T1 | CLI test produces a manifest for each pending request in a temp bus. |
| DAB-052 | `promptclaw asset-bus run` runs the continuous loop; `promptclaw asset-bus doctor` reports bus paths, configured runner, and capability matrix without doing work. | MUST | T1 | `doctor` test asserts the report content and that no files are written. |

### Box Render Entrypoints

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| DAB-060 | `tools/asset_render_image.py` accepts prompt/size/seed/count args and writes PNG(s) to an output directory. | SHOULD | T2 | A smoke test parses the documented argv and asserts the resolved render parameters. |
| DAB-061 | `tools/asset_render_music.py` accepts mood/scene/duration/loopable args and writes a WAV to an output path; the documented contract is exercised in-repo via `FakeBoxRunner`. | SHOULD | T2 | The arg contract is documented and parsed; the fake runner reproduces it. |

### Security

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| DAB-070 | Path-bearing request fields are sanitized; produced files always land under `deliverables/<request_id>/`; path traversal and absolute paths are rejected. | MUST | T1 | Test with `../` and an absolute `target_path` is rejected; output stays inside the sandbox dir. |
| DAB-071 | Render arguments derived from request fields are passed as argv only; shell metacharacters are not interpreted. | MUST | T1 | An injection fixture in a prompt is passed literally and not interpreted. |
| DAB-072 | Bounded work: per-request ceilings on image count, music duration, and total output bytes; requests over a ceiling return `error`. | MUST | T1 | Over-limit fixtures produce an `error` manifest stating the exceeded ceiling. |

### Documentation

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| DAB-080 | `docs/deniable-asset-bus-spec.md` gains a "Producer (CypherClaw side)" section. | SHOULD | T1 | The section is present and the `schema` version string is unchanged. |

---

## Suggested Task Slicing

### Sprint 1 — Contract core
- DAB-001, DAB-002 (schema + validation)
- DAB-010, DAB-011, DAB-012, DAB-013 (store + idempotency)

### Sprint 2 — Capability & runner boundary
- DAB-020, DAB-021, DAB-022 (capability matrix + routing, voiceover deferral)
- DAB-030, DAB-031 (runner protocol + fake + ssh argv safety)

### Sprint 3 — Producer & CLI
- DAB-040, DAB-041, DAB-042 (producer loop)
- DAB-050, DAB-051, DAB-052 (CLI)

### Sprint 4 — Box entrypoints, security, docs
- DAB-060, DAB-061 (box render CLI contracts)
- DAB-070, DAB-071, DAB-072 (security)
- DAB-080 (docs)

---

## Verification Strategy

### Unit & CLI tests (TDD — tests written first/alongside, never after)
- Each DAB-* requirement has at least one `tests/test_asset_bus_*.py` test.
- A round-trip test: fake request → `asset-bus once` with `FakeBoxRunner` → manifest with correct
  `status`, `sha256`, and relative paths; assets present under `deliverables/<request_id>/`.
- Idempotency test (DAB-013), injection test (DAB-071), traversal test (DAB-070), deferral test (DAB-021).

### Static checks
- The new subpackage passes the repo's existing lint/type configuration.

### Live verification (operator, post-merge, out of SDP scope)
- One real `image` and one real `music` request fulfilled end-to-end against the box, results
  copied into a scratch game folder, sha256 verified.

---

## Security Requirements

- Request files are untrusted input. Validate strictly; never `eval`/`exec` request content.
- No shell string interpolation of request-derived values (argv only).
- All produced files confined to `deliverables/<request_id>/`; reject path traversal and absolute paths.
- Enforce per-request resource ceilings (count, duration, bytes).
- No secrets in the bus; manifests carry only metadata, never credentials.

## Deployment Requirements

- Producer runs on the laptop against the configured `$DENIABLE_ASSET_BUS`.
- Box render CLIs (`asset_render_image.py`, `asset_render_music.py`) are deployed to the box by
  the operator; the producer reaches them over existing Tailscale SSH.
- No new always-on service is required for v1; `asset-bus run` may be launched on demand.

## Risks

- **Music style mismatch** — generative-ambient engine may not satisfy game-music needs; mitigated
  by `partial` + notes and by surfacing style limits in the spec.
- **Box availability** — if the box is unreachable, requests fail with `error`; producer must not hang.
- **Voiceover gap** — VO stays `deferred`; the game must not block on it.

## Assumptions

- The Deniable agent implements the requester side per the frozen v0.1 spec.
- Existing box art/synthesis entrypoints can be wrapped without modification to their internals.
- Tailscale SSH from laptop to box remains available.

## Open Questions for SDP Agents to Resolve Without Blocking

- Exact arg surface of `asset_render_image.py` / `asset_render_music.py` — choose a minimal,
  documented set consistent with the spec's `spec` blocks; the `FakeBoxRunner` defines the contract.
- Polling interval and resource ceilings — choose sane defaults, make them config-overridable.

## Operator Handoff to SDP

Build the producer in `promptclaw/asset_bus/` with tests-first, no live box, no GPU. Do not run or
modify the CypherClaw v2 aesthetic tasks. Do not deploy to the box. Keep the v0.1 wire contract
in `docs/deniable-asset-bus-spec.md` authoritative.
