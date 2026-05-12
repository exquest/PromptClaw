# PAL 2026 Phase 1 Checkpoints

Use this file as the live deployment runbook. Work sequentially. Display one
step to Anthony, wait for confirmation, then continue.

## 1.1 Select And Launch Vast.ai Instance

### 1.1.1 Select Instance

Have Anthony open Vast.ai and filter:

- GPU: NVIDIA RTX A6000, 48 GB VRAM.
- GPU count: 1.
- Disk: at least 200 GB.
- Internet: at least 500 Mbps down and 500 Mbps up.
- Reliability: at least 0.98.
- CUDA: at least 12.4.
- Verified host: yes.
- Price ceiling: 0.70 USD/hour, target 0.40 to 0.60 USD/hour.

Sort by price ascending. Pick the cheapest instance meeting all criteria. If
A6000 inventory is thin, acceptable alternatives are L40S 48 GB, RTX 6000 Ada
48 GB, or A100 40 GB.

Checkpoint: Anthony has selected an instance and is looking at the Rent button.
Do not let him click it yet.

### 1.1.2 Configure Launch Options

Before renting:

- Template: Ubuntu 22.04 + CUDA 12.4 or closest available.
- On-start script: empty.
- SSH access: enabled.
- Jupyter: disabled.
- Public ports: none.
- Disk allocation: 200 GB.

Checkpoint: all options match. Then Anthony clicks Rent.

### 1.1.3 Wait For Provisioning

Wait 1 to 5 minutes. Checkpoint: instance is Running and shows an SSH command.
If it does not provision within 10 minutes, cancel rental and return to 1.1.1.

### 1.1.4 Verify SSH And GPU

Anthony runs the Vast.ai SSH command from his MacBook terminal, then on the
instance:

```bash
nvidia-smi
```

Checkpoint: SSH succeeds and `nvidia-smi` shows RTX A6000 48 GB with CUDA 12.4
or newer. If wrong GPU or `nvidia-smi` fails, destroy instance and return to
1.1.1.

## 1.2 Install Tailscale

### 1.2.1 Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

Checkpoint: installation completes without errors.

### 1.2.2 Authenticate

Anthony substitutes his auth key:

```bash
tailscale up --authkey=tskey-auth-<ANTHONY_PROVIDES> --hostname=pal-cloud-a6000 --advertise-exit-node
```

Checkpoint: command completes with Success.

### 1.2.3 Verify Connectivity

On cloud instance:

```bash
tailscale status
```

On MacBook:

```bash
tailscale status | grep pal-cloud-a6000
```

Checkpoint: cloud node appears in local tailnet status.

### 1.2.4 Enable Exit Node

Anthony opens `https://login.tailscale.com/admin/machines`, finds
`pal-cloud-a6000`, edits route settings, and enables exit node.

Checkpoint: exit node is approved and enabled.

Troubleshooting:

- Auth failure: generate a new reusable auth key with exit-node permissions.
- Node missing: run `tailscale status --json`; try `tailscale up --reset`.
- Exit node disabled in admin: regenerate key with route permissions.

## 1.3 Install Docker And NVIDIA Runtime

### 1.3.1 Update Packages

```bash
apt update && apt upgrade -y
apt install -y curl wget git vim htop tmux build-essential
```

### 1.3.2 Install Docker

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
systemctl enable docker
systemctl start docker
docker --version
```

Checkpoint: Docker 24.x or 25.x or newer is shown.

### 1.3.3 Install NVIDIA Container Toolkit

```bash
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt update
apt install -y nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

Checkpoint: containerized `nvidia-smi` works.

Troubleshooting: run `nvidia-ctk runtime configure --runtime=docker
--set-as-default` and restart Docker.

## 1.4 Deploy Ollama

### 1.4.1 Create Directories

```bash
mkdir -p /opt/pal/{ollama,router,scripts,config,logs}
cd /opt/pal
```

### 1.4.2 Create Initial Compose File

Create `/opt/pal/docker-compose.yml` with Ollama and placeholder router services.
Use `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=2`, and expose Ollama on
11434. The final Phase 1 compose template is stored locally at
`ops/templates/docker-compose.phase1.yml`.

### 1.4.3 Start Ollama

```bash
cd /opt/pal
docker compose up -d ollama
docker logs pal-ollama --tail 50
curl http://localhost:11434/api/version
```

Checkpoint: Ollama version returns.

### 1.4.4 Pull Llama 3.3 70B

```bash
docker exec pal-ollama ollama pull llama3.3:70b-instruct-q4_K_M
docker exec pal-ollama ollama list
```

Checkpoint: model appears at about 40 GB.

### 1.4.5 Pull Embedding Model

```bash
docker exec pal-ollama ollama pull nomic-embed-text
docker exec pal-ollama ollama list
```

Checkpoint: both models appear.

### 1.4.6 Verify Inference

```bash
docker exec pal-ollama ollama run llama3.3:70b-instruct-q4_K_M "Confirm you are operational and report your token generation speed in one sentence."
```

Checkpoint: coherent response; optionally check GPU usage with `nvidia-smi` in a
second SSH session.

## 1.5 Deploy FastAPI Router

Create `/opt/pal/router/app.py`, `/opt/pal/router/Dockerfile`, and update
`/opt/pal/docker-compose.yml` to put Ollama and router on `pal-net`. Local
templates:

- `ops/templates/router-app.py`
- `ops/templates/router-Dockerfile`
- `ops/templates/docker-compose.phase1.yml`

Required local checks:

```bash
cd /opt/pal
docker compose up -d --build
curl http://localhost:8000/health
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Confirm PAL 2026 Phase 1 is operational.", "temperature": 0.3}'
```

Required MacBook checks:

```bash
curl http://pal-cloud-a6000:8000/health
curl -X POST http://pal-cloud-a6000:8000/query \
  -H "Content-Type: application/json" \
  -d '{"prompt": "From the MacBook over Tailscale: are you reachable?", "temperature": 0.3}'
```

Checkpoint: health and inference work over Tailscale.

## 1.6 Configure Auto-Shutdown

Create `/opt/pal/config/shutdown.conf`, `/opt/pal/scripts/auto_shutdown.sh`, make
it executable, and install. Local templates:

- `ops/templates/shutdown.conf`
- `ops/templates/auto_shutdown.sh`

```bash
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/pal/scripts/auto_shutdown.sh") | crontab -
crontab -l
```

Checkpoint: cron entry exists.

Override:

```bash
touch /opt/pal/config/override.flag
rm /opt/pal/config/override.flag
```

Safe test: temporarily set shutdown time to 5 minutes from now, verify Vast.ai
shows stopped, restart, SSH back in, and restore `SHUTDOWN_TIME=01:00`.

## 1.7 Final Verification And Handoff

From MacBook:

```bash
curl http://pal-cloud-a6000:8000/health
curl -X POST http://pal-cloud-a6000:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Confirm PAL 2026 Phase 1 is operational. Describe your current configuration in two sentences.",
    "system": "You are PAL 2026, an AI operations platform for Looking Glass Community Services. Respond concisely.",
    "temperature": 0.3
  }'
```

Create `/opt/pal/DEPLOYMENT_INFO.md` on the cloud host with instance ID, GPU,
hourly cost, Tailscale hostname, shutdown policy, models, endpoints, and Phase 1
status.

Confirm Anthony knows:

- health endpoint works from MacBook.
- query endpoint works from MacBook.
- auto-shutdown override commands.
- hourly cost and approximate monthly burn.
- Phase 2 is appendix-only and not for today.
