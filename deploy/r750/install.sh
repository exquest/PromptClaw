#!/usr/bin/env bash
#
# PromptClaw R750 Fast-Path Install
# =================================
#
# Idempotent single-file installer. Takes a fresh Ubuntu 24.04 LTS
# from "just booted" to "PromptClaw running with dual NUMA-pinned
# Ollama, cloud agent fallback, Tailscale federation, and systemd
# autonomy".
#
# PREREQUISITES (do these manually first):
#   1. Ubuntu 24.04 LTS Server installed (see r750-bare-metal-runbook.md)
#   2. BIOS tuned: SNC off, HT off, System Profile=Performance
#   3. User created with sudo privileges (NOT root)
#   4. Internet access (apt, github, ollama.com, docker.io)
#   5. Tailscale installed and authorized (`sudo tailscale up`)
#   6. (Optional) GitHub PAT exported as GITHUB_TOKEN for private repo clone
#
# USAGE:
#   scp install.sh user@r750:~/
#   ssh user@r750
#   chmod +x install.sh
#   ./install.sh                        # full install
#   ./install.sh --phase=ollama         # run one phase
#   ./install.sh --skip=models          # skip model pull (slow)
#   ./install.sh --verify-only          # just run verification
#
# Phase 7 (pulling models) takes 30-60 minutes depending on network.
# Everything else completes in ~15 minutes.

set -euo pipefail

# ═══════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════

readonly PROMPTCLAW_USER="${SUDO_USER:-${USER}}"
readonly PROMPTCLAW_HOME="/home/${PROMPTCLAW_USER}"
readonly PROMPTCLAW_DIR="${PROMPTCLAW_HOME}/promptclaw"
readonly DATA_DIR="/data/promptclaw"
readonly TMPFS_DIR="/run/promptclaw-tmp"

readonly REPO_URL="${REPO_URL:-https://github.com/exquest/PromptClaw.git}"
readonly REPO_BRANCH="${REPO_BRANCH:-main}"

readonly SDP_CLI_REPO="${SDP_CLI_REPO:-https://github.com/exquest/sdp-cli.git}"
readonly SDP_CLI_BRANCH="${SDP_CLI_BRANCH:-main}"

# Default models — fast-path selection, no full evaluation.
# Chosen for CPU-only dual-NUMA inference on 813GB RAM:
#   - qwen3:30b-a3b   — MoE, only 3B active, fastest 30B on CPU
#   - qwen3-coder:30b — code specialist, same runtime class
#   - nomic-embed-text — embeddings
readonly MODEL_ORCHESTRATOR="qwen3:30b-a3b"
readonly MODEL_CODER="qwen3-coder:30b"
readonly MODEL_EMBEDDINGS="nomic-embed-text:latest"
readonly MODELS_FAST_PATH=(
    "$MODEL_ORCHESTRATOR"
    "$MODEL_CODER"
    "$MODEL_EMBEDDINGS"
)

# Ollama socket-to-port mapping
readonly OLLAMA_PORT_0=11434  # NUMA socket 0
readonly OLLAMA_PORT_1=11435  # NUMA socket 1

# Colors
readonly C_RESET=$'\e[0m'
readonly C_BOLD=$'\e[1m'
readonly C_GREEN=$'\e[32m'
readonly C_YELLOW=$'\e[33m'
readonly C_RED=$'\e[31m'
readonly C_CYAN=$'\e[36m'

# ═══════════════════════════════════════════════════════════════════
# CLI arg parsing
# ═══════════════════════════════════════════════════════════════════

PHASES_TO_RUN="all"
PHASES_TO_SKIP=""
VERIFY_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --phase=*) PHASES_TO_RUN="${1#*=}"; shift ;;
        --skip=*) PHASES_TO_SKIP="${1#*=}"; shift ;;
        --verify-only) VERIFY_ONLY=true; shift ;;
        --help|-h)
            sed -n '/^# USAGE:/,/^# Phase 7/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

log() { printf '%s[%s]%s %s\n' "${C_CYAN}" "$(date +%H:%M:%S)" "${C_RESET}" "$*"; }
ok() { printf '  %s✓%s %s\n' "${C_GREEN}" "${C_RESET}" "$*"; }
warn() { printf '  %s⚠%s %s\n' "${C_YELLOW}" "${C_RESET}" "$*"; }
err() { printf '  %s✗%s %s\n' "${C_RED}" "${C_RESET}" "$*" >&2; }
fail() { err "$*"; exit 1; }

