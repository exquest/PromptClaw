# PromptClaw Application Deployment Plan — Dell PowerEdge R750

**Prerequisite:** The bare metal runbook (`r750-bare-metal-runbook.md`) has been completed. Ubuntu 24.04 is installed, dual Ollama instances are running on ports 11434/11435, PostgreSQL and Redis are healthy, and Tailscale is connected.

**Goal:** Deploy PromptClaw on the R750 with Ollama as a first-class agent alongside the existing cloud CLI agents (claude, codex, gemini). No architectural rewrites — extend the existing daemon to route tasks to local models.

---

## Part 1: Clone and Configure PromptClaw

### 1.1 Create the deployment user and directories

```bash
# Use your existing user (created during Ubuntu install), not root
mkdir -p ~/cypherclaw
mkdir -p /data/promptclaw/{observatory,sdp-state,gallery,logs,artifacts}
```

### 1.2 Clone the repository

```bash
cd ~
git clone https://github.com/exquest/cypherclaw-private.git cypherclaw
cd cypherclaw
```

> **Note:** You'll need to authenticate with GitHub. Either configure an SSH key or use a personal access token for HTTPS.

### 1.3 Create the Python virtual environment

```bash
cd ~/cypherclaw
python3 -m venv .venv
source .venv/bin/activate

# Install the package and optional dependencies
pip install -e ".[coherence-pg]"

# Install runtime dependencies used by tools
pip install httpx pillow psycopg2-binary redis structlog
```

### 1.4 Install cloud CLI agents

The daemon invokes `claude`, `codex`, and `gemini` as subprocess commands. Install them:

```bash
# Claude Code CLI (Anthropic)
npm install -g @anthropic-ai/claude-code

# Codex CLI (OpenAI) — check current install method
npm install -g @openai/codex

# Gemini CLI (Google)
npm install -g @anthropic-ai/claude-code  # verify actual package name
# OR
pip install google-genai
```

> **Note:** These cloud CLIs require API keys. They are optional on the R750 — the whole point is to use local Ollama models for most work. But keeping them available gives you fallback capability when quota exists.

Verify they are on PATH:

```bash
which claude codex gemini 2>/dev/null
```

### 1.5 Install sdp-cli

```bash
cd ~
git clone <sdp-cli-repo-url> sdp-cli
cd sdp-cli
pip install -e .
# OR if it installs to ~/.local/bin:
pip install --user -e .
```

Verify:

```bash
which sdp-cli
sdp-cli --version
```

### 1.6 Create the .env file

```bash
cat > ~/cypherclaw/.env << 'ENV'
DB_MODE=dual
DATABASE_URL=postgresql://inference:YOUR_PG_PASSWORD@localhost:5432/langgraph

TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_TELEGRAM_CHAT_ID

GEMINI_API_KEY=YOUR_GEMINI_API_KEY

# R750-specific: Ollama endpoints for dual-socket topology
OLLAMA_URL_SOCKET0=http://localhost:11434
OLLAMA_URL_SOCKET1=http://localhost:11435

# Default Ollama URL (used by art_engine.py and the new ollama agent)
OLLAMA_URL=http://localhost:11434
ENV
chmod 600 ~/cypherclaw/.env
```

> **Warning:** Copy your actual tokens from the CypherClaw `.env` file. Do NOT commit this file to git.

### 1.7 Initialize the Observatory database

The R750's PostgreSQL (from the runbook) already has a `langgraph` database. Add the observatory tables:

