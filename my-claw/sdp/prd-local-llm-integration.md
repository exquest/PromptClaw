# PRD: Local LLM Integration — CypherClaw Self-Hosted Intelligence

## Overview

Deploy a multi-model local LLM stack on CypherClaw's home server (12 cores, 62GB RAM, CPU-only) to provide instant routing, code generation, vision assessment, and general text tasks without cloud API latency or cost. The stack uses Ollama for multi-model management plus a dedicated llamafile classification server for sub-200ms routing. During a calibration period, local and cloud models run in parallel to build confidence scores before gradually shifting traffic to local where quality is sufficient.

**Depends on:** `prd-model-awareness.md` (model registry, model selector, fitness scoring), `prd-glyphweave-art-studio.md` (art generation pipeline, vision assessment)

**Reference:** `docs/local-llm-research.md` (research document with full model catalog and benchmarks)

## Hardware Profile

| Resource | Spec | Constraint |
|----------|------|-----------|
| CPU | 12 cores @ 3.2GHz | Memory-bandwidth-bound, not compute-bound |
| RAM | 62 GB | 48 GB budget for LLMs (14 GB reserved for OS + daemon + agents) |
| Disk | 1.8 TB SSD | Model files stored on disk, inference in RAM via mlock |
| GPU | None | CPU-only inference; all estimates assume this |
| Memory bandwidth | ~51 GB/s (estimated DDR4-3200 dual-channel) | Verify with `dmidecode` — this is the #1 performance variable |

## Model Stack

### Always-Loaded Trio (~16 GB)

| Role | Model | Quant | RAM | Est. tok/s | Ollama Tag |
|------|-------|-------|-----|-----------|------------|
| Router / classifier | Qwen3.5-4B | Q4_K_M | ~2.5 GB | ~12-16 | `qwen3.5:4b` |
| Coder / generator / summarizer | Qwen3.5-9B | Q5_K_M | ~6-7 GB | ~5-8 | `qwen3.5:9b` |
| Vision assessor | Gemma 3 4B | Q4_K_M | ~3 GB | ~15-19 text, ~25-35s/image | `gemma3:4b` |

### On-Demand Heavyweight (~16 GB, loaded when needed)

| Role | Model | Quant | RAM | Est. tok/s | Ollama Tag |
|------|-------|-------|-----|-----------|------------|
| Complex coding / architecture | Qwen3.5-27B | Q4_K_M | ~16 GB | ~2-3 | `qwen3.5:27b` |

### Dedicated Classification Server (llamafile)

