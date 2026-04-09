# PromptClaw R750 Fast-Path Deployment

Single-file installer that takes a fresh Ubuntu 24.04 LTS install from
"just booted" to "PromptClaw running with dual NUMA-pinned Ollama,
LOCAL_ONLY inference mode, and systemd autonomy" in ~15 minutes (plus
30-60 minutes for model pulls).

## Prerequisites

Before running this, complete manually:

1. **Ubuntu 24.04 LTS Server** installed via iDRAC virtual media (see
   `../../docs/r750-bare-metal-runbook.md` for BIOS tuning and install)
2. **BIOS settings applied**:
   - Hyperthreading: OFF
   - Sub-NUMA Clustering: OFF
   - System Profile: Performance
   - C-states: C1 only
3. **Regular sudo user** (not root)
4. **Internet access** for apt, GitHub, ollama.com, docker hub
5. **Tailscale** installed and authorized:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```

## Usage

```bash
# Copy installer over
scp deploy/r750/install.sh user@r750:~/

# SSH in
ssh user@r750

# Full install (default)
chmod +x install.sh
./install.sh

# Or with GitHub token for private repo clone
GITHUB_TOKEN=ghp_... ./install.sh

# Phase-by-phase (useful for debugging)
./install.sh --phase=system
./install.sh --phase=ollama
./install.sh --phase=models

# Skip slow model pulls, start PromptClaw with no models loaded
./install.sh --skip=models

# Just run verification
./install.sh --verify-only
```

## What It Does

| Phase | Name | What | Time |
|-------|------|------|------|
| 1 | system | apt packages, /data/promptclaw, tmpfs dir, NUMA check | 2 min |
| 2 | docker | Docker CE, PostgreSQL 16 + Redis 7 via compose | 3 min |
| 3 | ollama | Ollama binary + dual NUMA-pinned systemd units | 2 min |
| 4 | models | Pull qwen3:30b-a3b, qwen3-coder:30b, nomic-embed-text on both sockets | 30-60 min |
| 5 | clone | Clone PromptClaw repo to ~/promptclaw | 1 min |
| 6 | venv | Python venv + httpx, pillow, psycopg2, redis, pytest, etc. | 2 min |
| 7 | sdp-cli | Clone and editable-install sdp-cli to ~/.local | 1 min |
| 8 | observatory | Create PostgreSQL schema for observatory + agent_skills | <1 min |
| 9 | config | Write .env from template, symlink .sdp/.promptclaw state | <1 min |
| 10 | cloud-clis | (Optional) Install claude/codex/gemini CLIs for cloud fallback | 2 min |
| 11 | systemd | Install and enable promptclaw-daemon + promptclaw-sdp-runner units | <1 min |
| 12 | start | systemctl start everything | 1 min |
| 13 | verify | Check services, endpoints, loaded models, smoke test Ollama | <1 min |

## Fast-Path Model Selection

The installer pulls three models by default — skipping the 7-day
evaluation plan. These are chosen for good-enough CPU-only inference
on dual-socket 813GB RAM:

| Model | Size | Role | Why |
|-------|------|------|-----|
| `qwen3:30b-a3b` | ~18 GB | orchestrator, default | MoE, only 3B params active per token — fastest 30B on CPU |
| `qwen3-coder:30b` | ~18 GB | coding | Code-specialized, same runtime class |
| `nomic-embed-text` | ~275 MB | embeddings | Memory store, narrative retrieval |

You can add more models later with `ollama pull` once production traffic
tells you what's actually needed. To run the full evaluation plan
instead, see `../../docs/r750-model-evaluation-plan.md`.

## Default Mode: LOCAL_ONLY

The installer writes `LOCAL_ONLY=true` to `.env`, meaning the daemon
uses only Ollama agents with no cloud API calls. To enable cloud
fallback:

```bash
# Edit .env
nano ~/promptclaw/.env
# Set LOCAL_ONLY=false and fill in API keys

# Install cloud CLIs (skipped by default)
./install.sh --phase=cloud-clis

# Restart daemon
sudo systemctl restart promptclaw-daemon.service
```

## Federation with CypherClaw

Once the R750 is running and both hosts are on the same Tailscale
network, the R750 will auto-discover CypherClaw as a peer:

```bash
# Check peer registry
cat ~/.promptclaw/federation/peers.json

# Manually trigger a scan
~/promptclaw/.venv/bin/python -c \
  "from promptclaw.federation.discovery import discover_peers; print(discover_peers())"
```

The R750 mints its own instance identity at first boot (UUID + artistic
name) and stores it at `~/.promptclaw/identity.json`. It will NOT auto-
announce to the federation unless `FEDERATION_MODE=federated` is set in
`.env` — default is standalone for safety.

## Troubleshooting

### Install failed partway through
The installer is idempotent. Just re-run it:
```bash
./install.sh
```
Already-installed phases are detected and skipped.

### Service not starting
```bash
sudo systemctl status promptclaw-daemon.service
journalctl -u promptclaw-daemon -n 50
```

### Ollama not responding
```bash
sudo systemctl status ollama-0.service ollama-1.service
curl http://localhost:11434/api/version
curl http://localhost:11435/api/version
```

### Circuit breaker blocks SDP runner
The sdp-cli fix (commit 98da2b4 on feature/monitor-compact-audit-grouping)
auto-closes the breaker after a successful task. If you see the runner
hot-looping:
```bash
sdp-cli circuit reset
sdp-cli circuit status
```

### Model pulls interrupted
Just re-run phase 4:
```bash
./install.sh --phase=models
```
Ollama resumes partial downloads.

## Uninstall

```bash
sudo systemctl disable --now promptclaw-daemon promptclaw-sdp-runner \
    promptclaw-bootstrap promptclaw-datastore ollama-0 ollama-1
sudo rm /etc/systemd/system/promptclaw-*.service \
    /etc/systemd/system/ollama-{0,1}.service
sudo systemctl daemon-reload
sudo rm -rf /data/promptclaw /etc/promptclaw
rm -rf ~/promptclaw ~/sdp-cli
```

## Files Produced

| Location | What |
|----------|------|
| `~/promptclaw/` | PromptClaw git clone |
| `~/sdp-cli/` | sdp-cli git clone (editable install) |
| `~/.local/bin/sdp-cli` | sdp-cli entry point |
| `~/promptclaw/.env` | Config (secrets) |
| `~/promptclaw/.venv/` | Python virtualenv |
| `~/.promptclaw/identity.json` | Instance identity (minted on first daemon run) |
| `~/.promptclaw/federation/peers.json` | Federation peer registry |
| `/data/promptclaw/` | Persistent data (DBs, observatory, models, logs) |
| `/data/promptclaw/ollama-0/` | Socket 0 model cache |
| `/data/promptclaw/ollama-1/` | Socket 1 model cache |
| `/data/promptclaw/observatory/` | Observatory SQLite (if used) |
| `/etc/promptclaw/datastore.env` | PostgreSQL password |
| `/etc/promptclaw/datastore-compose.yml` | PG + Redis compose file |
| `/etc/systemd/system/ollama-0.service` | NUMA 0 Ollama |
| `/etc/systemd/system/ollama-1.service` | NUMA 1 Ollama |
| `/etc/systemd/system/promptclaw-*.service` | Daemon, SDP runner, bootstrap, datastore |
| `/run/promptclaw-tmp/` | tmpfs workspace |