```bash
PGPASSWORD=YOUR_PG_PASSWORD psql -h localhost -U inference -d langgraph << 'SQL'
-- Observatory core tables (from observatory.py schema)
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

CREATE TABLE IF NOT EXISTS healing_log (
    id SERIAL PRIMARY KEY,
    failure_type TEXT NOT NULL,
    severity TEXT,
    action_taken TEXT,
    context JSONB,
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

CREATE TABLE IF NOT EXISTS watchdog_events (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    details JSONB,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(event_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_task_results_agent ON task_results(agent, timestamp);
CREATE INDEX IF NOT EXISTS idx_agent_skills_lookup ON agent_skills(agent, category);

-- Seed initial skill scores for the ollama agent
INSERT INTO agent_skills (agent, category, score, sample_count) VALUES
    ('ollama', 'architecture', 0.65, 0),
    ('ollama', 'review', 0.60, 0),
    ('ollama', 'coding', 0.70, 0),
    ('ollama', 'research', 0.65, 0),
    ('ollama', 'routing', 0.70, 0),
    ('ollama', 'writing', 0.70, 0),
    ('ollama', 'testing', 0.65, 0),
    ('ollama', 'devops', 0.60, 0),
    ('ollama', 'netops', 0.80, 0)
ON CONFLICT (agent, category) DO NOTHING;

SELECT 'Observatory schema created successfully' AS status;
SQL
```

### 1.8 Initialize the workspace

```bash
# Create the tmpfs working directory structure
sudo mkdir -p /run/cypherclaw-tmp/workdir/cypherclaw-work
sudo chmod 1777 /run/cypherclaw-tmp

# Initialize SDP state directories
mkdir -p ~/cypherclaw/.sdp
mkdir -p ~/cypherclaw/.promptclaw

# Create symlinks to persistent storage
ln -sf /data/promptclaw/observatory ~/cypherclaw/.promptclaw/db
ln -sf /data/promptclaw/sdp-state ~/cypherclaw/.sdp/persistent
```

---

## Part 2: Add Ollama as a First-Class Agent

This is the core integration work. The changes are minimal because the daemon's architecture already supports pluggable agents.

### 2.1 Modify agent_selector.py

Add Ollama to the provider map and fitness scores:

```python
# In agent_selector.py

PROVIDERS = {
    "claude": "anthropic",
    "codex": "openai",
    "gemini": "google",
    "ollama": "local",       # <-- ADD
}

DEFAULT_FITNESS = {
    "claude": {"architecture": 0.85, "review": 0.90, "coding": 0.70, ...},
    "codex": {"architecture": 0.55, "review": 0.60, "coding": 0.90, ...},
    "gemini": {"architecture": 0.60, "review": 0.55, "coding": 0.55, ...},
    "ollama": {                                                    # <-- ADD
        "architecture": 0.65,
        "review": 0.60,
        "coding": 0.70,
        "research": 0.65,
        "routing": 0.70,
        "writing": 0.70,
        "testing": 0.65,
        "devops": 0.60,
        "netops": 0.80,
    },
}
```

> **Note:** These are conservative seed values. The EMA skill tracking in Observatory will adjust them based on actual performance after the model evaluation phase. `netops` is set high because the LG SoT bot will run entirely on Ollama.

### 2.2 Modify quota_monitor.py

Ollama has infinite local quota. Add a short-circuit:

```python
# In quota_monitor.py, in _load_provider_headroom() or get_agent_headroom()

def get_agent_headroom(self, agent: str) -> float:
    provider = PROVIDERS.get(agent)
    if provider == "local":
        return 1.0  # Local models always have full quota
    # ... existing cloud quota logic ...
```

### 2.3 Modify _build_agent_command() in cypherclaw_daemon.py

**Option 1 (recommended): HTTP call, no subprocess.** This avoids the overhead of spawning a process and matches the pattern already used by `art_engine.py`.

```python
# In cypherclaw_daemon.py

import httpx  # add to imports

OLLAMA_MODELS = {
    "orchestrator": {"model": "qwen3:30b-a3b", "port": 11434},
    "coding":       {"model": "qwen3-coder:30b", "port": 11434},
    "review":       {"model": "qwen3.5:122b",    "port": 11435},
    "netops":       {"model": "qwen3:30b-a3b",   "port": 11435},
    "default":      {"model": "qwen3:30b-a3b",   "port": 11434},
}

def _invoke_ollama(prompt: str, timeout: int, task_label: str = "") -> str:
    """Call Ollama HTTP API directly. Returns the response text."""
    # Select model based on task category
    category = agent_selector.detect_category(task_label or prompt[:200])
    model_config = OLLAMA_MODELS.get(category, OLLAMA_MODELS["default"])

    url = f"http://localhost:{model_config['port']}/api/generate"
    payload = {
        "model": model_config["model"],
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 4096,
            "num_ctx": 8192,
        },
    }

    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except httpx.TimeoutException:
        return "[ollama timed out]"
    except httpx.HTTPStatusError as e:
        return f"[ollama error: {e.response.status_code}]"
    except Exception as e:
        return f"[ollama error: {e}]"
```

