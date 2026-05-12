# PRD: CypherClaw External Generation — Phase 5 of the Listening Architecture

## Overview

CypherClaw composes from rules. Phase 1–4 of the listening architecture
gives it ears — a CLAP-anchored cross-modal geometry, an IDyOM LTM whose
predictive distribution drifts with exposure, and an ITPRA readout whose
sweet-spots track its own listening history. Phase 5 closes the loop: it
turns that accumulated *taste* into new audio by routing
**MusicGen-medium** (or **Stable Audio Open**) through a serverless GPU
API, conditioned on the rolling CLAP centroid of recent listening.

The architectural place is precise. Phase 5 is not a "music generation
feature" — it is the **generation back-end of a predictive listener**. The
output is not a finished track to play; it is a sample to drop into the
existing sampler library so the granular voice picks it up like any other
captured material. Generated audio is indistinguishable, downstream, from
the room captures and the curated library. Phases 1–4 pick what to listen
to. The sampler picks how to play it back. Phase 5 is the only stage that
introduces material the system hasn't heard before.

This PRD ships the generation back-end without blocking on the planned
RTX 2000 Ada 16 GB upgrade. The listening front-end (CLAP, MERT-base,
IDyOMpy, AMT, scikit-maad, PANNs, BirdNET) runs on the current T1000 8 GB.
The generation back-end (MusicGen / Stable Audio Open at 3–5 GB VRAM
firing once per art cycle) runs on Replicate or Modal serverless until
the upgrade lands. The `GenerationClient` Protocol then swaps to a local
implementation with no caller-side change.

Five principles govern the design:

1. **Generation is a sample source, not a parallel synthesis path.**
   Generated audio lands in `samples/generated/` with full metadata,
   indexes in `index.sqlite` with `source="generated"`, and is picked
   by the existing `SampleSelector` when mode/arc/mood matches. The
   composer never knows or cares whether a sample is library, room, self,
   or generated.
2. **Async fire-and-forget.** The composer never waits on the network.
   Requests queue; results land in the library minutes later and are
   eligible from the next selector pass onward. Cold-start latency is
   irrelevant because nothing blocks on it.
3. **Conditioned by the predictive listener, not by per-piece prompts.**
   The conditioning vector is the rolling CLAP centroid of recent
   inputs (room captures + corpus retrievals + IDyOM-flagged surprising
   pieces), never a hand-written "in the style of Eno" string. Text
   prompts are derived deterministically from artist mode + arc phase +
   mood via a static, version-controlled template — explicitly
   **rejecting LLM-as-prompt-writer**, the homogenization trap from the
   creativity-theatre literature.
4. **Hard daily and monthly $ caps.** When the cap is hit, the queue
   pauses; existing samples carry the music. Caps are tunable by env
   var and exposed in diagnostics. Bedrock fallback principle:
   **Phase 5 adds, never replaces.** If generation breaks for any
   reason, the system sounds exactly like Phase 1–4 + the library.
5. **Backend-agnostic.** `GenerationClient` is a Protocol. `ReplicateClient`
   is the primary; `ModalClient` is a cheaper alt with more setup;
   `LocalAdaClient` lands when the GPU upgrade is in. Caller code is
   unchanged across all three.

The artistic outcome: each art cycle, when the predictive listener's
state has shifted enough to warrant fresh material, a new sample appears
in the library. It is *of* the room and *of* the listening history at
that moment, never literally — granularly transformed by the sampler at
playback time. CypherClaw composes new music *because* it has been
listening, and the music it generates is part of what it listens to next.

## Scope and non-goals

**In scope:** a content-hashable `GenerationRequest` data model; a pure
deterministic `GenerationConditioner` from listening state to request; a
`GenerationClient` Protocol with `ReplicateClient` as the shipped primary
and `ModalClient` + `LocalAdaClient` stubs; a daily/monthly USD budget
with persistence and atomic rollover; a content-addressed audio cache
with LRU + size eviction; an async persistent `GenerationQueue` with
idempotent enqueue; `GenerationStorage` that writes to disk and registers
a `SampleRecord` with `source="generated"` in the existing SQLite library;
a composer post-song hook that conditionally enqueues; a systemd worker
unit; mode-collapse discipline (source-tagged metrics, dominance detector,
KL-divergence weekly audit, self-distance prior on conditioning);
diagnostics surface; runbook; e2e smoke against real Replicate.