| Role | Model | Quant | RAM | Threads | Port |
|------|-------|-------|-----|---------|------|
| Fast routing | Qwen3.5-4B | Q4_K_M | ~2.5 GB | 4 (reserved) | 8081 |

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| LLM-001 | Verify server memory configuration by running `sudo dmidecode -t memory` and recording channel count, speed, and type. This determines all performance expectations. Update the model stack configuration if memory bandwidth differs from the assumed 51 GB/s (DDR4-3200 dual-channel). If DDR5 or quad-channel, 14B models become viable as always-loaded; if single-channel, downgrade coder to 4B. | MUST | T1 | - Memory config documented<br/>- Expected tok/s updated based on actual bandwidth<br/>- Model stack adjusted if needed |
| LLM-002 | Configure Ollama for multi-model serving. Set environment variables in Ollama's systemd service: `OLLAMA_MAX_LOADED_MODELS=3`, `OLLAMA_KEEP_ALIVE=30m`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_NUM_PARALLEL=1`. Verify Ollama uses mlock to keep loaded models in RAM (default behavior). Set CPU governor to performance mode. | MUST | T1 | - Ollama systemd override created with all env vars<br/>- `ollama ps` shows 3 models loaded simultaneously<br/>- CPU governor set to performance<br/>- mlock verified via `cat /proc/<pid>/status \| grep VmLck` |
| LLM-003 | Pull the four recommended models one at a time with I/O monitoring between each pull. Monitor disk I/O via the watchdog during pulls — if I/O exceeds 70%, pause and wait. Models: `qwen3.5:4b`, `qwen3.5:9b`, `gemma3:4b`, `qwen3.5:27b`. After each pull, verify the model loads and responds to a test prompt. Remove the old `llama3.2:3b` model after all new models are verified. | MUST | T1 | - All 4 models pulled successfully<br/>- Each model responds to test prompt<br/>- I/O watchdog shows no spikes above 70% during pulls<br/>- `ollama list` shows all 4 models<br/>- llama3.2:3b removed |
| LLM-004 | Install and configure llamafile as a dedicated classification server. Download the llamafile binary and Qwen3.5-4B GGUF file. Create a systemd service `cypherclaw-router.service` that runs llamafile on port 8081 with 4 reserved threads, 2048 context size, and JSON grammar constraint. The service should start after Ollama, restart on failure, and use ionice/nice to limit I/O priority. | MUST | T2 | - llamafile binary installed at `/usr/local/bin/llamafile`<br/>- GGUF model file stored at `/home/user/models/qwen3.5-4b-q4_k_m.gguf`<br/>- systemd service created and enabled<br/>- Server responds on port 8081 to OpenAI-compatible API<br/>- JSON output validated<br/>- Test classification returns in <200ms |
| LLM-005 | Create `tools/local_llm.py` — a unified client for both Ollama and llamafile. The client provides: `classify(text) -> dict` (uses llamafile on :8081 for sub-200ms routing), `generate_code(prompt, model=None) -> str` (uses Ollama, defaults to qwen3.5:9b), `assess_image(image_path, rubric) -> dict` (uses Ollama gemma3:4b), `generate_text(prompt, model=None) -> str` (uses Ollama, defaults to qwen3.5:9b), `generate_heavy(prompt) -> str` (loads qwen3.5:27b on demand). All methods include timeout, retry, and error handling. Use the OpenAI-compatible API for both Ollama (port 11434) and llamafile (port 8081). | MUST | T2 | - `classify()` returns JSON with category and confidence in <500ms<br/>- `generate_code()` returns valid Python code<br/>- `assess_image()` returns scores for 5 criteria<br/>- `generate_text()` returns coherent text<br/>- `generate_heavy()` triggers 27B model load<br/>- All methods handle timeouts and connection errors gracefully<br/>- OpenAI-compatible API used throughout |
| LLM-006 | Integrate local classification into daemon routing. Replace the current cloud-based routing call in `route_message()` with `local_llm.classify()` via llamafile. The classifier should categorize messages as simple/standard/complex and return a routing decision (which agent/model should handle it). Fall back to cloud routing (haiku/flash) if llamafile is unavailable or returns low confidence (<0.7). | MUST | T2 | - Routing uses llamafile by default<br/>- Routing latency drops from 2-8s to <500ms<br/>- Fallback to cloud on llamafile failure<br/>- Low-confidence results (<0.7) escalate to cloud router<br/>- Routing accuracy logged to Observatory for comparison |
| LLM-007 | Integrate local code generation into GlyphWeave art pipeline. The art engine (GW-001) should support local models as a generation option: `qwen3.5:9b` for standard art, `qwen3.5:27b` for complex pieces. The art experimenter (GW-007) should include local models in its calibration grid alongside cloud models. Local generation should use the same two-phase pipeline (plan + generate) with the same validation and retry loop. | SHOULD | T2 | - Art engine accepts `model_id="local:qwen3.5:9b"` parameter<br/>- Local models included in GlyphWeave calibration grid<br/>- Two-phase generation works with local models<br/>- Validation/retry loop functions identically to cloud<br/>- Art scores for local models tracked separately in experiment DB |
| LLM-008 | Integrate local vision assessment into GlyphWeave pipeline. The art assessor (GW-003) should support Gemma 3 4B via Ollama as an assessment option alongside cloud vision models. Images should be resized to 800px max before sending to reduce encoding time. Assessment should be async — queue the image, process score when ready (~25-35s). Results stored alongside cloud assessments for calibration comparison. | SHOULD | T2 | - Art assessor accepts `assessor_model="local:gemma3:4b"` parameter<br/>- Images resized to 800px before local assessment<br/>- Assessment runs async (doesn't block art generation)<br/>- Scores stored with model identifier for comparison<br/>- Timeout of 60s with graceful fallback to cloud |
| LLM-009 | Implement the local-vs-cloud calibration framework. For each use case (routing, code gen, vision, text gen), run both local and cloud models on the same inputs during a calibration period. Track: accuracy/quality score, latency, cost savings. Compute a confidence score per local model per task type. When local confidence exceeds a configurable threshold (default 0.8), start shifting traffic: 80% local / 20% cloud (for ongoing comparison). Store all comparison data in the PostgreSQL art repository's `model_art_scores` table (extended for local models). | MUST | T2 | - Same inputs sent to both local and cloud during calibration<br/>- Per-model per-task confidence scores computed<br/>- Traffic shift triggers at configurable threshold<br/>- 80/20 split after confidence reached<br/>- Comparison data queryable from gallery dashboard<br/>- Cost savings tracked (local = $0 vs cloud token costs) |
| LLM-010 | Add local models to the model registry (from model-awareness PRD). Register all local models with their capabilities: provider="local-ollama" or provider="local-llamafile", with correct speed ratings, cost_tier="free", context windows, and strength lists. The model selector should consider local models alongside cloud models when picking the best model for a task, factoring in the zero-cost advantage. | MUST | T2 | - All local models registered in model_registry<br/>- Provider field distinguishes local-ollama vs local-llamafile<br/>- cost_tier="free" for all local models<br/>- Model selector considers local models in selection<br/>- Speed ratings reflect actual measured tok/s |
| LLM-011 | Create Ollama health monitoring. Add Ollama status to the I/O watchdog: check that Ollama is running, which models are loaded, memory usage per model. If Ollama becomes unresponsive, restart it via systemd. Add Ollama metrics to the Redis metrics store: loaded_models, total_model_ram, ollama_responsive. Show Ollama status in `/health` command output. | MUST | T1 | - Watchdog checks Ollama health every 30s<br/>- Auto-restart on unresponsive Ollama<br/>- Ollama metrics in Redis<br/>- `/health` shows loaded models and Ollama RAM usage<br/>- llamafile health also monitored |
| LLM-012 | Add `/local` command to Telegram. Subcommands: `/local` (show loaded models, RAM usage, status), `/local bench` (run a quick benchmark: classify a test message, generate a short code snippet, time both), `/local stats` (show calibration comparison — local vs cloud accuracy/latency per task type). | SHOULD | T2 | - `/local` shows Ollama model list with RAM per model<br/>- `/local bench` runs and reports classification + generation times<br/>- `/local stats` shows local vs cloud comparison table<br/>- Commands respond within 30s |
| LLM-013 | Benchmark actual performance after model pull. Run standardized benchmarks for each model and record results: (1) Classification: 10 test messages, measure avg latency via llamafile. (2) Code generation: 5 Canvas DSL prompts, measure avg tok/s and code validity rate via qwen3.5:9b. (3) Vision: 3 test images, measure avg assessment time via gemma3:4b. (4) Heavy coding: 2 complex prompts via qwen3.5:27b, measure tok/s. Store results in PostgreSQL for the calibration baseline. | MUST | T1 | - All 4 benchmarks run successfully<br/>- Results stored in PostgreSQL<br/>- Actual tok/s recorded per model<br/>- Classification latency <500ms confirmed<br/>- Results accessible via `/local bench` |
| LLM-014 | Implement model-load-aware I/O protection. When Ollama loads the 27B model on demand (~16 GB read from disk), the I/O watchdog should temporarily raise its kill threshold to avoid false-positive agent kills during model loading. Detect model loading via Ollama API (`/api/ps` shows loading state) and suppress I/O alerts for up to 60 seconds during loads. After loading completes, restore normal thresholds. | SHOULD | T2 | - Watchdog detects Ollama model loading state<br/>- I/O kill threshold temporarily raised during model loads<br/>- Alert suppression lasts max 60s<br/>- Normal thresholds restored after load completes<br/>- Loading events logged to Observatory |
| LLM-015 | Configure Ollama and llamafile to minimize disk I/O during operation. Ensure mlock is enabled (models stay in RAM after load). Set Ollama's model storage to the main disk but verify that inference temp files go to tmpfs (`TMPDIR=/run/cypherclaw-tmp`). Set llamafile's `--no-mmap` flag if needed to force full model load to RAM. Verify with `lsof` and `strace` that no disk reads occur during steady-state inference. | MUST | T1 | - mlock confirmed for all loaded models<br/>- No disk reads during steady-state inference (verified via strace sample)<br/>- Ollama TMPDIR set to tmpfs<br/>- llamafile fully loaded in RAM<br/>- lsof shows no open handles to model files during inference |
| LLM-016 | Copy the local LLM research document to the server at `/home/user/cypherclaw/docs/local-llm-research.md`. This serves as reference for the model selection rationale and benchmark expectations. | MUST | T1 | - Document present on server at specified path |

## Implementation Phases

### Phase 1: Infrastructure (LLM-001, LLM-002, LLM-003, LLM-015, LLM-016)
Verify hardware, configure Ollama, pull models safely, verify zero disk I/O during inference. No integration yet — just a working local LLM stack.

### Phase 2: Interfaces (LLM-004, LLM-005, LLM-011)
Set up llamafile classification server, create the unified Python client, add health monitoring. Local models accessible via API but not yet wired into the daemon.

### Phase 3: Integration (LLM-006, LLM-007, LLM-008, LLM-010, LLM-014)
Wire local routing into the daemon, local code gen into GlyphWeave, local vision into art assessment. Add to model registry. I/O-aware model loading.

### Phase 4: Calibration (LLM-009, LLM-013)
Run benchmarks, start local-vs-cloud comparison, build confidence scores. Gradually shift traffic to local where quality is sufficient.

### Phase 5: Commands & Visibility (LLM-012)
Telegram commands for monitoring local model status, benchmarks, and calibration stats.

## Disk I/O Safety

Every requirement in this PRD must respect the jbd2 constraint:

- **Model pulls**: One at a time, with I/O watchdog monitoring. Pause if >70%.
- **Model loading**: Temporary I/O spike (up to 16GB read for 27B). Watchdog suppresses alerts during loads.
- **Inference**: Zero disk I/O. Models locked in RAM via mlock. Verified via strace.
- **llamafile**: Full model loaded to RAM on startup. No disk access during operation.
- **Ollama temp files**: Directed to tmpfs, not disk.

## RAM Budget

| Component | RAM | When |
|-----------|-----|------|
| OS + daemon + agents + Docker | ~14 GB | Always |
| Qwen3.5-4B (Ollama, always loaded) | ~2.5 GB | Always |
| Qwen3.5-9B (Ollama, always loaded) | ~6-7 GB | Always |
| Gemma 3 4B vision (Ollama, always loaded) | ~3 GB | Always |
| Qwen3.5-4B (llamafile, always loaded) | ~2.5 GB | Always |
| KV caches (4 models) | ~1-2 GB | Always |
| **Normal operation total** | **~30-32 GB** | |
| **Free** | **~30 GB** | |
| Qwen3.5-27B (on demand, replaces 9B) | ~16 GB | On demand |
| **Peak operation total** | **~42-44 GB** | |
| **Free at peak** | **~18 GB** | |

## Success Metrics

| Metric | Target |
|--------|--------|
| Classification latency (llamafile) | <200ms |
| Classification accuracy | >85% vs cloud router |
| Code generation validity (qwen3.5:9b) | >50% first-attempt valid |
| Vision assessment time | <35s per image |
| Routing cloud calls eliminated | >80% after calibration |
| Server stability | Zero jbd2 freezes from LLM operations |
| Model availability | >99% uptime for always-loaded trio |
