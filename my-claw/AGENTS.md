# Agent Instructions — CypherClaw Project

**This is the single source of truth for ALL agents working on this project (Claude, Codex, Gemini, local LLMs). CLAUDE.md points here.**

## Core Tenets

### 1. Test-Driven Development (TDD)

**Every piece of code must have tests. No exceptions.**

- Write tests BEFORE or ALONGSIDE the implementation — never after
- No module ships without a corresponding test file in `tests/`
- Tests must pass before any task is marked complete
- If fixing a bug, write a failing test that reproduces it first, then fix
- E2E integration tests verify components work together, not just in isolation
- Mock external services (Ollama, Telegram, cloud APIs) — never make real calls in tests
- If you see untested code while working, add tests for it

### 2. Verify/Scan/Fix Loop

**Every action must follow this loop:**

1. **DO** the thing (write code, fix bug, change config)
2. **VERIFY** it worked (run tests, check imports, confirm output)
3. **SCAN** for related issues and side effects
4. **FIX** anything found
5. **REPEAT** steps 2-4 until clean
6. Only then mark the task as done

Verification depth scales with risk:
- **Simple** (config, file copy): functional check — did it work?
- **Moderate** (code changes, new features): functional + ripple — verify change AND scan everything it touches
- **Critical** (daemon, watchdog, services): full system health — all imports, gates, services, logs

**Never leave broken things behind.** If you notice an error while working on something else, fix it.

**System stability is the goal.** Every change should leave the system healthier than you found it.

### 3. Read Before You Write

1. **Read AGENTS.md** (this file) for full codebase architecture and API reference
2. **Read the relevant PRD** in `sdp/` — it specifies the design decisions and acceptance criteria
3. **Read existing code** before modifying — understand patterns used in the codebase
4. Write tests, run gates, verify clean before marking done

## Pre-Authorized Actions

These actions are approved in advance — do them without asking:
- **Daemon restart** — kill and restart `cypherclaw_daemon.py` to load new code. Always verify it comes back up.
- **Package installation** — `pip install` in the venv to add missing dependencies
- **File sync** — copy files from main codebase to working directory
- **Service restart** — restart gallery, watchdog, or other supporting services
- **Simple gap fixes** — missing dirs, stale locks, config drift

**Still require approval:** deleting data, modifying secrets/API keys, production deployments to external services.

## Environment

- **Python venv**: Always use `/home/user/cypherclaw/.venv/bin/python` and `/home/user/cypherclaw/.venv/bin/pytest`
- **pip install**: Use `.venv/bin/pip install` — system Python is PEP 668 managed, do NOT use `pip install --break-system-packages`
- **Run tests**: `.venv/bin/pytest tests/ -x`
- **Lint**: `.venv/bin/ruff check tools/`
- **Project root**: `/home/user/cypherclaw`
- **Tools**: `tools/` directory contains all daemon modules
- **sdp-cli**: `/home/user/.local/bin/sdp-cli`

## Available Services

- PostgreSQL: running, databases cypherclaw_observatory, cypherclaw_state, cypherclaw_sdp
- Redis: running on localhost:6379
- Ollama: running on localhost:11434 (models: qwen3.5:9b, qwen3.5:4b, qwen3.5:27b, gemma3:4b, llama3.2:3b, nomic-embed-text)
- Nginx: running

## I/O Safety

This server has limited disk I/O. Follow these rules:
- **NEVER** write large files to disk during builds — use tmpfs at /run/cypherclaw-tmp/
- **NEVER** run multiple concurrent heavy processes — disk I/O will freeze the server
- All temp files go to TMPDIR=/run/cypherclaw-tmp
- Keep commits small and focused
- SQLite databases use WAL mode

## Installed Packages (venv)

Key packages: fastapi, uvicorn, httpx, pillow, numpy, pyyaml, redis, psycopg2-binary, pydantic, mypy, ruff, pytest, hypothesis, Jinja2

## Codebase Architecture

CypherClaw is an always-on AI orchestrator running as a daemon. It coordinates multiple AI agents (Claude, Codex, Gemini) via Telegram, manages a virtual pet system, generates art, and runs an automated task pipeline.

### Core Files

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `tools/cypherclaw_daemon.py` | Main daemon (~2500 lines). Telegram bot, agent routing, health checks, scheduler | `route_message()`, `run_agent()`, `tg_send()` |
| `tools/agent_selector.py` | Fitness-based agent selection with rotation | `AgentSelector.select()` — picks best agent for task category |
| `tools/observatory.py` | Agent metrics, task results, healing log, daily rollups | `Observatory.record_task_result()`, `Observatory.agent_fitness()` |
| `tools/healer.py` | Self-healing engine (severity: SILENT/NOTIFY/ASK) | `Healer.handle_failure()` — dispatches to type-specific handlers |
| `tools/tamagotchi.py` | Virtual pet system — 4 pets (claude, codex, gemini, cypherclaw) | `Pet` class with mood, energy, hunger, stage, XP |
| `tools/effort_router.py` | Effort-based model degradation/escalation | `run_with_effort_escalation()` |
| `tools/researcher.py` | Deep research via agent calls | `Researcher.research()` |
| `tools/server_health.py` | Server metrics (CPU, RAM, disk, I/O) | `get_server_health()` |
| `tools/telegram.py` | Telegram bot API wrapper | `send_message()`, `get_updates()` |
| `tools/gemini_image.py` | Image generation via Gemini | `generate_image(prompt_file)` |
| `tools/local_llm.py` | Ollama wrapper for local LLM calls | calls Ollama API at localhost:11434 |