**Out of scope / non-goals:**

- Replacing the existing sampler quintet with generated-only audio. The
  quartet of synthesis voices and the granular sampler stay.
- LLM-driven prompt authoring. Prompt templates are static, in code,
  version-controlled. The LLM is never near aesthetic decisions in
  Phase 5.
- Real-time generation. Latency target is "next art cycle" (~30 min),
  not "this scene." Synchronous calls are explicitly disallowed.
- Long-form structure. MusicGen / SAO produce 30 s clips; the *piece-level*
  structure stays in `score_tree` + `recursive_composer`. Phase 5 produces
  raw material for the sampler, not whole pieces.
- Audio melodic-seed conditioning (`melody_audio` input on MusicGen). v2
  feature; ship text + CLAP first.
- Variable-length output beyond the shipped 30 s default. Adjustable by
  env once the system is producing good material at default length.
- Fine-tuning of MusicGen / SAO on Anthony's corpus. Defer until the GPU
  upgrade and a year of accumulated taste data. Prompt + CLAP conditioning
  is enough material for v1.
- Local generation. `LocalAdaClient` ships as a stub; the real
  implementation lands as a separate work item once the RTX 2000 Ada
  is installed.

## The five phases

**Phase 1 — Foundations (CCG-001..CCG-008).** `GenerationRequest`
dataclass with content hashing; `GenerationConditioner` with per-mode
prompt fragments + deterministic seed derivation; `GenerationBudget`
with daily/monthly persistence; `GenerationCache` content-addressed with
LRU/size eviction; `validate_audio` rejecter. Pure Python + tests, no
network. End of phase: requests can be built, hashed, cached, and
budgeted in isolation; canned audio inputs flow through validation.

**Phase 2 — Backend client (CCG-009..CCG-014).** `GenerationClient`
Protocol + `GenerationResult` dataclass; `ReplicateClient` with mocked
+ live tests; `ModalClient` parity implementation; `LocalAdaClient`
stub raising `NotImplementedError`; cost-tracking from Replicate
prediction metadata; rate-limit and timeout handling with bounded
exponential backoff. End of phase: a single `client.generate(req)`
call against real Replicate produces a valid 30 s WAV in `/tmp` and a
GenerationResult with cost recorded; mocked tests cover failure cascades.

**Phase 3 — Storage + queue (CCG-015..CCG-021).** `GenerationStorage`
writes WAV to `samples/generated/<yyyy-mm-dd>/<hash>.wav`, computes
peak/RMS/CLAP-tag, registers `SampleRecord` in `SampleLibrary`;
`GenerationQueue` SQLite-backed persistent queue with idempotent enqueue,
asyncio worker, max-concurrency cap, retry-with-backoff, restart-resilience;
post-failure retry budget bounded per request. End of phase: one full
mocked-Replicate lifecycle (enqueue → cache miss → generate → validate
→ store → register → mark done) green in CI.

**Phase 4 — Composer integration (CCG-022..CCG-026).** Composer
`_post_song_generation_hook` invoked from `tracker_solo_song` post-result;
`_should_queue_now` heuristic gated on cycle-rate, mode-change events,
and the existing sampler antipattern detectors; `cypherclaw-generation-worker`
systemd unit with `Restart=always`, `LimitMEMLOCK=infinity`, and
`EnvironmentFile=` honoring the budget cap env vars; `/tmp/generation_status.json`
diagnostic surface. End of phase: composer running on cypherclaw queues
at least one generation per ~3 art cycles in production; generated samples
appear audibly in pieces selected after their save time.

**Phase 5 — Discipline + observability (CCG-027..CCG-032).** Source-tagged
metric extension to `usage_journal.jsonl` (per-piece per-source ratios);
generated-content dominance detector wired into `render/antipatterns.py`;
weekly KL-divergence audit against frozen IDyOM LTM checkpoint; self-distance
prior on `GenerationConditioner` (skip requests whose embedded prompt sits
< 0.3 cosine from rolling 7-day generated-centroid); operator runbook in
`docs/runbooks/generation-backend.md`; live smoke against Replicate as
an `@pytest.mark.live_replicate` test. End of phase: 7 consecutive days
of production runtime with daily $ stays-under-cap, mode-collapse audit
runs cleanly, sampler-source ratios are healthy.