phase() {
    local name="$1"
    printf '\n%s═══ Phase: %s ═══%s\n' "${C_BOLD}" "$name" "${C_RESET}"
}

should_run_phase() {
    local phase_name="$1"
    if [[ ",$PHASES_TO_SKIP," == *",$phase_name,"* ]]; then
        return 1
    fi
    if [[ "$PHASES_TO_RUN" == "all" ]]; then
        return 0
    fi
    if [[ ",$PHASES_TO_RUN," == *",$phase_name,"* ]]; then
        return 0
    fi
    return 1
}

require_not_root() {
    if [[ "$EUID" -eq 0 ]]; then
        fail "Run as a regular user with sudo, not as root directly."
    fi
}

require_sudo() {
    if ! sudo -n true 2>/dev/null; then
        warn "You will be prompted for your sudo password."
        sudo true || fail "sudo required"
    fi
}

# ═══════════════════════════════════════════════════════════════════
# Phase 1: System packages and directories
# ═══════════════════════════════════════════════════════════════════

phase_system() {
    phase "1/13 — System packages and directories"

    log "Updating apt cache..."
    sudo apt update -qq

    log "Installing system packages..."
    sudo apt install -y -qq \
        build-essential git curl wget jq \
        python3 python3-venv python3-pip python3-dev \
        postgresql-client redis-tools \
        nginx sqlite3 \
        numactl htop iotop ncdu tmux \
        ca-certificates gnupg lsb-release
    ok "System packages installed"

    log "Creating directories..."
    sudo mkdir -p \
        "${DATA_DIR}"/{observatory,sdp-state,gallery,logs,artifacts,ollama-0,ollama-1} \
        /etc/promptclaw
    sudo chown -R "${PROMPTCLAW_USER}:${PROMPTCLAW_USER}" "${DATA_DIR}"
    sudo chmod 755 "${DATA_DIR}"

    # tmpfs workdir (recreated on boot)
    sudo install -d -m 1777 "${TMPFS_DIR}"
    mkdir -p "${TMPFS_DIR}/workdir"
    ok "Directories created under ${DATA_DIR}"

    log "Detecting NUMA topology..."
    if ! command -v numactl &>/dev/null; then
        fail "numactl not installed"
    fi
    local node_count
    node_count=$(numactl --hardware | awk '/available:/ {print $2}')
    if [[ "$node_count" -ne 2 ]]; then
        warn "Expected 2 NUMA nodes, found $node_count — dual-Ollama setup assumes 2 sockets"
        warn "Continuing anyway. Check BIOS: Sub-NUMA Clustering should be Disabled."
    else
        ok "NUMA: 2 nodes detected"
    fi
    numactl --hardware | grep -E "node [01] cpus" | sed 's/^/    /'
}

# ═══════════════════════════════════════════════════════════════════
# Phase 2: Docker for datastores (PostgreSQL + Redis)
# ═══════════════════════════════════════════════════════════════════

phase_docker() {
    phase "2/13 — Docker + datastores (PostgreSQL + Redis)"

    if ! command -v docker &>/dev/null; then
        log "Installing Docker..."
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
            sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        sudo chmod a+r /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
            sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        sudo apt update -qq
        sudo apt install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
        sudo usermod -aG docker "${PROMPTCLAW_USER}"
        ok "Docker installed"
    else
        ok "Docker already installed"
    fi

    log "Writing datastore compose file..."
    sudo tee /etc/promptclaw/datastore-compose.yml > /dev/null <<'COMPOSE'
version: "3.8"
services:
  postgres:
    image: postgres:16
    container_name: promptclaw-postgres
    restart: always
    environment:
      POSTGRES_USER: inference
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: langgraph
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - /data/promptclaw/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U inference"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: promptclaw-redis
    restart: always
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - /data/promptclaw/redis:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
COMPOSE
    ok "Compose file written"

    if [[ ! -f /etc/promptclaw/datastore.env ]]; then
        log "Generating datastore credentials..."
        local pg_pass
        pg_pass=$(openssl rand -hex 16)
        sudo tee /etc/promptclaw/datastore.env > /dev/null <<ENV
POSTGRES_PASSWORD=${pg_pass}
ENV
        sudo chmod 600 /etc/promptclaw/datastore.env
        ok "Credentials generated (saved to /etc/promptclaw/datastore.env)"
    else
        ok "Credentials already exist"
    fi

    log "Writing datastore systemd unit..."
    sudo tee /etc/systemd/system/promptclaw-datastore.service > /dev/null <<UNIT
[Unit]
Description=PromptClaw Datastore (PostgreSQL + Redis)
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
EnvironmentFile=/etc/promptclaw/datastore.env
ExecStart=/usr/bin/docker compose -f /etc/promptclaw/datastore-compose.yml up -d
ExecStop=/usr/bin/docker compose -f /etc/promptclaw/datastore-compose.yml down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
UNIT
    sudo systemctl daemon-reload
    sudo systemctl enable --now promptclaw-datastore.service
    ok "Datastore systemd unit active"

    log "Waiting for PostgreSQL to be ready..."
    local tries=30
    while ((tries > 0)); do
        if docker exec promptclaw-postgres pg_isready -U inference &>/dev/null; then
            ok "PostgreSQL ready"
            break
        fi
        sleep 2
        ((tries--))
    done
    ((tries == 0)) && fail "PostgreSQL never became ready"
}

