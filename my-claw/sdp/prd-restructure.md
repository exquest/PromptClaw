# PRD: Restructure CypherClaw to Standard Python Package Layout

## Overview

Restructure CypherClaw from the non-standard `tools/` flat layout to a standard Python `src/` package layout. This is the highest priority task because the non-standard layout causes every sdp-cli agent to fail — they expect `src/`, standard imports, and `pip install -e .` to work. Every PRD task after this will benefit from the fix.

**Depends on:** `prd-home-resilience.md` (finish the queue/runtime authority work first so the restructure does not happen on a brittle foundation)

**Current structure (broken):**
```
cypherclaw/
├── tools/
│   ├── cypherclaw_daemon.py
│   ├── tamagotchi.py
│   ├── observatory.py
│   ├── healer.py
│   ├── server_health.py
│   ├── io_watchdog.py
│   ├── agent_selector.py
│   ├── researcher.py
│   ├── context_pulse.py
│   ├── reviewer.py
│   ├── lifeimprover_bridge.py
│   ├── glyphweave/
│   │   ├── __init__.py
│   │   ├── dsl.py
│   │   ├── scenes.py
│   │   ├── player.py
│   │   ├── pet_animations.py
│   │   └── pet_sprites.py
│   └── workspace/
├── tests/
├── sdp/
├── docs/
└── pyproject.toml
```

**Target structure (standard):**
```

## Execution Role

This is **Stage 2** of the execution spine. It begins only after the Home Resilience core is in place.

This PRD unblocks:

- `prd-model-awareness.md`
- `prd-verification-system.md`
- `prd-agent-runtime-substrate.md`
- `prd-context-engine.md`
- `prd-capability-approval-framework.md`
- `prd-introspector.md`
- `prd-web-platform.md`

If the import graph and packaging stay unstable, every later agent, verifier, and service task inherits avoidable failure modes.
cypherclaw/
├── src/
│   └── cypherclaw/
│       ├── __init__.py
│       ├── daemon.py          (was cypherclaw_daemon.py)
│       ├── tamagotchi.py
│       ├── observatory.py
│       ├── healer.py
│       ├── server_health.py
│       ├── io_watchdog.py
│       ├── agent_selector.py
│       ├── researcher.py
│       ├── context_pulse.py
│       ├── reviewer.py
│       ├── lifeimprover_bridge.py
│       ├── glyphweave/
│       │   ├── __init__.py
│       │   ├── dsl.py
│       │   ├── scenes.py
│       │   ├── player.py
│       │   ├── pet_animations.py
│       │   └── pet_sprites.py
│       └── web/              (future web platform)
├── tests/
├── sdp/
├── docs/
├── pyproject.toml
└── CLAUDE.md
```

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| RS-001 | Create the `src/cypherclaw/` package directory. Move all Python modules from `tools/` to `src/cypherclaw/`. Create `__init__.py` with package version. Rename `cypherclaw_daemon.py` to `daemon.py`. Move `glyphweave/` subdirectory intact. Do NOT move `workspace/` — it stays as a working directory, not part of the package. | MUST | T2 | - `src/cypherclaw/` exists with all modules<br/>- `__init__.py` created with `__version__`<br/>- All .py files from tools/ present in src/cypherclaw/<br/>- glyphweave/ subdirectory intact<br/>- workspace/ NOT moved |
| RS-002 | Update all internal imports. Change every `from tamagotchi import` to `from cypherclaw.tamagotchi import`, every `from observatory import` to `from cypherclaw.observatory import`, etc. Update all relative imports within glyphweave/. Search all .py files for import statements that reference the old flat structure and fix them. | MUST | T2 | - All imports use `cypherclaw.` prefix<br/>- `python -c "from cypherclaw.daemon import *"` works<br/>- `python -c "from cypherclaw.tamagotchi import PetManager"` works<br/>- No ImportError on any module<br/>- `.venv/bin/pytest tests/ -x` passes |
| RS-003 | Update `pyproject.toml` for the new layout. Set `[tool.setuptools.packages.find]` to `where = ["src"]`. Update the package name, add console_scripts entry point for the daemon if appropriate. Run `.venv/bin/pip install -e ".[dev]"` and verify it succeeds. | MUST | T1 | - `pip install -e ".[dev]"` succeeds<br/>- `python -c "import cypherclaw"` works after install<br/>- Package version accessible via `cypherclaw.__version__` |
| RS-004 | Update the systemd service file to reference the new daemon path. Change `ExecStart` from `tools/cypherclaw_daemon.py` to either `python3 -m cypherclaw.daemon` or the new `src/cypherclaw/daemon.py` path. Ensure the daemon starts correctly after the change. | MUST | T1 | - systemd service updated<br/>- `sudo systemctl daemon-reload`<br/>- `sudo systemctl restart cypherclaw` succeeds<br/>- Daemon starts and responds to Telegram |
| RS-005 | Update all path references in the codebase. Search for hardcoded paths like `tools/`, `TOOLS_DIR`, `PROJECT_ROOT` and update them. Update: `LOG_FILE`, `WORKSPACE_DIR`, `OBSERVATORY_DB`, `PETS_FILE`, and any other path constants. Ensure paths work from both the disk repo and the tmpfs working copy. | MUST | T2 | - No references to `tools/` in import paths<br/>- Path constants updated<br/>- Daemon log still writes correctly<br/>- Observatory DB still accessible<br/>- Workspace artifacts still work |
| RS-006 | Update tests to use the new import paths. All test files in `tests/` should import from `cypherclaw.` package. Run the full test suite and fix any failures. | MUST | T1 | - All tests import from `cypherclaw.*`<br/>- `.venv/bin/pytest tests/ -x` passes<br/>- No import errors in test collection |
| RS-007 | Update the tmpfs working copy init script, sync script, and cron jobs. Ensure `init_workdir.sh` creates the correct structure in tmpfs. Ensure `sync_workdir.sh` pushes from the right paths. Update any cron references to `tools/`. | MUST | T1 | - `init_workdir.sh` works with new structure<br/>- `sync_workdir.sh` syncs correctly<br/>- `io_guard.sh` still runs<br/>- `pipeline_watchdog.sh` still runs<br/>- All cron jobs work |
| RS-008 | Update CLAUDE.md and AGENTS.md to reflect the new structure. Remove all references to `tools/` layout. Document the standard `src/cypherclaw/` import pattern. | MUST | T1 | - CLAUDE.md reflects new structure<br/>- AGENTS.md updated<br/>- No references to old `tools/` layout |

## Implementation Notes

- This should be done in a SINGLE commit to avoid partial breakage
- The `tools/` directory should be removed after all modules are moved (or renamed to `tools_old/` temporarily)
- Keep `tools/workspace/` as a separate working directory (symlink or move to project root)
- Keep `tools/healthcheck.sh`, `tools/io_guard.sh`, `tools/pipeline_watchdog.sh`, `tools/sync_workdir.sh`, `tools/init_workdir.sh` as shell scripts in a `scripts/` directory
- The daemon should be runnable as both `python3 src/cypherclaw/daemon.py` and `python3 -m cypherclaw.daemon`

## Success Metrics

| Metric | Target |
|--------|--------|
| All imports work | `python -c "from cypherclaw.daemon import *"` — no errors |
| Tests pass | `.venv/bin/pytest tests/ -x` — all pass |
| Daemon starts | `systemctl restart cypherclaw` — active |
| sdp-cli gates pass | ruff + pytest gates pass on first try |
| Pipeline tasks stop escalating | Next 5 tasks complete without escalation |