## Depends on

- `my-claw/sdp/prd-cypherclaw-sampler.md` — the granular memory voice;
  generated audio lands in the same `SampleLibrary` and is dispatched via
  the same `SamplerDispatcher`. Phase 5 reuses every component there.
- `my-claw/tools/senseweave/sample_library.py` — `SampleRecord`,
  `SampleLibrary.add()`. Phase 5 adds `source="generated"` to the
  acceptable source enum.
- `my-claw/tools/senseweave/sampler_dispatch.py` — `BufferLoader.on_sampler_load`;
  Phase 5 produces records that satisfy this protocol.
- `my-claw/tools/senseweave/artist_identity.py` — `ArtistMode` and
  `select_mode()`. Phase 5's conditioner reads mode + arc to build prompts.
- The Phase 1–4 listening spine (separate PRD, in flight): produces the
  rolling CLAP centroid Phase 5 conditions on. Until that ships,
  `GenerationConditioner` accepts a placeholder centroid (uniform random
  unit-vector seeded by run-time inputs) so Phase 5 can integration-test
  before Phase 1–4 is ready.
- `tools/duet_composer.py` — `tracker_solo_song`, `_post_song_self_quote`;
  Phase 5 adds a parallel `_post_song_generation_hook`.
- `docs/research/2026-04-26-music-listening-audit.md` and
  `docs/research/2026-04-26-listening-as-taste-architecture.md` — the
  research that motivates this work and names the discipline rules
  (mode-collapse mitigations, no-LLM-as-judge, etc).

## Key files and modules

- **New** `my-claw/tools/senseweave/generation/` package:
  - `request.py` — `GenerationRequest` dataclass, content-hashing
  - `conditioner.py` — `GenerationConditioner`; prompt templates per mode
  - `client_protocol.py` — `GenerationClient` Protocol, `GenerationResult`
  - `client_replicate.py` — `ReplicateClient`
  - `client_modal.py` — `ModalClient`
  - `client_local.py` — `LocalAdaClient` (stub raising `NotImplementedError`)
  - `budget.py` — `GenerationBudget` with persistence
  - `cache.py` — `GenerationCache` content-addressed
  - `queue.py` — `GenerationQueue` async + worker loop
  - `storage.py` — `GenerationStorage` writing to library
  - `validate.py` — `validate_audio` (silence / clip / NaN check)
  - `health.py` — mode-collapse audit (KL divergence, dominance detector)
- **New** `my-claw/tools/generation_worker.py` — standalone worker entry
- **New** `my-claw/systemd/cypherclaw-generation-worker.service`
- **New** `my-claw/tests/test_generation_*.py` — per-component + e2e
- **Extended** `my-claw/tools/duet_composer.py` — post-song hook
- **Extended** `my-claw/tools/senseweave/sample_library.py` — accept
  `source="generated"`; ensure `SampleRecord` validates
- **Extended** `my-claw/tools/senseweave/usage_journal.py` — source-tagged
  ratios per piece
- **Extended** `my-claw/tools/senseweave/render/antipatterns.py` —
  `generated_content_dominance` detector
- **New** `docs/runbooks/generation-backend.md` — operator runbook

## Requirements