# ═══════════════════════════════════════════════════════════════════
# Phase 3: Ollama install + dual-socket systemd units
# ═══════════════════════════════════════════════════════════════════

phase_ollama() {
    phase "3/13 — Ollama + dual-socket systemd units"

    if ! command -v ollama &>/dev/null; then
        log "Installing Ollama..."
        curl -fsSL https://ollama.com/install.sh | sudo sh
        ok "Ollama binary installed"
    else
        ok "Ollama already installed ($(ollama --version 2>&1 | head -1))"
    fi

    # Disable the default service — we manage our own NUMA-pinned units
    if systemctl list-unit-files | grep -q '^ollama.service'; then
        log "Disabling default ollama.service..."
        sudo systemctl disable --now ollama.service 2>/dev/null || true
        ok "Default service disabled"
    fi

    # Detect NUMA nodes
    local node0_cpus node1_cpus
    node0_cpus=$(numactl --hardware | awk '/node 0 cpus:/ {$1=""; $2=""; $3=""; print}' | xargs | tr ' ' ',')
    node1_cpus=$(numactl --hardware | awk '/node 1 cpus:/ {$1=""; $2=""; $3=""; print}' | xargs | tr ' ' ',')

    if [[ -z "$node0_cpus" ]]; then
        fail "Could not detect NUMA node 0 CPUs"
    fi

    log "Writing ollama-0.service (NUMA 0, port ${OLLAMA_PORT_0})..."
    sudo tee /etc/systemd/system/ollama-0.service > /dev/null <<UNIT
[Unit]
Description=Ollama Socket 0 (NUMA node 0)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${PROMPTCLAW_USER}
Group=${PROMPTCLAW_USER}
Environment="OLLAMA_HOST=127.0.0.1:${OLLAMA_PORT_0}"
Environment="OLLAMA_MODELS=${DATA_DIR}/ollama-0"
Environment="OLLAMA_NUM_THREAD=12"
Environment="OLLAMA_KEEP_ALIVE=24h"
Environment="OLLAMA_MAX_LOADED_MODELS=3"
ExecStart=/usr/bin/numactl --cpunodebind=0 --membind=0 /usr/local/bin/ollama serve
Restart=always
RestartSec=5
LimitNOFILE=65536
LimitMEMLOCK=infinity

[Install]
WantedBy=multi-user.target
UNIT

    if [[ -n "$node1_cpus" ]]; then
        log "Writing ollama-1.service (NUMA 1, port ${OLLAMA_PORT_1})..."
        sudo tee /etc/systemd/system/ollama-1.service > /dev/null <<UNIT
[Unit]
Description=Ollama Socket 1 (NUMA node 1)
After=network-online.target ollama-0.service
Wants=network-online.target

[Service]
Type=simple
User=${PROMPTCLAW_USER}
Group=${PROMPTCLAW_USER}
Environment="OLLAMA_HOST=127.0.0.1:${OLLAMA_PORT_1}"
Environment="OLLAMA_MODELS=${DATA_DIR}/ollama-1"
Environment="OLLAMA_NUM_THREAD=12"
Environment="OLLAMA_KEEP_ALIVE=24h"
Environment="OLLAMA_MAX_LOADED_MODELS=3"
ExecStart=/usr/bin/numactl --cpunodebind=1 --membind=1 /usr/local/bin/ollama serve
Restart=always
RestartSec=5
LimitNOFILE=65536
LimitMEMLOCK=infinity

[Install]
WantedBy=multi-user.target
UNIT
    else
        warn "Skipping ollama-1.service — no NUMA node 1 detected"
    fi

    sudo systemctl daemon-reload
    sudo systemctl enable --now ollama-0.service
    [[ -n "$node1_cpus" ]] && sudo systemctl enable --now ollama-1.service

    log "Waiting for Ollama instances..."
    local tries=30
    while ((tries > 0)); do
        if curl -sf "http://127.0.0.1:${OLLAMA_PORT_0}/api/version" >/dev/null 2>&1; then
            ok "Ollama socket 0 responding on port ${OLLAMA_PORT_0}"
            break
        fi
        sleep 2
        ((tries--))
    done
    ((tries == 0)) && fail "Ollama socket 0 never responded"

    if [[ -n "$node1_cpus" ]]; then
        tries=30
        while ((tries > 0)); do
            if curl -sf "http://127.0.0.1:${OLLAMA_PORT_1}/api/version" >/dev/null 2>&1; then
                ok "Ollama socket 1 responding on port ${OLLAMA_PORT_1}"
                break
            fi
            sleep 2
            ((tries--))
        done
        ((tries == 0)) && fail "Ollama socket 1 never responded"
    fi
}