Then in `run_agent()`, add the Ollama branch before the subprocess path:

```python
def run_agent(agent: str, prompt: str, timeout: int = MAX_AGENT_TIMEOUT,
              task_label: str = "", ...) -> str:
    # ... existing semaphore, spinner setup ...

    if agent == "ollama":
        result_text = _invoke_ollama(prompt, timeout, task_label)
        # ... log to observatory, update pet, etc. ...
        return result_text

    # ... existing subprocess path for claude/codex/gemini ...
```

### 2.4 Modify promptclaw.json

Add the Ollama agent definition:

```json
{
  "agents": {
    "claude": { ... },
    "codex": { ... },
    "gemini": { ... },
    "ollama": {
      "kind": "http",
      "base_url": "http://localhost:11434",
      "capabilities": ["coding", "review", "architecture", "research", "netops", "routing"]
    }
  }
}
```

### 2.5 Model-per-role routing

The key advantage of Ollama on the R750 is role-specific models. The `OLLAMA_MODELS` dict in 2.3 maps task categories to specific models on specific NUMA sockets:

| Category | Model | NUMA Socket | Port | Rationale |
|----------|-------|-------------|------|-----------|
| coding | Best coding model from eval | Socket 0 | 11434 | Code-specialized, fast |
| review | Best reviewer from eval | Socket 1 | 11435 | Strongest reasoning |
| netops | Best tool-calling model from eval | Socket 1 | 11435 | API chaining |
| orchestrator | Best routing model from eval | Socket 0 | 11434 | Fast decisions |
| default | Same as orchestrator | Socket 0 | 11434 | Fallback |

> **Note:** The exact model names are placeholders. Fill in after completing the model evaluation plan (`r750-model-evaluation-plan.md`). The architecture supports swapping models without code changes — just update `OLLAMA_MODELS`.

---

## Part 3: Systemd Services

### 3.1 Main daemon service

```bash
sudo tee /etc/systemd/system/cypherclaw.service << 'UNIT'
[Unit]
StartLimitIntervalSec=300
Description=CypherClaw Daemon — AI Orchestrator
After=network-online.target ollama-0.service ollama-1.service docker-datastore.service
Wants=network-online.target ollama-0.service ollama-1.service

[Service]
EnvironmentFile=/home/anthony/cypherclaw/.env
Type=simple
User=anthony
Group=anthony
WorkingDirectory=/home/anthony/cypherclaw
ExecStart=/usr/bin/python3 /home/anthony/cypherclaw/tools/cypherclaw_daemon.py
WatchdogSec=600
NotifyAccess=main
Restart=always
RestartSec=5
StartLimitBurst=5
TimeoutStopSec=30
KillMode=control-group
KillSignal=SIGTERM
SendSIGKILL=yes
MemoryMax=16G
TasksMax=200
Environment=PATH=/home/anthony/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=GEMINI_IMAGE_MODEL=gemini-3.1-flash-image-preview
Environment=PYTHONUNBUFFERED=1
Environment=TMPDIR=/run/cypherclaw-tmp
Environment=OLLAMA_URL=http://localhost:11434

[Install]
WantedBy=multi-user.target
UNIT
```

### 3.2 SDP runner service

