# PromptClaw v3.0

```text
 /\_/\
( o.o )  PromptClaw v3.0 🦀✨🧠
 > ^ <   coherence engine + constitutional enforcement
```

PromptClaw v3.0 is a markdown-first, artifact-driven, multi-agent orchestrator with built-in **coherence enforcement**. It ensures multiple AI agents (Claude, Codex, Gemini, etc.) produce consistent outputs, respect architectural decisions, and follow constitutional rules — automatically.

## What's New in v3.0

### Coherence Engine (core feature)
Every PromptClaw project now gets coherence enforcement built in:

- **Event-sourced state** — append-only event log (SQLite or PostgreSQL) replaces JSON files. Full audit trail and replay.
- **Decision memory** — record Architecture Decision Records (ADRs). Relevant decisions are automatically injected into agent prompts before every action.
- **Constitutional enforcement** — define hard/soft rules in YAML or JSON. Agent outputs are evaluated against rules at every phase.
- **Trust scoring** — per-agent trust (0.0–1.0). Violations penalize, compliance rewards. Low-trust agents are deprioritized in routing.
- **Self-graduating enforcement** — starts in monitor mode (log only), auto-promotes to soft (block hard violations) then full (block all) based on detection confidence.

### 7 Orchestrator Hooks
The coherence engine hooks into every phase of the orchestration flow:

| Hook | Phase | What It Does |
|------|-------|-------------|
| A | Pre-routing | Inject decision context into routing |
| B | Post-routing | Validate route against constitution |
| C | Pre-lead | Inject constraints into lead prompt |
| D | Post-lead | Assess output against rules + decisions |
| E | Pre-verify | Inject criteria into verify prompt |
| F | Post-verify | Override verdict on constitutional violation |
| G | Finalize | Full compliance audit, graduation check |

## Quick Start

### 1) Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Optional: PostgreSQL + Redis + pgvector support
pip install -e ".[coherence-pg]"
```

### 2) Create a project

```bash
promptclaw init my-claw --name "My PromptClaw"
cd my-claw
```

The startup wizard asks questions one at a time and configures your agents.

### 3) Add a constitution (optional)

Create `constitution.json` in your project root:

```json
{
  "rules": [
    {
      "id": "no-secrets",
      "severity": "hard",
      "description": "Never include API keys or secrets in output",
      "pattern": "(api[_-]?key|secret|password|token)\\s*[:=]\\s*\\S+",
      "applies_to": ["lead", "verify"],
      "message": "Output contains what appears to be a secret"
    }
  ]
}
```

### 4) Record architectural decisions

```bash
promptclaw coherence record-decision . \
  --title "Use PostgreSQL for all durable state" \
  --context "Need ACID transactions and vector search" \
  --decision "PostgreSQL with pgvector extension" \
  --rationale "Eliminates ChromaDB dependency, single transactional system" \
  --tags database,storage
```

These decisions are automatically surfaced in agent prompts when relevant.

### 5) Run tasks

```bash
promptclaw run . --task "Implement user authentication"
promptclaw status .
```

The coherence engine logs all events, evaluates outputs against your constitution, and tracks agent trust scores — all automatically.

### 6) Check coherence health

```bash
promptclaw coherence status .      # Enforcement mode, trust scores
promptclaw coherence decisions .   # Active architectural decisions
promptclaw coherence doctor .      # Validate coherence system health
promptclaw coherence replay . --run-id <id>  # Event replay for a run
```

## Commands

```bash
# Project management
promptclaw init PATH [--name NAME] [--no-wizard]
promptclaw wizard PROJECT_ROOT
promptclaw doctor PROJECT_ROOT
promptclaw bootstrap PROJECT_ROOT

# Task execution
promptclaw run PROJECT_ROOT --task-file FILE
promptclaw run PROJECT_ROOT --task "free text task"
promptclaw resume PROJECT_ROOT --run-id RUN_ID --answer "answer"
promptclaw status PROJECT_ROOT [--run-id RUN_ID]
promptclaw show-config PROJECT_ROOT

# Coherence
promptclaw coherence status PROJECT_ROOT
promptclaw coherence decisions PROJECT_ROOT
promptclaw coherence record-decision PROJECT_ROOT --title ... --decision ...
promptclaw coherence replay PROJECT_ROOT --run-id RUN_ID
promptclaw coherence doctor PROJECT_ROOT
```

## Project Structure

```text
promptclaw/
├── promptclaw/
│   ├── coherence/              # Coherence engine
│   │   ├── engine.py           # CoherenceEngine (7 hooks)
│   │   ├── event_store.py      # SQLite + PostgreSQL backends
│   │   ├── decision_store.py   # ADR storage + retrieval
│   │   ├── constitution.py     # Rule loading + evaluation
│   │   ├── trust.py            # Per-agent trust scoring
│   │   ├── graduation.py       # Self-graduating enforcement
│   │   └── prompt_injection.py # Context formatting for prompts
│   ├── orchestrator.py         # Core orchestration with hooks
│   ├── router.py               # Trust-aware agent routing
│   ├── agent_runtime.py        # Agent execution (mock/command)
│   ├── state_store.py          # JSON + event-sourced state
│   ├── cli.py                  # CLI commands
│   └── ...
├── examples/
│   ├── constitution.json       # Example constitution
│   └── coherence-demo/         # Demo project with coherence
├── tests/                      # 120+ tests
├── docs/
│   ├── coherence-foundations.md # Research foundations
│   └── ...
└── pyproject.toml
```

## Design Principles

- **Artifact-based handoffs** — agents communicate through files, not direct chat
- **Constitutional governance** — rules enforced at infrastructure level, not just prompts
- **Event sourcing** — all state derived from immutable event log
- **Progressive enforcement** — monitor first, enforce after confidence is established
- **Trust but verify** — agents earn trust through compliant behavior
- **Backward compatible** — works with zero config, zero dependencies (SQLite fallback)

## Configuration

Add coherence settings to `promptclaw.json`:

```json
{
  "coherence": {
    "enabled": true,
    "database_url": "",
    "redis_url": "",
    "constitution_path": "constitution.json",
    "enforcement_mode": "monitor",
    "auto_graduate": true
  }
}
```

## Docs

- `docs/coherence-foundations.md` — research basis (60+ papers)
- `docs/architecture.md` — system design
- `docs/build-your-own-promptclaw.md` — custom claw guide
- `docs/configuration-reference.md` — all config options
- `docs/command-reference.md` — CLI reference