# ═══════════════════════════════════════════════════════════════════
# Phase 4: Pull fast-path models
# ═══════════════════════════════════════════════════════════════════

phase_models() {
    phase "4/13 — Pulling fast-path models (${#MODELS_FAST_PATH[@]} models)"

    log "This takes 30-60 minutes. Models are cached per-socket."

    for model in "${MODELS_FAST_PATH[@]}"; do
        log "Pulling ${model} on socket 0..."
        OLLAMA_HOST="http://127.0.0.1:${OLLAMA_PORT_0}" \
            ollama pull "${model}" || warn "Failed to pull ${model} on socket 0"
    done
    ok "Socket 0 models pulled"

    if systemctl is-active ollama-1.service &>/dev/null; then
        for model in "${MODELS_FAST_PATH[@]}"; do
            log "Pulling ${model} on socket 1..."
            OLLAMA_HOST="http://127.0.0.1:${OLLAMA_PORT_1}" \
                ollama pull "${model}" || warn "Failed to pull ${model} on socket 1"
        done
        ok "Socket 1 models pulled"
    fi
}

# ═══════════════════════════════════════════════════════════════════
# Phase 5: Clone PromptClaw repo
# ═══════════════════════════════════════════════════════════════════

phase_clone() {
    phase "5/13 — Clone PromptClaw repository"

    if [[ -d "${PROMPTCLAW_DIR}/.git" ]]; then
        log "Updating existing clone..."
        cd "${PROMPTCLAW_DIR}"
        git fetch origin --quiet
        git checkout "${REPO_BRANCH}"
        git pull --ff-only origin "${REPO_BRANCH}" || warn "Pull failed — keeping local state"
        ok "Repo updated"
    else
        log "Cloning ${REPO_URL} (branch ${REPO_BRANCH})..."
        local clone_url="${REPO_URL}"
        if [[ -n "${GITHUB_TOKEN:-}" ]]; then
            clone_url="${REPO_URL/https:\/\//https://oauth2:${GITHUB_TOKEN}@}"
        fi
        git clone --branch "${REPO_BRANCH}" "${clone_url}" "${PROMPTCLAW_DIR}"
        ok "Repo cloned to ${PROMPTCLAW_DIR}"
    fi

    # Convenience symlink so tools can be invoked from /home/$USER/promptclaw/tools/
    if [[ ! -e "${PROMPTCLAW_DIR}/tools" ]]; then
        ln -sf "${PROMPTCLAW_DIR}/my-claw/tools" "${PROMPTCLAW_DIR}/tools"
        ok "tools/ symlink created"
    fi
}

# ═══════════════════════════════════════════════════════════════════
# Phase 6: Python venv + dependencies
# ═══════════════════════════════════════════════════════════════════

phase_venv() {
    phase "6/13 — Python venv and dependencies"

    if [[ ! -d "${PROMPTCLAW_DIR}/.venv" ]]; then
        log "Creating venv..."
        python3 -m venv "${PROMPTCLAW_DIR}/.venv"
        ok "venv created"
    else
        ok "venv exists"
    fi

    log "Upgrading pip..."
    "${PROMPTCLAW_DIR}/.venv/bin/pip" install --quiet --upgrade pip setuptools wheel

    log "Installing Python dependencies..."
    "${PROMPTCLAW_DIR}/.venv/bin/pip" install --quiet \
        httpx pillow psycopg2-binary redis structlog \
        python-osc pygame numpy scipy \
        pytest pytest-asyncio

    if [[ -f "${PROMPTCLAW_DIR}/pyproject.toml" ]]; then
        log "Installing PromptClaw package..."
        "${PROMPTCLAW_DIR}/.venv/bin/pip" install --quiet -e "${PROMPTCLAW_DIR}" || \
            warn "Editable install failed — continuing with path-based imports"
    fi
    ok "Python deps installed"
}