```bash
sudo tee /etc/systemd/system/cypherclaw-sdp-runner.service << 'UNIT'
[Unit]
Description=CypherClaw SDP Runner
After=cypherclaw-bootstrap.service cypherclaw.service network-online.target
Requires=cypherclaw-bootstrap.service
ConditionPathExists=/home/anthony/cypherclaw
ConditionPathExists=/home/anthony/.local/bin/sdp-cli

[Service]
Type=simple
User=anthony
WorkingDirectory=/run/cypherclaw-tmp/workdir/cypherclaw-work
Environment=HOME=/home/anthony
Environment=PATH=/home/anthony/.local/bin:/home/anthony/cypherclaw/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=TMPDIR=/run/cypherclaw-tmp
Environment=PYTHONPATH=/home/anthony/sdp-cli/src
Environment=TERM=dumb
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/anthony/cypherclaw/tools/sdp_runner_launcher.sh
Restart=always
RestartSec=10
SuccessExitStatus=75
RestartPreventExitStatus=75
KillSignal=SIGINT
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cypherclaw-sdp-runner

[Install]
WantedBy=multi-user.target
UNIT
```

### 3.3 Web platform service

```bash
sudo tee /etc/systemd/system/cypherclaw-web.service << 'UNIT'
[Unit]
Description=CypherClaw Web Platform
After=network-online.target docker-datastore.service cypherclaw.service
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=3

[Service]
Type=simple
User=anthony
Group=anthony
WorkingDirectory=/home/anthony/cypherclaw
ExecStartPre=+/usr/bin/install -d -m 1777 /run/cypherclaw-tmp
EnvironmentFile=/home/anthony/cypherclaw/.env
Environment=PYTHONPATH=/home/anthony/cypherclaw/src
Environment=TMPDIR=/run/cypherclaw-tmp
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/anthony/cypherclaw/.venv/bin/gunicorn --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 127.0.0.1:3000 tools.web.backend.main:app
Restart=on-failure
RestartSec=10
TimeoutStopSec=30
KillMode=process
IOSchedulingClass=idle
Nice=19

[Install]
WantedBy=multi-user.target
UNIT
```

### 3.4 Bootstrap service (tmpfs initialization)

```bash
sudo tee /etc/systemd/system/cypherclaw-bootstrap.service << 'UNIT'
[Unit]
Description=CypherClaw Bootstrap — Initialize tmpfs workspace
After=network-online.target
DefaultDependencies=no

[Service]
Type=oneshot
RemainAfterExit=yes
User=anthony
ExecStartPre=+/usr/bin/install -d -m 1777 /run/cypherclaw-tmp
ExecStart=/home/anthony/cypherclaw/tools/init_workdir.sh

[Install]
WantedBy=multi-user.target
UNIT
```

### 3.5 Gallery service (GlyphWeave art display)

```bash
sudo tee /etc/systemd/system/cypherclaw-gallery.service << 'UNIT'
[Unit]
Description=CypherClaw Gallery — GlyphWeave Art Display
After=ollama-0.service cypherclaw.service
Wants=ollama-0.service

[Service]
Type=simple
User=anthony
Group=anthony
WorkingDirectory=/home/anthony/cypherclaw
Environment=PYTHONPATH=/home/anthony/cypherclaw/tools
Environment=OLLAMA_URL=http://localhost:11434
Environment=GALLERY_DIR=/data/promptclaw/gallery
ExecStart=/home/anthony/cypherclaw/.venv/bin/python3 tools/gallery/gallery_display.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT
```

### 3.6 Enable all services

```bash
sudo systemctl daemon-reload
sudo systemctl enable cypherclaw-bootstrap cypherclaw cypherclaw-sdp-runner cypherclaw-web cypherclaw-gallery
```

### 3.7 Service startup order

The full boot sequence on the R750:

```
1. docker-datastore.service    → PostgreSQL + Redis containers
2. ollama-0.service            → NUMA socket 0 (port 11434)
3. ollama-1.service            → NUMA socket 1 (port 11435)
4. ollama-warmup.service       → Preload models into RAM
5. cypherclaw-bootstrap.service → tmpfs workspace init
6. cypherclaw.service          → Main daemon (Telegram bot)
7. cypherclaw-sdp-runner.service → SDP task runner
8. cypherclaw-web.service      → FastAPI dashboard
9. cypherclaw-gallery.service  → Art display
```

