# PAL 2026 Startup Profile

## Purpose

Create a dedicated PromptClaw project for Anthony's PAL 2026 cloud deployment.
The first operational target is a single A6000-class Vast.ai instance running
Llama 3.3 70B Q4 behind a FastAPI router on Tailscale.

## Current Phase

Phase 1 only.

## Confirmed Prerequisites

- Anthony has a funded Vast.ai account.
- Anthony has SSH configured on his MacBook.
- Anthony has a Tailscale auth token and admin access.
- Anthony knows his existing Tailscale network name.

Do not re-verify these before starting Phase 1.

## Phase 1 Target

- GPU: RTX A6000 48 GB preferred.
- Acceptable fallback GPUs: L40S 48 GB, RTX 6000 Ada 48 GB, A100 40 GB.
- Avoid: GPUs below 40 GB VRAM and H100 for Phase 1.
- Runtime: Ubuntu 22.04 with CUDA 12.4 or newer.
- Network: Tailscale hostname `pal-cloud-a6000`.
- Model: `llama3.3:70b-instruct-q4_K_M`.
- Embeddings: `nomic-embed-text`.
- Router: FastAPI on port 8000, accessed over Tailscale.
- Auto-shutdown: configurable, default 01:00 America/Los_Angeles.

## First Live Step

Begin at Phase 1 Step 1.1.1 in `ops/phase-1-checkpoints.md`.
