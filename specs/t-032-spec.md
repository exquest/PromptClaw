# T-032 Specification - Scripted Live Audio End-to-End Test

## Problem Statement

CypherClaw has separate pieces of the public stream path: `audio_streamer.py`
captures JACK output into Ogg/Opus segments, the holdenu Worker accepts segment
POSTs and stores them in R2, the Worker serves a rolling HLS playlist and segment
proxy, and the `cypherclaw.holdenu.com` root page contains a browser `<audio>`
element wired to that playlist. There is not yet one automated test that proves
a tone-generator signal can cross those boundaries and reach the browser audio
surface within the PRD's 30-second budget.

## Technical Approach

- Keep PromptClaw as the ADP source of truth for this spec, progress notes,
  changelog, and escalation records.
- Add a small typed streamer upload helper in `my-claw/tools/audio_streamer.py`
  that posts a completed segment file to the Worker's existing
  `/api/cypherclaw/segment` route with the canonical CypherClaw metadata
  headers. This is the production boundary between the JACK/ffmpeg streamer and
  the Worker.
- Add locked Python coverage for the streamer upload helper to prove the POST
  request carries the sequence, captured timestamp, duration, scene, tuning,
  source marker, content type, bearer token, and latency result parsing.
- Add a dependency-free Worker E2E test in
  `/Users/anthony/Programming/catalog-explorer/worker/tests/` that scripts the
  CI-safe version of the full path:
  1. construct a synthetic Ogg/Opus-like JACK tone segment body;
  2. POST it to the real Worker handler with `X-CypherClaw-Source:
     jack-tone-generator`;
  3. verify fake R2 stores the object with source and latency metadata;
  4. fetch `/api/cypherclaw/live.m3u8` and verify it references the segment;
  5. fetch the segment through `/api/cypherclaw/segment/...` and verify bytes;
  6. fetch the root page, execute the inline browser runtime with a fake DOM,
     and verify the `<audio>` element is pointed at the live playlist;
  7. log `cypherclaw_t032_latency_ms=<value>` and assert the measured path is
     under 30 seconds.
- Extend the Worker ingest response with a `latency_ms` field derived from
  `X-CypherClaw-Captured-At` and the Worker receipt time. Preserve existing
  segment metadata for clients that do not send the new source marker.

## Edge Cases

- CI does not require live JACK, a real browser, Cloudflare credentials, or a
  live R2 bucket. The test uses a scripted tone segment and a fake R2 bucket but
  exercises the real Worker handler, playlist generation, segment proxy, and
  browser audio initialization code.
- The existing T-026 Ogg/Opus HLS-container caveat remains: this verifies the
  request/storage/playlist/browser-wiring path and byte retrieval, not native
  media decoder compatibility in hls.js or Safari.
- Missing or invalid captured timestamps continue to follow existing Worker
  validation behavior. Future timestamps produce a non-negative latency.
- Source and latency custom metadata are only added to R2 when the streamer sends
  `X-CypherClaw-Source`, so existing ingest tests and clients keep their exact
  metadata shape.
- No new Python, npm, database, migration, provider-secret, or runtime-state
  dependency is required.
- The generated startup identity hardening bullets target existing startup
  paths. T-032 verifies the established CLI, first-boot, daemon-ordering, and
  narrative ASGI identity anchors instead of changing unrelated startup flow.

## Acceptance Criteria

1. T-032 has a written specification with problem statement, technical approach,
   edge cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-032|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-032-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "T-032 Phase 0 Explore|audio_streamer|Worker|R2|browser <audio>" progress.md`

3. The streamer exposes a typed upload helper that sends the canonical Worker
   segment POST headers and parses the Worker's latency response.
   - **VERIFY:** `pytest tests/test_audio_streamer.py::test_post_segment_to_worker_sends_streamer_headers_and_reports_latency -q`

4. A scripted Worker E2E test confirms a synthetic JACK tone segment flows
   through Worker ingest, fake R2, playlist serving, segment serving, and
   browser `<audio>` initialization within 30 seconds, while logging latency.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test -- tests/cypherclaw-e2e.test.js`

5. Existing Worker live-page, segment, playlist, archive-feed, and visualizer
   behavior remains intact.
   - **VERIFY:** `cd /Users/anthony/Programming/catalog-explorer/worker && npm test && npm run check`

6. Mandatory startup identity hardening remains covered for
   `bootstrap_identity()` persistence, standalone/federated reuse, and
   bootstrap-before-announcer ordering.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

7. Task bookkeeping documents T-032 scope, assumptions, dependency status, and
   validation results.
   - **VERIFY:** `rg -n "T-032|tone-generator|audio_streamer|latency|browser <audio>|R2" CHANGELOG.md progress.md ESCALATIONS.md specs/t-032-spec.md`

8. Full PromptClaw validation passes.
   - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