---

## Part 4: Nginx Reverse Proxy

### 4.1 Install nginx

```bash
sudo apt install -y nginx
```

### 4.2 Configure the site

```bash
sudo tee /etc/nginx/sites-available/cypherclaw << 'NGINX'
server {
    listen 80;
    server_name _;

    # Web dashboard
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support for streaming
    location /ws/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # Health check endpoint (no auth)
    location /health {
        proxy_pass http://127.0.0.1:3000/health;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/cypherclaw /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

---

## Part 5: Migration from CypherClaw

### 5.1 What transfers from CypherClaw

| Data | Source | Destination | Method |
|------|--------|-------------|--------|
| Observatory DB | CypherClaw PostgreSQL | R750 PostgreSQL | `pg_dump` / `pg_restore` |
| Agent skill scores | `agent_skills` table | Same | Included in DB dump |
| Pet data | `pets`, `pet_*` tables | Same | Included in DB dump |
| Art gallery | `/home/user/cypherclaw/gallery/` | `/data/promptclaw/gallery/` | `rsync` |
| .env secrets | `/home/user/cypherclaw/.env` | `/home/anthony/cypherclaw/.env` | Manual copy |
| SDP state | `~/.sdp/state.db` | `~/cypherclaw/.sdp/state.db` | `scp` |
| Promptclaw config | `promptclaw.json` | Same (in git) | Already in repo |

### 5.2 Database migration

```bash
# On CypherClaw: dump the observatory
ssh user@cypherclaw 'PGPASSWORD=cypherclaw pg_dump -h localhost -U cypherclaw cypherclaw_observatory' > /tmp/observatory_dump.sql

# On R750: restore into the langgraph database (or create a separate observatory DB)
PGPASSWORD=YOUR_PG_PASSWORD psql -h localhost -U inference -d langgraph < /tmp/observatory_dump.sql
```

### 5.3 Gallery migration

```bash
rsync -avz user@cypherclaw:/home/user/cypherclaw/gallery/ /data/promptclaw/gallery/
```

### 5.4 SDP state migration

```bash
scp user@cypherclaw:/home/user/cypherclaw/.sdp/state.db ~/cypherclaw/.sdp/state.db
```

### 5.5 Relationship between CypherClaw and R750

**Both instances can run simultaneously.** They share:
- The same git repository (different clones)
- The same Telegram bot token (only ONE should poll at a time — disable the daemon on whichever server is secondary)
- Different PostgreSQL instances (no replication for v1)
- Different Ollama instances (CypherClaw has small models, R750 has large ones)

**Recommended approach:**
1. Deploy on R750 with the Telegram bot token
2. Stop `cypherclaw.service` on CypherClaw (but keep Ollama + gallery running for art)
3. The R750 becomes the primary PromptClaw instance
4. CypherClaw becomes art-only (GlyphWeave studio continues independently)

---

## Part 6: Update the Warmup Script

After the model evaluation phase, update `/usr/local/bin/ollama-warmup.sh` from the runbook with the actual selected models:

```bash
#!/bin/bash
set -e
echo "[$(date)] Starting Ollama warmup..."

for port in 11434 11435; do
  until curl -sf http://localhost:$port/api/version > /dev/null 2>&1; do
    sleep 2
  done
done

# Socket 0 — orchestrator + coding models
for model in "MODEL_FROM_EVAL_ORCHESTRATOR" "MODEL_FROM_EVAL_CODING" "qwen3-embedding:8b"; do
  echo "Loading $model on Socket 0..."
  curl -sf http://localhost:11434/api/generate \
    -d "{\"model\":\"$model\",\"prompt\":\"warmup\",\"stream\":false}" > /dev/null
done