# ═══════════════════════════════════════════════════════════════════
# Phase 7: Install sdp-cli
# ═══════════════════════════════════════════════════════════════════

phase_sdp_cli() {
    phase "7/13 — Install sdp-cli"

    local sdp_cli_dir="${PROMPTCLAW_HOME}/sdp-cli"
    if [[ -d "${sdp_cli_dir}/.git" ]]; then
        log "Updating sdp-cli..."
        cd "${sdp_cli_dir}"
        git fetch origin --quiet
        git checkout "${SDP_CLI_BRANCH}"
        git pull --ff-only origin "${SDP_CLI_BRANCH}" || warn "Pull failed"
    else
        log "Cloning sdp-cli..."
        local clone_url="${SDP_CLI_REPO}"
        if [[ -n "${GITHUB_TOKEN:-}" ]]; then
            clone_url="${SDP_CLI_REPO/https:\/\//https://oauth2:${GITHUB_TOKEN}@}"
        fi
        git clone --branch "${SDP_CLI_BRANCH}" "${clone_url}" "${sdp_cli_dir}"
    fi

    log "Installing sdp-cli to ${PROMPTCLAW_HOME}/.local..."
    pip3 install --user --quiet -e "${sdp_cli_dir}"

    # Verify
    if "${PROMPTCLAW_HOME}/.local/bin/sdp-cli" --version &>/dev/null; then
        ok "sdp-cli installed: $("${PROMPTCLAW_HOME}/.local/bin/sdp-cli" --version)"
    else
        fail "sdp-cli install failed"
    fi
}

# ═══════════════════════════════════════════════════════════════════
# Phase 8: Observatory schema
# ═══════════════════════════════════════════════════════════════════

phase_observatory() {
    phase "8/13 — Observatory PostgreSQL schema"

    # shellcheck disable=SC1091
    source /etc/promptclaw/datastore.env

    log "Creating observatory schema..."
    PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h 127.0.0.1 -U inference -d langgraph <<'SQL'
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    data JSONB
);

CREATE TABLE IF NOT EXISTS task_results (
    id SERIAL PRIMARY KEY,
    agent TEXT NOT NULL,
    task_id TEXT,
    success BOOLEAN NOT NULL,
    duration_ms INTEGER,
    tokens INTEGER,
    gate_pass BOOLEAN,
    category TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_skills (
    id SERIAL PRIMARY KEY,
    agent TEXT NOT NULL,
    category TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0.5,
    sample_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent, category)
);

CREATE TABLE IF NOT EXISTS daily_rollups (
    id SERIAL PRIMARY KEY,
    agent TEXT NOT NULL,
    date DATE NOT NULL,
    tasks_completed INTEGER DEFAULT 0,
    tasks_failed INTEGER DEFAULT 0,
    tokens_used INTEGER DEFAULT 0,
    total_duration_ms INTEGER DEFAULT 0,
    gate_passes INTEGER DEFAULT 0,
    UNIQUE(agent, date)
);

CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(event_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_task_results_agent ON task_results(agent, timestamp);
CREATE INDEX IF NOT EXISTS idx_agent_skills_lookup ON agent_skills(agent, category);

INSERT INTO agent_skills (agent, category, score, sample_count) VALUES
    ('ollama', 'architecture', 0.65, 0),
    ('ollama', 'review',       0.60, 0),
    ('ollama', 'coding',       0.70, 0),
    ('ollama', 'research',     0.65, 0),
    ('ollama', 'routing',      0.70, 0),
    ('ollama', 'writing',      0.70, 0),
    ('ollama', 'testing',      0.65, 0),
    ('ollama', 'devops',       0.60, 0),
    ('ollama', 'netops',       0.80, 0)
ON CONFLICT (agent, category) DO NOTHING;

SELECT 'Observatory schema ready' AS status;
SQL
    ok "Schema created"
}

# ═══════════════════════════════════════════════════════════════════
# Phase 9: .env and .sdp configuration
# ═══════════════════════════════════════════════════════════════════