| ID | Description | Priority | Tier | Acceptance criteria |
|----|-------------|----------|------|---------------------|
| CCG-001 | Define `GenerationRequest` frozen dataclass with prompt, clap_centroid (np.ndarray[512]), duration_sec, seed, backend, model, bpm_target, mode_name, arc_phase fields. | MUST | T1 | - `senseweave/generation/request.py` defines the dataclass with `frozen=True`<br/>- `clap_centroid` is `np.ndarray` with shape `(512,)` and dtype `float32`<br/>- `backend` is a `Literal["replicate", "modal", "local"]` defaulting to `"replicate"`<br/>- `model` is a `Literal["musicgen-medium", "stable-audio-open"]` defaulting to `"musicgen-medium"`<br/>- `duration_sec` validates to range `[5.0, 60.0]` on construction, raises `ValueError` otherwise<br/>- `seed` is an int and is included in the hash<br/>- tests cover field types, defaults, range validation, and rejection of invalid backend/model strings |
| CCG-002 | Implement `GenerationRequest.hash()` content-addressed identity that excludes `backend` and includes prompt, clap_centroid bytes, duration, seed, model, bpm_target. | MUST | T1 | - `request.hash()` returns a 64-char hex SHA-256 string<br/>- Identical inputs produce identical hashes across process restarts<br/>- Changing any of {prompt, clap_centroid, duration_sec, seed, model, bpm_target} changes the hash<br/>- Changing `backend` does NOT change the hash (so Replicate ↔ Modal migrations preserve cache)<br/>- Tests verify each field's contribution and the backend exclusion |
| CCG-003 | Implement `GenerationConditioner.build_request(mode, arc_phase, mood, clap_centroid, duration_sec)` returning `GenerationRequest` with deterministic prompt and seed. | MUST | T1 | - `senseweave/generation/conditioner.py` defines `GenerationConditioner`<br/>- `build_request` is pure: same inputs → same `GenerationRequest` (including hash)<br/>- Prompt is composed via static template: `"<mode-fragment>, <arc-fragment>, <mood-adjective>: <constraint-fragment>"`<br/>- Per-mode fragments live in a `_MODE_FRAGMENTS` dict; tests assert table values<br/>- Seed is derived via SHA-256 of (mode.name, arc_phase, sorted-mood-tuple, clap_centroid bytes), folded to 32-bit int<br/>- CLAP centroid is unit-normalized before storage<br/>- No `import openai`, `import anthropic`, `ollama`, or any LLM call appears in this module |
| CCG-004 | Define per-mode prompt fragment table for solitary, companion, working_ambience, evening_reflection, storm. | MUST | T1 | - `_MODE_FRAGMENTS` table keys exactly match the 5 ArtistMode names<br/>- Each value is a `tuple[str, ...]` of palette + restraint adjectives<br/>- solitary: includes "intimate", "sparse", "single voice", "long held tones", "lots of silence"<br/>- companion: includes "warm", "harmonic", "supportive", "two-three voices"<br/>- working_ambience: includes "pulse-based", "predictable", "no melody", "minimal"<br/>- evening_reflection: includes "longer phrases", "harmonic tension", "tender", "lyrical"<br/>- storm: includes "turbulent", "dense grains", "modal shifts", "fast articulation"<br/>- Tests assert presence of canonical fragments per mode |
| CCG-005 | Define per-arc-phase fragment overlays (Emergence, Crystallization, Divination, Convergence, Conversation, Reflection, etc.) feeding into prompt composition. | MUST | T1 | - `_ARC_FRAGMENTS` dict keyed by ArcPhase name<br/>- Each value contributes one short string fragment to the final prompt<br/>- Unknown arc names fall back to a neutral "in-progress" fragment<br/>- Tests assert canonical fragment per arc and the fallback path |
| CCG-006 | Implement `GenerationBudget` with daily and monthly USD caps, atomic persistence, and date-rollover. | MUST | T1 | - `senseweave/generation/budget.py` defines `BudgetState` dataclass and `GenerationBudget` class<br/>- Defaults: `daily_cap_usd=5.0`, `monthly_cap_usd=100.0`<br/>- State persists to `/home/user/cypherclaw-data/state/generation_budget.json` via atomic write (`os.replace`)<br/>- Caps overridable via `CYPHERCLAW_GENERATION_DAILY_CAP_USD` and `CYPHERCLAW_GENERATION_MONTHLY_CAP_USD` env vars<br/>- `allow(req)` returns `(allowed: bool, reason: str)`; estimates cost from per-model rate × duration × 1.5 overhead factor<br/>- `record(result)` increments today_spent + month_spent atomically<br/>- Auto-rollover on date change tested with mocked clock<br/>- Tests cover cap enforcement, rollover, persistence across instances, env-var overrides |
| CCG-007 | Implement `GenerationCache` content-addressed audio cache with LRU + size-cap eviction. | MUST | T1 | - `senseweave/generation/cache.py` defines `GenerationCache(root, max_entries, max_size_gb)`<br/>- Defaults: `max_entries=256`, `max_size_gb=5.0`<br/>- `lookup(req)` returns Path or None; touches LRU on hit<br/>- `put(req, audio_path)` copies file into cache, evicts LRU if over either limit<br/>- Eviction trips on whichever cap hits first; tested<br/>- Cache state survives process restart (filesystem + sidecar `cache_index.json` listing access timestamps)<br/>- Tests cover hit/miss, LRU ordering, size eviction, count eviction, persistence |
| CCG-008 | Implement `validate_audio(path)` rejecting silent / clipped / NaN / wrong-format files. | MUST | T1 | - `senseweave/generation/validate.py` defines `validate_audio(path) -> ValidationReport`<br/>- ValidationReport has `valid: bool`, `reason: str`, `peak_dbfs: float`, `rms_dbfs: float`, `nan_count: int`, `format: str`<br/>- Rejects when peak > 0 dBFS (clipping), RMS < -50 dBFS (silence), any NaN samples, or format other than WAV/FLAC<br/>- Accepts mono or stereo at 22050+ Hz<br/>- Test fixtures: silent WAV, clipped WAV, NaN-laden WAV, valid stereo WAV; assertions on each |
| CCG-009 | Define `GenerationClient` Protocol and `GenerationResult` dataclass. | MUST | T1 | - `client_protocol.py` defines `class GenerationClient(Protocol)` with `generate(request: GenerationRequest) -> GenerationResult`<br/>- `GenerationResult` is frozen dataclass: `audio_path: Path`, `sample_rate: int`, `duration_actual_sec: float`, `model_used: str`, `cost_usd: float`, `latency_ms: int`, `api_request_id: str`<br/>- Type-check passes when both ReplicateClient and a test FakeClient satisfy the Protocol<br/>- Tests use FakeClient to confirm Protocol satisfaction at runtime |
| CCG-010 | Implement `ReplicateClient.generate(request)` using the official `replicate` Python SDK with timeout, polling, and result download. | MUST | T1 | - `client_replicate.py` defines `ReplicateClient(api_token, timeout_sec=120.0)`<br/>- API token loaded from `REPLICATE_API_TOKEN` env var; never logged<br/>- Maps `request.model` to Replicate model IDs via a `REPLICATE_VERSIONS` dict (`musicgen-medium` → `meta/musicgen:...`, `stable-audio-open` → `stability-ai/stable-audio-open:...`)<br/>- Submits prediction with input dict from `_build_input(req)`; polls until complete or timeout<br/>- Downloads audio output to a temp path; verifies it exists before returning<br/>- Computes `cost_usd` from `prediction.metrics.predict_time` × per-second rate from `PER_SECOND_USD` table<br/>- Mocked tests cover happy path, timeout, 4xx error, 5xx error, network error |
| CCG-011 | Implement Replicate rate-limit (429) and 5xx retry with exponential backoff bounded to 3 attempts, honoring `Retry-After`. | MUST | T1 | - `ReplicateClient.generate` wraps prediction submission in a retry loop<br/>- Retry on 429 and 5xx; do NOT retry on 4xx (other than 429)<br/>- Backoff: 5 s → 30 s → 5 min, capped at `Retry-After` if present and larger<br/>- Maximum 3 retries; after that raises `GenerationError`<br/>- Tests mock httpx-style responses and assert call counts + delays |
| CCG-012 | Implement `ModalClient` parallel implementation of `GenerationClient` Protocol. | MUST | T2 | - `client_modal.py` defines `ModalClient` satisfying `GenerationClient` Protocol<br/>- Uses Modal Python SDK to invoke a deployed MusicGen function<br/>- Cost computed from Modal prediction metadata × per-second A10G rate<br/>- Mocked test asserts Protocol parity with `ReplicateClient`<br/>- Real Modal call gated behind `@pytest.mark.live_modal` (skipped by default) |
| CCG-013 | Provide `LocalAdaClient` stub raising `NotImplementedError`. | MUST | T2 | - `client_local.py` defines `LocalAdaClient` satisfying the `GenerationClient` Protocol signature<br/>- `generate()` raises `NotImplementedError("LocalAdaClient: GPU not yet installed; use Replicate or Modal")`<br/>- Static type-check confirms Protocol satisfaction<br/>- Test asserts the raise + message |
| CCG-014 | Implement live smoke test against real Replicate that asserts a 30 s WAV is produced and cost is recorded. | MUST | T2 | - `tests/test_generation_live_replicate.py` marked `@pytest.mark.live_replicate`<br/>- Runs only when `REPLICATE_API_TOKEN` is set and `--run-live-replicate` flag passed<br/>- Calls `ReplicateClient.generate(req)` with a fixed test prompt and seed<br/>- Asserts result is a real WAV file > 100 KB<br/>- Asserts `cost_usd > 0.01 and cost_usd < 0.50` (sanity bound)<br/>- Asserts `latency_ms < 60000`<br/>- Documented in test docstring as ~$0.10 per run |
| CCG-015 | Implement `GenerationStorage.save(result, request)` writing WAV to `samples/generated/<yyyy-mm-dd>/<hash>.wav` and registering `SampleRecord`. | MUST | T1 | - `storage.py` defines `GenerationStorage(library, samples_root)`<br/>- `save(result, req)` produces a target path with the date partition and request hash<br/>- If audio is mp3, transcode to WAV via `ffmpeg -y -i in.mp3 -ar 48000 -ac 2 out.wav` before saving<br/>- If audio is WAV but not 48 kHz stereo, resample/upmix via `librosa` or `sox`<br/>- Computes peak, RMS, duration via `soundfile.read`<br/>- Builds SampleRecord with `source="generated"` and registers via `library.add(record)`<br/>- Tags include `"generated"` plus model name and mode; mood and arc carried from request<br/>- Tests with mocked library cover format conversion, peak/RMS computation, library register call, target path layout |
| CCG-016 | Extend `SampleLibrary` to accept `source="generated"`. | MUST | T1 | - `sample_library.py`: `SOURCE_VALUES` (or equivalent enum) gains `"generated"`<br/>- `SampleLibrary.find(source="generated")` returns generated records<br/>- Tests assert insertion + retrieval round-trip with `source="generated"` |
| CCG-017 | Implement `GenerationQueue` SQLite-backed persistent queue with idempotent enqueue. | MUST | T1 | - `queue.py` defines `GenerationQueue(db_path, client, cache, budget, storage, max_concurrent=1)`<br/>- SQLite schema: `gen_queue(hash TEXT PRIMARY KEY, request_json TEXT, status TEXT, attempts INT, error TEXT, created_at REAL, updated_at REAL)`<br/>- Status states: `pending`, `running`, `done`, `failed`, `blocked` (budget)<br/>- `enqueue(req)` is idempotent: re-enqueue with same hash that is `pending`/`running`/`done` is a no-op; `failed` past max-retries is also no-op<br/>- Tests cover idempotence, state transitions, restart resilience |
| CCG-018 | Implement async worker loop `GenerationQueue.run_worker()` that processes pending items end-to-end. | MUST | T1 | - `run_worker()` is an `async def` infinite loop<br/>- Each iteration: pull next `pending` (oldest first), check cache, check budget, generate, validate, store, mark `done` (or appropriate failure state)<br/>- Cache hit → mark done with `source="cache"` without paying<br/>- Budget deny → mark `blocked` (next iteration tries again with fresh budget after rollover)<br/>- `client.generate()` runs in `asyncio.to_thread` so the event loop stays responsive<br/>- `max_concurrent` limits parallel workers (default 1)<br/>- Tests with FakeClient verify each branch (cache hit, budget block, gen success, gen failure, validation reject) |
| CCG-019 | Implement bounded retry on transient generation failures with `attempts` column. | MUST | T1 | - On `GenerationError` (transient), increment `attempts`, mark `pending` again until `attempts >= 3`<br/>- After 3 attempts, mark `failed` permanently with last error<br/>- Validation rejection counts as terminal — no retries (model produced bad output, retrying won't help)<br/>- Tests assert retry count enforcement and terminal-vs-transient distinction |
| CCG-020 | Implement `_post_song_generation_hook(score, learning, mood, mode, clap_centroid)` in `tools/duet_composer.py`. | MUST | T1 | - Hook called from `tracker_solo_song` after `result.completed`, parallel to `_post_song_self_quote`<br/>- Reads global `_generation_queue` (lazy-init); no-op if Phase 5 not enabled<br/>- Calls `_should_queue_now(mode, mood, learning)` to gate<br/>- When gated true, calls `_conditioner.build_request(...)` and `_generation_queue.enqueue(req)`<br/>- Never raises out to the composer; logs failures and continues<br/>- Tests with mocked queue + conditioner assert correct call-through and gate behavior |
| CCG-021 | Implement `_should_queue_now(mode, mood, learning)` heuristic based on cycle rate and homogeneity flags. | MUST | T1 | - Returns True when ALL of: (a) at least 30 minutes since last enqueued generation, (b) the existing sampler antipattern detectors don't currently report `sampler_dominating`, (c) the daily budget has > $0.50 remaining<br/>- Returns True 100% of the time when no generation has ever been enqueued (cold start)<br/>- Returns False if mode is `working_ambience` and current piece's arc_payoff < 0.4 (don't generate during quiet work)<br/>- Tests with synthetic state cover each branch |
| CCG-022 | Add systemd unit `cypherclaw-generation-worker.service` running the queue worker. | MUST | T1 | - `my-claw/systemd/cypherclaw-generation-worker.service`<br/>- `User=user`, `LimitMEMLOCK=infinity`, `Restart=always`, `RestartSec=10`<br/>- `EnvironmentFile=/home/user/cypherclaw/.env` (carries `REPLICATE_API_TOKEN` + budget caps)<br/>- `ExecStart=/home/user/cypherclaw/.venv/bin/python3 /home/user/cypherclaw/tools/generation_worker.py`<br/>- `After=cypherclaw-jack.service network-online.target`<br/>- Hardened: `NoNewPrivileges=true`, `ProtectSystem=strict`, `ReadWritePaths=/home/user/cypherclaw-data`<br/>- Documented in runbook |
| CCG-023 | Implement `tools/generation_worker.py` as the standalone async worker entry point. | MUST | T1 | - Loads settings + DB path from env<br/>- Constructs `ReplicateClient`, `GenerationCache`, `GenerationBudget`, `SampleLibrary`, `GenerationStorage`, `GenerationQueue`<br/>- Runs `await queue.run_worker()` under `asyncio.run`<br/>- Handles SIGTERM gracefully — finishes current item, then exits clean<br/>- Tests with subprocess + signal assertion |
| CCG-024 | Implement `/tmp/generation_status.json` diagnostic file written every 30 s by the worker. | MUST | T1 | - File schema: `{queue_depth: int, cache_size_bytes: int, cache_entries: int, today_spent_usd: float, month_spent_usd: float, last_error: {ts, message} \| null, last_success: {ts, hash, model, cost} \| null, worker_pid: int, last_updated: float}`<br/>- Atomic write via temp file + `os.replace`<br/>- Tests assert schema and atomicity |
| CCG-025 | Wire generation status into `operator_diagnostics.py` so the face/inkplate display can show "♫ generating" / "♫ queued: N". | MUST | T2 | - `operator_diagnostics.py::generation_status() -> dict` reads `/tmp/generation_status.json`<br/>- Returns sanitized dict suitable for face/inkplate rendering<br/>- Adds a one-line caption: "♫ generating" when queue depth > 0, "♫ ready" otherwise<br/>- Tests assert reader handles missing/stale/corrupt status file |
| CCG-026 | Extend `usage_journal.jsonl` to tag each played sample by source. | MUST | T1 | - Per-piece journal entry's `samples_used` list gains `source` field per entry<br/>- Sources are exactly: `library`, `self`, `room`, `contact`, `theramini`, `keyboard`, `generated`<br/>- Per-piece summary includes `samples_by_source: {source: count}` aggregation<br/>- Schema migration documented; old entries handled gracefully<br/>- Tests assert source propagation through the journal pipeline |
| CCG-027 | Add `generated_content_dominance` antipattern detector to `render/antipatterns.py`. | MUST | T1 | - Per-piece check: fires when `samples_by_source["generated"] / total_sampler_events > 0.3`<br/>- Rolling-window check: fires when above ratio holds for 7 consecutive days of the last 50 pieces<br/>- Detector returns warning per-piece; rolling violation upgrades to MUST FIX<br/>- Tests with synthetic piece histories cover both thresholds |
| CCG-028 | Implement weekly KL-divergence audit between current IDyOM LTM and a frozen week-0 snapshot. | SHOULD | T2 | - `senseweave/generation/health.py::idyom_kl_divergence_audit() -> AuditReport`<br/>- Runs as cron-style job (`OnCalendar=weekly` systemd timer)<br/>- Loads current LTM and the immutable seed snapshot<br/>- Computes symmetric KL over a fixed test set of melodic n-grams<br/>- AuditReport tracks 8 weeks of values; flags collapse-drift when KL is increasing AND `generated` ratio is high AND CLAP-centroid variance is decreasing<br/>- On flag: writes `/tmp/generation_collapse_alert.json`; does not auto-rollback (operator decision)<br/>- Tests with synthetic LTM time-series cover the conjunction of three signals |
| CCG-029 | Implement self-distance prior on `GenerationConditioner` rejecting requests too similar to recent generations. | MUST | T1 | - `GenerationConditioner.build_request` accepts an optional `recent_generated_centroid: np.ndarray` parameter<br/>- When provided and the cosine distance between the new request's CLAP centroid and `recent_generated_centroid` is < 0.3, perturbs prompt or returns None (caller skips enqueue)<br/>- Perturbation: prepends a randomly-selected fragment from a small pool of "departure" adjectives (e.g. "unexpected", "distant", "novel") seeded by request seed<br/>- Tests cover the threshold check, perturbation determinism, and None-return path |
| CCG-030 | Write operator runbook at `docs/runbooks/generation-backend.md`. | MUST | T2 | - Runbook covers: how to check generation status, how to widen/tighten budget caps, how to switch backend (Replicate ↔ Modal ↔ local), how to roll back IDyOM LTM if collapse audit fires, how to clear stuck queue items, how to inspect cache, where audio + journal land on disk<br/>- Documents the env vars and their default values<br/>- Includes 5 worked-example debugging scenarios |
| CCG-031 | End-to-end smoke test on cypherclaw producing one real generated sample audible in a piece. | MUST | T1 | - `tests/test_generation_e2e_cypherclaw.py` marked `@pytest.mark.cypherclaw_e2e` (skipped on CI, runs on cypherclaw)<br/>- Drives composer with a fixed mode + arc that triggers `_should_queue_now`<br/>- Waits up to 60 s for queue to process; asserts file appears in `samples/generated/`<br/>- Asserts library has `source="generated"` row<br/>- Drives at least 2 more pieces; asserts at least one selects + plays the new generated sample (per `usage_journal.jsonl`)<br/>- Asserts `/tmp/self_listen.json` shows non-zero peak during the piece |
| CCG-032 | Document the cost model and verify steady-state stays under cap for ≥7 consecutive days. | SHOULD | T2 | - `docs/runbooks/generation-backend.md` includes the cost model from spec §5<br/>- A 7-day soak run on cypherclaw produces a daily-spend chart from `generation_status.json` snapshots<br/>- Soak passes when no day exceeds the daily cap; documented in the soak report |

## Acceptance: end-of-PRD demonstration

A piece in **Evening Reflection** mode that includes a sampler event whose
record has `source="generated"`, where:

- The audio file lives at `samples/generated/<yyyy-mm-dd>/<hash>.wav`.
- The piece's `usage_journal.jsonl` entry shows the generated sample
  with its model name, cost, mood/arc tags.
- `/tmp/generation_status.json` shows the daily spend > $0 and < cap,
  cache size > 0, queue depth >= 0.
- The face/inkplate display showed "♫ generating" earlier in the day
  while the queue was active.
- Mode-collapse audit reports clean: `generated` ratio in healthy band
  (0.05–0.3), KL-divergence stable, CLAP-centroid variance stable.
- Removing `REPLICATE_API_TOKEN` from `.env` and restarting the worker
  results in the queue going to `blocked` state with clear diagnostic;
  the composer continues playing pieces with no audible degradation
  (library samples carry the music).

The system has now turned its accumulated taste into new audio. The
fallback principle holds: when generation is unavailable, the music
sounds exactly like Phase 1–4 + the library. When generation is
available, the music includes material the system *has not heard
before* — material conditioned on what it *has* heard.
