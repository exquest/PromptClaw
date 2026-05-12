# Project Vision

PAL 2026 is an interactive deployment claw for standing up Anthony's Phase 1
cloud inference node:

- Vast.ai instance with 1x RTX A6000 48 GB or approved fallback GPU.
- Ubuntu 22.04 with CUDA 12.4 or newer.
- Tailscale node named `pal-cloud-a6000`.
- Docker, Docker Compose, and NVIDIA Container Toolkit.
- Ollama serving `llama3.3:70b-instruct-q4_K_M` and `nomic-embed-text`.
- FastAPI router exposing `/health` and `/query`.
- Configurable auto-shutdown with override flag.

Success means Anthony can reach `http://pal-cloud-a6000:8000/health` from his
MacBook over Tailscale, send a query through the router, understand the
auto-shutdown override, and have deviations recorded for a future v2 guide.

The claw must never collect or persist secrets. Tailscale auth keys, Vast.ai
account details, and any private credentials stay in Anthony's terminal or
provider console. Public ports stay closed for Phase 1 unless Anthony explicitly
changes the security model.

The setup agent asks questions one at a time only when a checkpoint requires
Anthony confirmation, a command fails, a provider choice is ambiguous, or Anthony
asks to pause/resume.
