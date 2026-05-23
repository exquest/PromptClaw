# T-029 Specification - CypherClaw Session Archiver

## Problem Statement

CypherClaw now has a live Opus segment stream and Worker/R2 segment ingest, but
there is no `session_archiver.py` to turn those short live segments into
journal-like public archive sessions. The PRD requires sessions approximately
every 8 minutes or more, with CypherClaw's archive title pattern:
`{House-Imagery} / {Tuning-Character} — {DD Month}`. After 30 minutes of
synthetic uptime, at least 3 complete sessions must be present in R2 with
metadata sufficient for the later archive feed.

## Technical Approach

- Add `my-claw/tools/session_archiver.py` as a typed stdlib-only runtime tool.
- Read completed `.opus` segment files from the local streamer directory,
  defaulting to `/home/user/cypherclaw-data/streams`.
- Read optional segment sidecar JSON next to each `.opus` file for
  `captured_at`, `duration`, `scene`, `patch_name` or `house`, `tuning`, RMS,
  and MIDI influence metadata. Missing sidecars fall back to timestamp parsing
  from filenames or filesystem metadata, plus the default 6-second duration.
- Group chronological, sufficiently contiguous segments into fixed minimum
  windows of 480 seconds. A 30-minute synthetic run therefore yields 3 complete
  sessions and leaves the remaining partial window open.
- Concatenate session segment bytes into a single chained Ogg/Opus body.
- Derive dominant house and primary tuning by duration-weighted segment
  metadata. Map those values into CypherClaw's title vocabulary, for example
  `house_monastery` -> `Monastery-Stone` and `slendro` ->
  `Slendro-Drift`.
- Upload two objects per session through an injectable R2/S3-compatible client:
  `cypherclaw/archive/{session_id}/session.opus` and
  `cypherclaw/archive/{session_id}/metadata.json`.
- Persist local archiver state after successful uploads so repeated runs do not
  duplicate already archived session windows.
- Call `bootstrap_identity()` before archiving work. The CLI accepts
  standalone/federated identity arguments and optional identity path so this
  new startup path follows the existing hardening pattern.

## Edge Cases

- Fewer than 480 seconds of complete segments produces no archive session.
- Partial final windows are not uploaded until they reach the minimum duration.
- Missing sidecar metadata falls back to deterministic defaults without
  blocking archival.
- Segment gaps larger than the configured contiguity threshold start a new
  candidate window rather than merging unrelated audio.
- Upload failures must not mark a session archived in local state.
- Re-running the archiver over the same segment directory must be idempotent.
- R2 credentials are runtime configuration only. Tests use a fake uploader; no
  provider secrets or new dependencies are committed.
- No database schema or migration is needed.
- The generated startup identity hardening bullets are addressed by this
  tool's bootstrap call and by re-running the existing startup identity anchors.

## Acceptance Criteria

1. T-029 has a written specification with problem statement, technical
   approach, edge cases, and verifiable acceptance criteria.
   - **VERIFY:** `rg -n "T-029|Problem Statement|Technical Approach|Edge Cases|Acceptance Criteria" specs/t-029-spec.md`

2. Phase 0 exploration findings are documented in `progress.md`.
   - **VERIFY:** `rg -n "T-029 Phase 0 Explore|session_archiver|cypherclaw/archive|R2" progress.md`

3. Thirty minutes of synthetic uptime produces at least 3 complete archived
   sessions under the R2 archive prefix, each with a session audio object and
   metadata object.
   - **VERIFY:** `pytest tests/test_session_archiver.py::test_thirty_minutes_of_synthetic_uptime_uploads_three_named_sessions_to_r2 -q`

4. Session titles follow CypherClaw's naming pattern using dominant house,
   primary tuning, and human-readable date.
   - **VERIFY:** `pytest tests/test_session_archiver.py::test_session_title_uses_dominant_house_primary_tuning_and_date -q`

5. The archiver persists state and does not re-upload the same complete
   session windows on a repeat run.
   - **VERIFY:** `pytest tests/test_session_archiver.py::test_repeat_archiver_run_skips_already_uploaded_sessions -q`

6. Startup identity hardening is wired into this new runtime path and preserves
   identity across repeated starts.
   - **VERIFY:** `pytest tests/test_session_archiver.py::test_archiver_startup_bootstraps_identity_before_upload_and_persists_between_boots -q`
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

7. Task bookkeeping documents scope, assumptions, dependency status, and
   validation results.
   - **VERIFY:** `rg -n "T-029|session_archiver|cypherclaw/archive|R2|identity" CHANGELOG.md progress.md ESCALATIONS.md specs/t-029-spec.md`

8. Full repository validation passes.
   - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