phase_config() {
    phase "9/13 — PromptClaw .env and .sdp config"

    # shellcheck disable=SC1091
    source /etc/promptclaw/datastore.env

    if [[ ! -f "${PROMPTCLAW_DIR}/.env" ]]; then
        log "Writing .env template..."
        cat > "${PROMPTCLAW_DIR}/.env" <<ENV
# PromptClaw R750 environment

# Datastores
DATABASE_URL=postgresql://inference:${POSTGRES_PASSWORD}@localhost:5432/langgraph
REDIS_URL=redis://localhost:6379/0

# Ollama — dual socket
OLLAMA_URL=http://localhost:11434
OLLAMA_URL_SOCKET0=http://localhost:11434
OLLAMA_URL_SOCKET1=http://localhost:11435

# Mode: fully local inference on the R750
LOCAL_ONLY=true

# Cloud agent creds (optional fallback — leave empty to stay fully local)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
ENV
        chmod 600 "${PROMPTCLAW_DIR}/.env"
        ok ".env written (edit to add optional cloud creds)"
    else
        ok ".env already exists"
    fi

    # Symlink persistent state into the repo dir
    mkdir -p "${PROMPTCLAW_DIR}/.sdp" "${PROMPTCLAW_DIR}/.promptclaw"
    if [[ ! -L "${PROMPTCLAW_DIR}/.promptclaw/db" ]]; then
        ln -sfn "${DATA_DIR}/observatory" "${PROMPTCLAW_DIR}/.promptclaw/db"
    fi
    if [[ ! -L "${PROMPTCLAW_DIR}/.sdp/persistent" ]]; then
        ln -sfn "${DATA_DIR}/sdp-state" "${PROMPTCLAW_DIR}/.sdp/persistent"
    fi
    ok "State symlinks in place"
}

# ═══════════════════════════════════════════════════════════════════
# Phase 10: (Optional) Cloud CLIs for fallback
# ═══════════════════════════════════════════════════════════════════

phase_cloud_clis() {
    phase "10/13 — Cloud CLIs (optional fallback)"

    if [[ "${LOCAL_ONLY:-true}" == "true" ]]; then
        ok "Skipping cloud CLIs (LOCAL_ONLY mode)"
        return 0
    fi

    if ! command -v npm &>/dev/null; then
        log "Installing Node.js + npm for cloud CLIs..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt install -y -qq nodejs
    fi

    log "Installing Claude Code CLI..."
    sudo npm install -g @anthropic-ai/claude-code 2>&1 | tail -3 || warn "Claude CLI install failed"

    log "Installing Gemini CLI..."
    sudo npm install -g @google/generative-ai-cli 2>&1 | tail -3 || warn "Gemini CLI install failed"

    log "Installing Codex CLI..."
    sudo npm install -g @openai/codex 2>&1 | tail -3 || warn "Codex CLI install failed"

    for cli in claude codex gemini; do
        if command -v "$cli" &>/dev/null; then
            ok "$cli: $(command -v "$cli")"
        else
            warn "$cli: not found on PATH"
        fi
    done
}

# ═══════════════════════════════════════════════════════════════════
# Phase 11: systemd services for PromptClaw
# ═══════════════════════════════════════════════════════════════════

