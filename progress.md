# Session Handoff — 2026-04-08 (Day 5: Face Terminal + R750 Prep)

## What Was Built This Session

### 1. Face Terminal (keyboard_chat.py)
Complete rewrite from chat overlay to daemon-backed face terminal.

**Final architecture:** The face is a thin client. Keyboard input writes to the daemon inbox (`/run/cypherclaw-tmp/inbox.jsonl`). The daemon (2750-line `src/cypherclaw/daemon.py`) routes messages through Claude/Gemini/Codex with conversation memory, budget management, and smart routing. Responses come back via a shared message bus (`/tmp/cypherclaw_messages.jsonl`) that the face reads.

**What's on the face:**
- **Typing** — just start typing, no toggle. Words appear right-aligned below the face.
- **Responses** — daemon responses float left-aligned (blue). Same agents as Telegram.
- **Telegram mirror** — daemon's `tg_send()` patched to also write to face bus. Everything sent to Telegram shows on the face.
- **System events** — key changes, mood shifts, art generation, Theramini activity appear centered in amber.
- **Thinking animation** — orbiting particles, expanding ripples, and LLM-generated musings (qwen3.5:4b) while waiting for daemon response.
- **Chat history** — Tab toggles scrollable history from daemon conversation memory.
- **Emoji stripping** — PIL can't render emoji, so they're stripped from bus messages.

**Key files on CypherClaw:**
- `/home/user/cypherclaw/tools/senseweave/keyboard_chat.py` — face terminal module
- `/home/user/cypherclaw/tools/face_display.py` — patched: calls `chat.poll_system()`, `chat.poll_message_bus()`, `chat.render()`
- `/home/user/cypherclaw/src/cypherclaw/daemon.py` — patched: `_face_bus()` mirrors `tg_send()` to message bus

### 2. Audio Fixes
- Disconnected webcam + Scarlett inputs from SuperCollider (caused occasional pops via USB audio glitches)
- Commented out input connections in `scripts/start_audio.sh` so they don't return on reboot
- Inputs should be reconnected only when Theramini duet or contact mic listener is ready

### 3. Artist's Plan Completion PRD
New PRD (`prd-artist-plan-completion.md`) with 14 requirements covering gaps:
- **APC-001--005:** Visitor identity (face recognition, person registry, greeting)
- **APC-006--009:** Physical output (fix printer, sound postcards, daily digest, welcome stickers)
- **APC-010--011:** Gallery exhibition mode (curated sequences)
- **APC-012--013:** Room acoustics (swept sine IR, convolution reverb SynthDef)
- **APC-014:** B&P color covers via DreamShaper

### 4. Artist's Plan Rectified
Updated `artist-plan.md`: PipeWire not JACK, 21 chars not 15, Pareidolia not GlyphWeave, added Inner Life section, marked phase completion percentages, cross-referenced covering PRDs.

### 5. R750 Ollama Integration (built by local SDP pipeline)
12 tasks completed (all PASS), building the code for R750 deployment:
- `ollama_health.py` — health check + model listing for dual-socket Ollama
- `federation/discovery.py` — Tailscale peer discovery with registry merge
- `cypherclaw_daemon.py` — `_invoke_ollama()` HTTP invoke, `run_agent()` Ollama branch, `LOCAL_ONLY` mode, `_available_agents()` respects health + quota
- `quota_monitor.py` — local provider infinite headroom, Ollama models in PROVIDERS
- `first_boot.py` — instance identity with artistic name generation (already existed on CypherClaw)
- 11 new test files covering all Ollama integration paths

### 6. CypherClaw Day 1-4 Build Committed
64 files (11,907 insertions) committed on CypherClaw and synced to PromptClaw repo. This was the entire Day 1-4 build that was sitting uncommitted.

## Pipeline State

### CypherClaw SDP
- **531 total tasks, 434 complete (82%)**
- Runner active (`sdp-cli run --force`)
- 32 pending, 55 needs_split, 9 blocked, 84 skipped
- ETA ~7 hours (2 AM tomorrow)
- Loaded PRDs: artist-plan-completion (14 tasks), embodiment-core (13), embodiment-interaction-loops (12), clone (14), identity (9), federation-read (9), federation-writes (7), bundle-exchange (8), publication (10)

### Local MacBook SDP
- **14/14 complete (100%)** — R750 Ollama integration
- Runner stopped (work is done)
- R750 PRD: `my-claw/sdp/prd-r750-ollama-integration.md`

## Running Services on CypherClaw
- `scsynth` (PipeWire, port 57110)
- `duet_composer.py` (music with Korsakov Ch.1-4)
- `face_display.py` (face terminal + chat)
- `cypherclaw daemon` (Telegram bot, multi-agent routing)
- `sdp-cli run` (SDP pipeline runner)
- Art engine, gallery, web gallery, all sensor daemons

**NOT running:**
- `telegram_commands.py` — killed because it conflicted with daemon (409 errors). The daemon handles all Telegram.
- Inner life loop — was built but not started this session (needs to be added to boot script)

## What Needs Attention

### Immediate
1. **Start inner life loop on CypherClaw** — `tools/inner_life/main.py` is built but not in the boot script or running as a daemon
2. **telegram_commands.py keeps respawning** — it was killed but something may restart it. Check if a systemd unit or cron is respawning it. The daemon handles Telegram — telegram_commands should stay disabled.
3. **Face display sometimes has two processes** — kill both and restart one cleanly
4. **APC-010/011 need_split** — gallery exhibition tasks flagged as too broad, the pipeline will auto-split them

### R750 Deployment
The integration code is built and tested. When deploying:
1. Complete bare metal runbook (`docs/r750-bare-metal-runbook.md`)
2. Run model evaluation plan (`docs/r750-model-evaluation-plan.md`)
3. Update model names in `OLLAMA_MODELS` routing config (currently placeholders)
4. SCP the modified files to R750
5. Set `LOCAL_ONLY=true` in `.env` for full local inference mode

### Keyboard Chat on CypherClaw
The face terminal is working but could use:
- Better font rendering (consider rendering text to a separate surface for anti-aliasing)
- The `expression_override` property exists on `KeyboardChat` — wire it into `face_display.py` so the face goes "curious" while thinking
- Long daemon responses get cut off — consider word-wrapping at render time (already implemented but test with real long responses)

## Key Architectural Decisions Made This Session

1. **Face is a thin client** — no LLM calls, no Telegram polling. All intelligence goes through the daemon. The daemon is the single source of truth for conversation.
2. **Message bus pattern** — JSONL append files for inter-process communication. Simple, atomic, no dependencies.
3. **Thinking animation uses local LLM** — qwen3.5:4b generates contextual musings while the real agents work. Nice UX, trivial cost.
4. **Two pipelines in parallel** — CypherClaw runs the main task queue, MacBook runs R750 prep. Different PRDs, different queues, same codebase.

## Git State
- **PromptClaw** (MacBook): `feat/graceful-degradation` branch, pushed to GitHub
- **CypherClaw**: `agent/t1/demo-day-caveats` branch, pushed to cypherclaw-private
- These are different repos (`exquest/PromptClaw` vs `exquest/cypherclaw-private`) with overlapping content under different directory structures (`my-claw/tools/` vs `tools/`)