### GlyphWeave Art System (`tools/glyphweave/`)

ASCII+emoji hybrid art system with a Canvas DSL.

| File | Purpose | Key API |
|------|---------|---------|
| `dsl.py` | Canvas DSL — the foundation for all art | `Canvas(width, height)`, `.place(x,y,char)`, `.place_emoji(x,y,emoji)`, `.place_text(x,y,text)`, `.fill_row(y,char)`, `.fill_region(x,y,w,h,char)`, `.render()` -> string |
| `dsl.py` | Also defines: `Animation(w,h)`, `Motif(w,h,base,accent)` | `.add_frame(canvas)`, `.to_aeaf()` |
| `dsl.py` | Palettes: `PALETTE_WATER`, `PALETTE_SPACE`, `PALETTE_CUTE`, `PALETTE_DRAGON`, `PALETTE_NIGHT`, `PALETTE_UI` | Lists of emoji strings |
| `scenes.py` | Telegram scene rendering | `CypherClawArt` class: `startup_banner()`, `status_display()`, `processing_indicator()`, `pet_status_display()`, `pet_interaction_scene()` |
| `player.py` | AEAF animation player | `AEAFPlayer`, `build_processing_frames()`, `build_spinner_frames()` |
| `pet_sprites.py` | ASCII pet sprite definitions | `SPRITES` dict, `get_frames(agent, state)`, `get_portrait(agent)` |
| `pet_animations.py` | Pet animation sequences | Frame-based pet animations |

### Gallery Display (`tools/gallery/`)

Physical monitor gallery — renders art to the server's attached display.

| File | Purpose |
|------|---------|
| `gallery_display.py` | Main gallery loop — auto-rotates art every 60s, keyboard controls, ArtWatcher for new art |
| `tty_renderer.py` | ANSI text rendering to /dev/tty1 |
| `fb_renderer.py` | Framebuffer pixel rendering to /dev/fb0 (1280x1024, 32bpp) |

Art goes in: `/home/user/cypherclaw/gallery/renders/`
Supported formats: .txt, .ans, .ansi, .asc (text), .png, .jpg, .jpeg, .bmp, .gif, .svg (image)
JSON sidecar files (same name + .json) provide metadata for overlay display.

### Pet System (`tools/tamagotchi.py` + related)

| File | Purpose |
|------|---------|
| `tamagotchi.py` | Core Pet class — mood, energy, hunger, stage, XP, evolution |
| `pet_classes.py` | Class system — pets specialize based on agent behavior |
| `pet_xp_bridge.py` | XP earning from pipeline tasks and agent activity |
| `pet_rebirth.py` | Rebirth cycle when pet stats are critical |
| `pet_snapshots.py` | Daily state snapshots |
| `pet_db_migrate.py` | Database migrations for pet state |

Pet state stored in: `.promptclaw/pets.json`

### Database Locations

| Database | Path | Purpose |
|----------|------|---------|
| Observatory | `.promptclaw/observatory.db` | Agent metrics, task results, healing log, skills |
| SDP state | `.sdp/state.db` | Task queue, dependencies, run history |
| Pet state | `.promptclaw/pets.json` | Virtual pet data |

### PRD Reference

When implementing a task, check if there's a PRD in `sdp/` that specifies the design:

| PRD | Coverage |
|-----|----------|
| `prd-glyphweave-art-studio.md` | Art engine, experimenter, calibration, 30-min cycle |
| `prd-narrative-engine.md` | Story beats, world state, symbols, character arcs, art cycle integration |
| `prd-model-awareness.md` | Model registry, task classifier, per-model fitness |
| `prd-pet-system-v2.md` | XP, classes, personality traits, rebirth, snapshots |
| `prd-web-platform.md` | FastAPI backend, Vue.js SPA, mission control |
| `prd-proactive-intelligence.md` | Cost tracking, project health, morning briefings |
| `prd-verification-system.md` | Risk classification, verification engine |
| `prd-server-optimization.md` | Tmpfs validation, auto-recovery, reboot resilience |
| `prd-introspector.md` | Log scanner, pattern DB, auto-diagnosis, cross-provider verify |
| `prd-gap-analyzer.md` | Code/infra/integration gap detection, TDD enforcement, E2E tests |
| `prd-restructure.md` | Move tools/ to src/cypherclaw/ package |
| `prd-gallery-display.md` | Physical monitor gallery, keyboard controls |

**Always read the relevant PRD before implementing a task from that PRD.**

### Ollama API Usage

```python
import httpx

# Text generation
resp = httpx.post("http://localhost:11434/api/generate", json={
    "model": "qwen3.5:9b",
    "prompt": "your prompt here",
    "stream": False,
    "options": {"temperature": 0.7, "num_predict": 1024},
}, timeout=120)
text = resp.json()["response"]

# Embeddings
resp = httpx.post("http://localhost:11434/api/embeddings", json={
    "model": "nomic-embed-text:latest",
    "prompt": "text to embed",
}, timeout=30)
embedding = resp.json()["embedding"]  # list of floats
```

### Testing Patterns

- Tests go in `tests/` directory
- Use pytest fixtures in `tests/conftest.py`
- Use `tmp_path` fixture for temporary files
- Run gate: `.venv/bin/pytest tests/ -x --tb=short -q`