phase_systemd() {
    phase "11/13 — PromptClaw systemd services"

    log "Writing promptclaw-bootstrap.service..."
    sudo tee /etc/systemd/system/promptclaw-bootstrap.service > /dev/null <<UNIT
[Unit]
Description=PromptClaw Bootstrap — tmpfs workspace init
After=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=${PROMPTCLAW_USER}
ExecStartPre=+/usr/bin/install -d -m 1777 ${TMPFS_DIR}
ExecStart=/bin/bash -c 'mkdir -p ${TMPFS_DIR}/workdir'

[Install]
WantedBy=multi-user.target
UNIT

    log "Writing promptclaw-daemon.service..."
    sudo tee /etc/systemd/system/promptclaw-daemon.service > /dev/null <<UNIT
[Unit]
Description=PromptClaw Daemon
After=network-online.target ollama-0.service promptclaw-datastore.service
Wants=ollama-0.service promptclaw-datastore.service
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=${PROMPTCLAW_USER}
Group=${PROMPTCLAW_USER}
WorkingDirectory=${PROMPTCLAW_DIR}
EnvironmentFile=${PROMPTCLAW_DIR}/.env
Environment=PATH=${PROMPTCLAW_HOME}/.local/bin:${PROMPTCLAW_DIR}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=${PROMPTCLAW_DIR}/my-claw/tools:${PROMPTCLAW_DIR}/src
Environment=PYTHONUNBUFFERED=1
Environment=TMPDIR=${TMPFS_DIR}
ExecStart=${PROMPTCLAW_DIR}/.venv/bin/python3 ${PROMPTCLAW_DIR}/my-claw/tools/cypherclaw_daemon.py
Restart=always
RestartSec=10
TimeoutStopSec=30
MemoryMax=16G

[Install]
WantedBy=multi-user.target
UNIT

    log "Writing promptclaw-sdp-runner.service..."
    sudo tee /etc/systemd/system/promptclaw-sdp-runner.service > /dev/null <<UNIT
[Unit]
Description=PromptClaw SDP Runner
After=promptclaw-bootstrap.service promptclaw-daemon.service
Requires=promptclaw-bootstrap.service

[Service]
Type=simple
User=${PROMPTCLAW_USER}
WorkingDirectory=${PROMPTCLAW_DIR}
EnvironmentFile=${PROMPTCLAW_DIR}/.env
Environment=HOME=${PROMPTCLAW_HOME}
Environment=PATH=${PROMPTCLAW_HOME}/.local/bin:${PROMPTCLAW_DIR}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=TMPDIR=${TMPFS_DIR}
Environment=PYTHONPATH=${PROMPTCLAW_HOME}/sdp-cli/src
Environment=PYTHONUNBUFFERED=1
Environment=TERM=dumb
ExecStart=${PROMPTCLAW_HOME}/.local/bin/sdp-cli orchestrate --start-phase development --end-phase development
Restart=always
RestartSec=30
SuccessExitStatus=75
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

    sudo systemctl daemon-reload
    sudo systemctl enable promptclaw-bootstrap.service
    sudo systemctl enable promptclaw-daemon.service
    sudo systemctl enable promptclaw-sdp-runner.service
    ok "systemd units installed and enabled"
}

# ═══════════════════════════════════════════════════════════════════
# Phase 12: Start everything
# ═══════════════════════════════════════════════════════════════════

phase_start() {
    phase "12/13 — Starting PromptClaw services"

    log "Starting bootstrap..."
    sudo systemctl start promptclaw-bootstrap.service
    ok "Bootstrap complete"

    log "Starting daemon..."
    sudo systemctl start promptclaw-daemon.service || warn "Daemon start returned non-zero"
    sleep 3
    if systemctl is-active promptclaw-daemon.service &>/dev/null; then
        ok "Daemon active"
    else
        warn "Daemon not active — check: journalctl -u promptclaw-daemon"
    fi

    log "Starting SDP runner..."
    sudo systemctl start promptclaw-sdp-runner.service || warn "SDP runner start returned non-zero"
    sleep 3
    if systemctl is-active promptclaw-sdp-runner.service &>/dev/null; then
        ok "SDP runner active"
    else
        warn "SDP runner not active — check: journalctl -u promptclaw-sdp-runner"
    fi
}

# ═══════════════════════════════════════════════════════════════════
# Phase 13: Verification
# ═══════════════════════════════════════════════════════════════════