# Socket 1 — reviewer + netops models
for model in "MODEL_FROM_EVAL_REVIEWER" "MODEL_FROM_EVAL_NETOPS"; do
  echo "Loading $model on Socket 1..."
  curl -sf http://localhost:11435/api/generate \
    -d "{\"model\":\"$model\",\"prompt\":\"warmup\",\"stream\":false}" > /dev/null
done

echo "[$(date)] Warmup complete."
```

---

## Part 7: Verification Checklist

### 7.1 Services running

```bash
systemctl is-active ollama-0 ollama-1 docker-datastore cypherclaw cypherclaw-sdp-runner cypherclaw-web cypherclaw-gallery
```

All should show `active`.

### 7.2 Daemon health

```bash
# Check daemon logs
journalctl -u cypherclaw --since "5 minutes ago" --no-pager | tail -20
```

Should show successful startup, Telegram poll activity, no errors.

### 7.3 Telegram bot responds

Send a message to your Telegram bot. It should respond via the R750 daemon, not CypherClaw.

### 7.4 Ollama agent works

Send a test message that would route to Ollama:

```
/local
```

This should show the loaded models on both Ollama instances.

### 7.5 Observatory recording

```bash
PGPASSWORD=YOUR_PG_PASSWORD psql -h localhost -U inference -d langgraph \
  -c "SELECT event_type, COUNT(*) FROM events WHERE timestamp > NOW() - INTERVAL '1 hour' GROUP BY event_type;"
```

Should show events being recorded.

### 7.6 Web dashboard

Open `http://<tailscale-ip>/` in a browser. The CypherClaw Mission Control dashboard should load.

---

## Part 8: Post-Deployment Configuration

### 8.1 Set Ollama as the preferred agent

Once you've validated that Ollama produces acceptable results, increase its fitness scores to make it the default choice:

```python
# In agent_selector.py, raise ollama scores above cloud agents:
"ollama": {
    "architecture": 0.80,
    "review": 0.75,
    "coding": 0.85,
    "research": 0.80,
    "routing": 0.85,
    "writing": 0.80,
    "testing": 0.80,
    "devops": 0.75,
    "netops": 0.95,
},
```

Or override at runtime via Observatory's `agent_skills` table:

```sql
UPDATE agent_skills SET score = 0.85 WHERE agent = 'ollama' AND category = 'coding';
```

### 8.2 Cloud agent fallback

The quota monitor already handles fallback. For Ollama, add a health check:

```python
# In quota_monitor.py or a new ollama_health.py
def check_ollama_health(port: int = 11434) -> bool:
    try:
        resp = httpx.get(f"http://localhost:{port}/api/version", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False
```

If Ollama is down, the agent selector naturally falls back to cloud agents (they have the next-highest fitness scores and full quota).

### 8.3 Disable cloud agents entirely (optional)

If you want to run fully local with no cloud API calls:

```python
# In the daemon, modify _available_agents():
def _available_agents(agents=None, *, disabled_agents=None):
    candidates = list(agents or ["ollama"])  # Only ollama
    # ... rest unchanged ...
```

Or add a runtime toggle via environment variable:

```bash
# In .env:
LOCAL_ONLY=true
```

---

## Execution Sequence Summary

| Step | What | When | Depends on |
|------|------|------|------------|
| 1 | Complete bare metal runbook | Day 1-2 | Physical access to server |
| 2 | Run model evaluation plan | Day 3-9 | Runbook complete |
| 3 | Clone repo, create venv, install deps | Day 10 | Models selected |
| 4 | Apply code changes (agent_selector, daemon, quota_monitor) | Day 10 | Step 3 |
| 5 | Create systemd services | Day 10 | Step 4 |
| 6 | Migrate data from CypherClaw | Day 10 | Step 5 |
| 7 | Start services, verify | Day 10 | Step 6 |
| 8 | Switch Telegram bot to R750 | Day 10 | Step 7 verified |
| 9 | Monitor, tune fitness scores | Day 11+ | Production traffic |

**Total estimated time from bare metal to production:** 10 days (2 days install, 7 days model eval, 1 day app deployment).
