# Task T-025 Specification: CypherClaw Segment Ingest Worker

## Problem Statement

CypherClaw's live audio streamer produces short Ogg/Opus segment files, but the
Cloudflare Worker has no CypherClaw ingest route yet. T-025 adds the first
Worker-side live stream primitive: authenticated `POST /api/cypherclaw/segment`
requests must store one binary segment in the existing R2 media bucket so later
tasks can build HLS playlist serving and public playback.

## Technical Approach

- Extend the existing `catalog-explorer/worker/src/index.ts` Cloudflare Worker.
- Reuse the existing `MEDIA` R2 binding; no new bucket or dependency is needed.
- Follow the existing write-endpoint pattern and require
  `Authorization: Bearer <ADMIN_TOKEN>` before storing a segment.
- Accept a binary request body with metadata headers:
  - `X-CypherClaw-Sequence` required, non-negative integer.
  - `X-CypherClaw-Captured-At` optional ISO timestamp; defaults to Worker time.
  - `X-CypherClaw-Duration`, `X-CypherClaw-Scene`, and
    `X-CypherClaw-Tuning` optional metadata.
- Store objects at `cypherclaw/live/{YYYY-MM-DD}/seg-{sequence}.opus`.
- Preserve content type from `Content-Type`, defaulting to
  `audio/ogg; codecs=opus`.
- Return JSON with `ok`, `key`, `size`, `etag`, and normalized `sequence`.

## Edge Cases

- Missing or incorrect bearer token returns `401` and does not write to R2.
- Missing body returns `400`.
- Missing, negative, or non-integer sequence returns `400`.
- Invalid `X-CypherClaw-Captured-At` returns `400`.
- Optional scene and tuning metadata are sanitized by Cloudflare R2 metadata
  storage as simple strings only.
- This task does not build playlist generation, public segment serving, DNS,
  TLS, or the streamer POST client; those are later PRD tasks.
- The generated startup identity hardening bullets are already covered by the
  existing PromptClaw startup identity anchors. T-025 does not change startup
  flow; it will re-run those anchors as regression verification.

## Acceptance Criteria

1. Authenticated `POST /api/cypherclaw/segment` writes the request body to R2 at
   the canonical live segment key and the object is visible via R2 listing.
   VERIFY:
   `cd /Users/anthony/Programming/catalog-explorer/worker && npm test`

2. Unauthenticated segment POSTs are rejected before storage.
   VERIFY:
   `cd /Users/anthony/Programming/catalog-explorer/worker && npm test`

3. The Worker TypeScript remains strict-clean.
   VERIFY:
   `cd /Users/anthony/Programming/catalog-explorer/worker && npx tsc --noEmit`

4. PromptClaw regression anchors, including startup identity hardening, remain
   green.
   VERIFY:
   `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Full PromptClaw validation remains clean after documentation updates.
   VERIFY:
   `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