phase_verify() {
    phase "13/13 — Verification"

    local failures=0

    log "Checking directories..."
    [[ -d "${PROMPTCLAW_DIR}" ]] && ok "PromptClaw dir" || { err "PromptClaw dir missing"; ((failures++)); }
    [[ -d "${DATA_DIR}" ]] && ok "Data dir" || { err "Data dir missing"; ((failures++)); }

    log "Checking services..."
    for svc in promptclaw-datastore ollama-0 promptclaw-bootstrap promptclaw-daemon promptclaw-sdp-runner; do
        if systemctl is-active "${svc}.service" &>/dev/null; then
            ok "${svc} active"
        else
            warn "${svc} not active"
            ((failures++))
        fi
    done

    if systemctl list-unit-files | grep -q '^ollama-1.service'; then
        if systemctl is-active ollama-1.service &>/dev/null; then
            ok "ollama-1 active"
        else
            warn "ollama-1 not active"
        fi
    fi

    log "Checking Ollama endpoints..."
    if curl -sf "http://localhost:${OLLAMA_PORT_0}/api/version" >/dev/null; then
        local version
        version=$(curl -s "http://localhost:${OLLAMA_PORT_0}/api/version" | jq -r .version)
        ok "Ollama socket 0: ${version}"
    else
        err "Ollama socket 0 not responding"; ((failures++))
    fi

    if curl -sf "http://localhost:${OLLAMA_PORT_1}/api/version" >/dev/null 2>&1; then
        ok "Ollama socket 1 responding"
    fi

    log "Checking loaded models..."
    local loaded
    loaded=$(curl -s "http://localhost:${OLLAMA_PORT_0}/api/tags" | jq -r '.models[].name' 2>/dev/null | tr '\n' ' ')
    if [[ -n "$loaded" ]]; then
        ok "Models on socket 0: ${loaded}"
    else
        warn "No models loaded on socket 0 (phase 4 may be pending)"
    fi

    log "Checking PostgreSQL..."
    # shellcheck disable=SC1091
    source /etc/promptclaw/datastore.env
    if PGPASSWORD="${POSTGRES_PASSWORD}" psql -h 127.0.0.1 -U inference -d langgraph \
        -tAc "SELECT COUNT(*) FROM agent_skills WHERE agent='ollama';" 2>/dev/null | grep -q "^9$"; then
        ok "Observatory schema populated"
    else
        warn "Observatory schema incomplete"
        ((failures++))
    fi

    log "Running Ollama smoke test..."
    local smoke_response
    smoke_response=$(curl -s "http://localhost:${OLLAMA_PORT_0}/api/generate" \
        -d "{\"model\":\"${MODEL_ORCHESTRATOR}\",\"prompt\":\"Say 'hello' and nothing else.\",\"stream\":false,\"options\":{\"num_predict\":10}}" \
        2>/dev/null | jq -r .response 2>/dev/null || echo "")
    if [[ -n "$smoke_response" ]]; then
        ok "Ollama smoke test: \"${smoke_response:0:60}\""
    else
        warn "Ollama smoke test failed — model may not be pulled yet"
    fi

    echo
    if ((failures == 0)); then
        printf '%s╔══════════════════════════════════════════════╗%s\n' "${C_GREEN}" "${C_RESET}"
        printf '%s║  PromptClaw R750 install complete  ✓        ║%s\n' "${C_GREEN}" "${C_RESET}"
        printf '%s╚══════════════════════════════════════════════╝%s\n' "${C_GREEN}" "${C_RESET}"
        echo
        echo "Next steps:"
        echo "  1. Edit ${PROMPTCLAW_DIR}/.env to add optional cloud creds"
        echo "  2. Load a PRD:    sdp-cli analyze --prd path/to/prd.md --load"
        echo "  3. Check status:  sdp-cli status"
        echo "  4. Watch logs:    journalctl -u promptclaw-daemon -f"
        echo "  5. Federate with CypherClaw via Tailscale once both peers are up"
    else
        printf '%s╔══════════════════════════════════════════════╗%s\n' "${C_YELLOW}" "${C_RESET}"
        printf '%s║  Install completed with %d warning(s)        ║%s\n' "${C_YELLOW}" "$failures" "${C_RESET}"
        printf '%s╚══════════════════════════════════════════════╝%s\n' "${C_YELLOW}" "${C_RESET}"
        echo
        echo "Review warnings above. Common fixes:"
        echo "  - sudo systemctl restart promptclaw-daemon.service"
        echo "  - journalctl -u promptclaw-daemon -n 50"
        echo "  - Re-run a phase: $0 --phase=daemon"
        exit 1
    fi
}

# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

main() {
    require_not_root

    if [[ "${VERIFY_ONLY}" == "true" ]]; then
        phase_verify
        exit $?
    fi

    log "PromptClaw R750 fast-path install"
    log "User:       ${PROMPTCLAW_USER}"
    log "Target dir: ${PROMPTCLAW_DIR}"
    log "Data dir:   ${DATA_DIR}"
    log "Phases:     ${PHASES_TO_RUN}"
    [[ -n "${PHASES_TO_SKIP}" ]] && log "Skipping:   ${PHASES_TO_SKIP}"

    require_sudo

    should_run_phase "system"     && phase_system
    should_run_phase "docker"     && phase_docker
    should_run_phase "ollama"     && phase_ollama
    should_run_phase "models"     && phase_models
    should_run_phase "clone"      && phase_clone
    should_run_phase "venv"       && phase_venv
    should_run_phase "sdp-cli"    && phase_sdp_cli
    should_run_phase "observatory" && phase_observatory
    should_run_phase "config"     && phase_config
    should_run_phase "cloud-clis" && phase_cloud_clis
    should_run_phase "systemd"    && phase_systemd
    should_run_phase "start"      && phase_start
    phase_verify
}

main "$@"
