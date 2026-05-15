# PRD Snapshot - PAL 2026 Agentic Operations Platform PRD
**Source:** `sdp/prd-pal-2026-agentic-ops-platform.md`
**SHA-256:** `052b6771b0089e7dcff49c213fed78926f368fd218e4c1572b81eafc6f337bbc`
**Captured:** 2026-05-15T21:42:33.420199+00:00

---
# PAL 2026 Agentic Operations Platform PRD

**Project:** PromptClaw / PAL 2026
**Version:** 1.0
**Date:** 2026-05-15
**SDP Protocol:** v1.0
**Primary repo:** `/Users/anthony/Programming/PromptClaw`
**PAL project root:** `pal-2026/`
**Live PAL target:** Vast.ai A6000 node `pal-cloud-a6000` over Tailscale
**Current model substrate:** Ollama `llama3.3:70b-instruct-q4_K_M` plus `nomic-embed-text`

---

## Overview

PAL 2026 Phase 1 is already online as a basic inference and operations target:

- A Vast.ai A6000 host is reachable over Tailscale as `pal-cloud-a6000`.
- The FastAPI router is reachable at `http://pal-cloud-a6000:8000`.
- PromptClaw has PAL client commands for health, query, smoke tests, baseline summaries, triage, and approval-gated actions.
- Live smoke and triage runs have produced normal PromptClaw artifacts under `pal-2026/.promptclaw/runs/`.

The current implementation is a useful foundation but is not yet the full "minimal operator involvement" PAL system. This PRD defines the end-to-end build needed to let SDP frontier models implement, verify, and deploy a complete PAL 2026 agentic operations platform.

The intended outcome is not that PAL becomes an unrestricted shell agent. The intended outcome is that PAL can:

1. Maintain a project knowledge base from PAL docs, runbooks, smoke reports, deployment state, and run artifacts.
2. Plan operational workflows using that context.
3. Execute only typed, allow-listed tools and playbooks.
4. Require explicit approval for mutating or cost-bearing actions.
5. Resume saved approvals from a specific artifacted plan.
6. Verify its own work through tests, live health checks, smoke runs, and deployment probes.
7. Produce useful operator handoffs with minimal back-and-forth.

This PRD should be loaded into SDP after validation. The SDP frontier models should build this, not the current PAL model.

---

## Current State Snapshot

PromptClaw already contains:

- `promptclaw/pal_client.py`: stdlib client for PAL router `/health` and `/query`.
- `promptclaw/pal_smoke.py`: fixed PAL smoke suite and smoke baseline summaries.
- `promptclaw/pal_agent.py`: bounded PAL ops triage and approval-gated actions.
- CLI commands:
  - `promptclaw pal health PROJECT_ROOT`
  - `promptclaw pal query PROJECT_ROOT --prompt "..."`
  - `promptclaw pal smoke PROJECT_ROOT`
  - `promptclaw pal baseline PROJECT_ROOT`
  - `promptclaw pal agent triage PROJECT_ROOT`
  - `promptclaw pal agent actions PROJECT_ROOT [--approve ACTION_ID]`
- PAL project config in `pal-2026/promptclaw.json` with `pal.enabled=true`.

The live PAL host is currently host-managed, not Docker-managed:

- `/opt/pal/scripts/start_all.sh`
- `/opt/pal/scripts/start_ollama.sh`
- `/opt/pal/scripts/start_router.sh`
- `/opt/pal/logs/router.log`
- `/opt/pal/logs/ollama.log`
- `/opt/pal/logs/shutdown.log`
- `ollama serve` process
- `uvicorn app:app --host 0.0.0.0 --port 8000` process
- `tailscaled` userspace process
- cron-driven auto-shutdown script

The SDP implementation must preserve compatibility with this current deployed shape while still allowing later Docker/systemd variants.

---

## Goals

1. Build PAL into a complete agentic operations layer for the current Phase 1 deployment.
2. Keep Anthony's involvement low: he should mainly approve cost-bearing, credential, restart, shutdown, and destructive actions.
3. Make every PAL decision reproducible through PromptClaw artifacts.
4. Let SDP agents implement and verify this end to end with unit tests, CLI integration tests, and live PAL probes.
5. Add deployment automation that can safely update the live PAL host and verify it after deploy.
6. Keep a clear upgrade path toward Phase 2 multi-GPU / larger-model work, without executing Phase 2 in this PRD.

---

## Non-Goals

- No Phase 2 hardware upgrade.
- No H100 rental, Qwen3-235B deployment, or persistent Vast volume migration.
- No HIPAA production claims.
- No PHI ingestion.
- No unrestricted remote shell.
- No fully autonomous spending, instance destruction, key rotation, firewall mutation, or shutdown override.
- No replacement of `sdp-cli` as the implementation engine.

---

## Minimal Operator Involvement Contract

PAL should proceed without asking Anthony for routine implementation details, test runs, docs edits, health checks, smoke runs, read-only SSH inspections, and artifact generation.

PAL must stop for explicit approval before:

- Starting, stopping, destroying, or renting cloud instances.
- Any action that changes Vast.ai spend.
- Restarting live PAL services.
- Changing shutdown behavior.
- Writing or deleting remote config files.
- Rotating, creating, or exposing credentials.
- Opening public network ports.
- Loading Phase 2 hardware/model work.
- Any action that could disrupt active inference.

The UI/CLI must make the approval boundary concrete. A proposed action should be stored in an artifacted plan, and approval should execute that exact saved action, not a fresh model plan.

---

## Proposed Architecture

### Local Control Plane

PromptClaw remains the control plane. PAL router inference is treated as a reasoning service, not an executor.

### PAL Router

The remote PAL router remains a FastAPI service in front of Ollama. This PRD may add endpoints only when needed for safe operations, such as structured status or metrics. The existing `/health` and `/query` endpoints must remain backward compatible.

### PAL Knowledge Base

The local PromptClaw repo should maintain a PAL knowledge index built from:

- `pal-2026/docs/`
- `pal-2026/ops/`
- `docs/architecture.md`
- `docs/command-reference.md`
- `docs/handoff-protocol.md`
- `sdp/prd-pal-2026-agentic-ops-platform.md`
- PAL smoke reports under `pal-2026/.promptclaw/pal-smoke/`
- PAL agent run summaries under `pal-2026/.promptclaw/runs/`
- Remote deployment info from `/opt/pal/DEPLOYMENT_INFO.md` when available

Use a simple, inspectable local index first. SQLite FTS5 or a JSON-lines inverted index is acceptable. Do not introduce a heavyweight vector DB unless there is a measured need.

### Workflow Engine

Add a typed PAL workflow layer. Each workflow should:

- Have a stable workflow id.
- Declare its read-only tools.
- Declare its approval-gated actions.
- Declare expected artifacts.
- Declare verification commands.
- Return a JSON-safe run summary.

Initial workflows:

- `ops_triage`: current health/baseline/Tailscale/SSH triage.
- `approve_saved_action`: execute an action from a previously saved plan.
- `slow_inference_diagnosis`: diagnose high latency or poor token rate.
- `restart_validation`: validate service health after restart or instance boot.
- `shutdown_audit`: audit auto-shutdown config, cron, override flag, and recent logs.
- `phase2_readiness_report`: report whether Phase 2 prerequisites are met; no Phase 2 execution.

### Approval Model

The approval model must be artifact-based:

1. PAL proposes actions into `outputs/action-results.json`.
2. The operator runs an approve command with `--run-id` and `--action`.
3. PromptClaw loads that saved plan.
4. PromptClaw validates that the action id was proposed and is allow-listed.
5. PromptClaw executes only that saved action.
6. PromptClaw writes a new approval execution artifact.

### Deployment Model

Deployment should support the current host-managed PAL setup:

- Copy or sync repo-managed PAL scripts/router files to `/opt/pal`.
- Restart only approved services.
- Verify local and Tailscale health.
- Run smoke tests.
- Roll back when possible, or produce an escalation artifact when not.

Do not assume Docker is running on the PAL host. Docker support can remain as a fallback, but host-managed scripts are the current authority.

---

## Requirements

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| PAL-001 | Document the current PAL product surface. | MUST | T1 | Docs list PAL commands, modules, artifacts, and host-managed `/opt/pal` layout. |
| PAL-002 | Add JSON export for PAL action metadata. | MUST | T1 | Test reads every action id with mutating and approval fields. |
| PAL-003 | Add `promptclaw pal agent approve` parser wiring. | MUST | T1 | CLI help shows `approve PROJECT_ROOT --run-id --action`. |
| PAL-004 | Load saved PAL action plans by run id. | MUST | T1 | Test loads `outputs/action-results.json` from a fixture run. |
| PAL-005 | Reject approvals for actions absent from the saved plan. | MUST | T1 | CLI returns nonzero and writes no execution artifact. |
| PAL-006 | Reject approvals for unknown action ids. | MUST | T1 | Test proves unknown ids never reach the action runner. |
| PAL-007 | Execute an approved saved action without a model call. | MUST | T1 | Fake PAL client records zero `query()` calls during replay. |
| PAL-008 | Write approval execution artifacts. | MUST | T1 | Artifact contains action id, status, timestamp, and redacted command output. |
| PAL-009 | Link approval execution artifacts to the source plan. | MUST | T1 | Artifact stores source run id and source action-plan path. |
| PAL-010 | Harden `restart_router` for host-managed PAL. | MUST | T1 | Unit test verifies `/opt/pal/scripts/start_router.sh` is preferred. |
| PAL-011 | Keep Docker restart as fallback only. | MUST | T1 | Unit test verifies Docker is selected only when host script is absent. |
| PAL-012 | Add fake SSH runner support for PAL tests. | MUST | T1 | Tests run remote-action code without a real SSH connection. |
| PAL-013 | Create PAL source discovery function. | MUST | T2 | Test returns configured sample files. |
| PAL-014 | Add deterministic PAL knowledge chunking. | MUST | T2 | Test proves stable chunk ids for unchanged input files. |
| PAL-015 | Add PAL knowledge index writer. | MUST | T2 | `pal kb build` creates `.promptclaw/pal-kb/index.jsonl` or SQLite equivalent. |
| PAL-016 | Add PAL knowledge query command. | MUST | T2 | Query returns ranked snippets with source paths. |
| PAL-017 | Inject PAL knowledge into workflow prompts. | MUST | T2 | Prompt artifact includes a bounded `Knowledge Context` section. |
| PAL-018 | Add slow-inference context collection. | MUST | T2 | Workflow captures health, baseline token/s, GPU hints, and logs when available. |
| PAL-019 | Add slow-inference diagnosis CLI. | MUST | T2 | Command writes a diagnosis run artifact and performs no mutation. |
| PAL-020 | Add restart-validation workflow. | MUST | T2 | Command runs health, direct query, smoke, Tailscale, and process checks. |
| PAL-021 | Add shutdown-audit workflow. | MUST | T2 | Summary states shutdown enabled state, override state, and next shutdown window. |
| PAL-022 | Add Phase 2 readiness workflow. | MUST | T2 | Report scores each prerequisite and exposes no Phase 2 execution action. |
| PAL-023 | Standardize PAL workflow `run-summary.json`. | MUST | T1 | Every workflow writes required workflow/status/tool/action keys. |
| PAL-024 | Add PAL workflow artifact verifier. | MUST | T1 | Test fails a run missing required artifacts. |
| PAL-025 | Add PAL secret redaction verifier. | MUST | T1 | Test fails artifacts containing `PAL_SSH_KEY` or token-like values. |
| PAL-026 | Add PAL escalation artifact helper. | MUST | T1 | Missing SSH env and pending approval write `summary/escalation.md`. |
| PAL-027 | Create repo-managed PAL deployment manifest. | MUST | T2 | Manifest lists intended `/opt/pal` files and contains no secrets. |
| PAL-028 | Implement deploy diff model. | MUST | T2 | Fake remote test reports diff sets. |
| PAL-029 | Implement deploy-plan CLI. | MUST | T2 | Command prints plan with no remote writes. |
| PAL-030 | Implement deploy backup primitive. | SHOULD | T2 | Fake remote test stores changed files. |
| PAL-031 | Implement approved deploy-apply CLI. | SHOULD | T2 | Fake remote test requires approval flag. |
| PAL-032 | Implement rollback primitive. | SHOULD | T2 | Fake remote test restores backed-up files. |
| PAL-033 | Add `promptclaw pal deploy rollback --approve-rollback`. | SHOULD | T2 | Command refuses rollback without approval flag. |
| PAL-034 | Add PAL deployment metadata model. | SHOULD | T1 | Metadata stores hourly rate, runtime estimate, and optional Vast instance id. |
| PAL-035 | Add `promptclaw pal cost`. | SHOULD | T1 | Command prints hourly, daily, and monthly burn estimates. |
| PAL-036 | Add Vast connector stub boundary. | MUST | T2 | No rent/destroy/start/stop action is callable by default. |
| PAL-037 | Add Vast secret redaction tests. | MUST | T1 | Tests reject persisted Vast API key values. |
| PAL-038 | Update architecture documentation. | MUST | T1 | Docs include a PAL platform section. |
| PAL-039 | Update command reference documentation. | MUST | T1 | Docs list all new `promptclaw pal` commands. |
| PAL-040 | Update PAL project guide. | MUST | T1 | `pal-2026/docs/PROJECT_GUIDE.md` names the new operator loop. |
| PAL-041 | Add fake-client CLI tests for PAL workflows. | MUST | T2 | Tests cover kb, approve, workflow, and deploy-plan commands. |
| PAL-042 | Add opt-in live PAL verification marker or script. | MUST | T1 | Default test run skips live checks. |
| PAL-043 | Document live PAL verification commands. | MUST | T1 | Handoff lists health, smoke, triage, proposal-only, and read-only action checks. |
| PAL-044 | Create SDP handoff page. | MUST | T1 | Page lists analyze and run-loop commands. |
| PAL-045 | Update changelog for PAL agentic ops. | MUST | T1 | Changelog entry names approval replay, KB, workflows, and deploy plan. |

---

## Suggested Task Slicing

SDP should split this into roughly these implementation groups:

1. Approval replay and action metadata hardening: PAL-002 through PAL-012.
2. Knowledge base: PAL-013 through PAL-017.
3. Workflow family: PAL-018 through PAL-026.
4. Deployment tooling: PAL-027 through PAL-033.
5. Cost/Vast boundary: PAL-034 through PAL-037.
6. Docs, tests, live verification, and SDP handoff: PAL-038 through PAL-045.

Do not start deployment apply or rollback before the dry-run deployment plan and fake-remote tests are green.

---

## Verification Strategy

### Unit and CLI Tests

Run focused tests after each task:

```bash
pytest -q tests/test_pal_agent.py tests/test_pal_smoke.py tests/test_pal_client.py tests/test_doctor.py
```

New tests should be added for the new modules and commands. Avoid requiring live PAL for normal CI.

### Static Checks

Run:

```bash
ruff check promptclaw tests
git diff --check
```

If mypy is part of the active SDP gate for this repo, include it.

### Live Checks

Live checks are opt-in and require:

```bash
export PAL_SSH_HOST=209.137.198.14
export PAL_SSH_PORT=18967
export PAL_SSH_KEY="$HOME/.ssh/pal_2026_vast"
```

Required live checks before marking the PRD deployable:

```bash
python -m promptclaw.cli pal health pal-2026
python -m promptclaw.cli pal smoke pal-2026
python -m promptclaw.cli pal agent triage pal-2026
python -m promptclaw.cli pal agent actions pal-2026 --task "Proposal-only approval gate check. Propose restart_router only."
python -m promptclaw.cli pal agent actions pal-2026 --task "Run read-only deep log inspection." --approve inspect_logs_deep
```

Mutating live checks such as `restart_router`, `pause_shutdown_once`, `resume_shutdown`, deploy apply, rollback, or any Vast API action must not run unless Anthony explicitly approves that exact action.

---

## Security Requirements

- Do not commit API keys, auth keys, private SSH keys, Tailscale auth keys, or Vast API tokens.
- Read secrets only from environment variables or existing local SSH config.
- Redact `PAL_SSH_KEY`, private key paths when necessary, tokens, API keys, and Authorization-like values from artifacts.
- Never expose PAL through public ports as part of this PRD.
- Treat Tailscale as the network boundary.
- Preserve approval gates for mutating actions.
- Unknown model-suggested actions must be ignored and recorded.
- Frontier SDP agents may write code, tests, docs, and local artifacts, but must not perform cloud spend operations.

---

## Deployment Requirements

Deployment is a product deliverable, but deployment execution must be gated:

1. Build and test locally.
2. Create dry-run deploy plan.
3. Show file diff and service impact.
4. Require explicit `--approve-deploy`.
5. Back up remote files.
6. Apply files.
7. Restart only approved service(s).
8. Verify `/health`, query, smoke, Tailscale, and process state.
9. Write deployment artifact locally under `.promptclaw/pal-deploy/`.

The deploy implementation must support the current host-managed PAL runtime. It may support Docker as an additional deployment mode, but Docker cannot be the only path.

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SDP agents assume Docker because older guide used Docker | High | Medium | PAL-010 and PAL-011 require host-managed restart selection tests and Docker fallback-only behavior. |
| Approval replay accidentally re-plans with model and executes a different action | Medium | High | PAL-002 forbids model calls during replay; tests must assert fake client is not called. |
| Knowledge index grows with noisy run artifacts | Medium | Low | PAL-013 through PAL-015 bind source discovery, chunking, and index writing to deterministic tests. |
| Live deployment apply breaks the PAL router | Medium | High | PAL-029 through PAL-031 require deploy plan, backup primitive, and explicit apply approval. |
| Secrets leak into artifacts | Medium | High | Verifier gate scans artifacts for env var names, key paths, and token-like values. |
| PAL recommends Phase 2 too early | Medium | Medium | PAL-022 requires a report-only workflow with no Phase 2 execution action. |
| Vast API connector causes spend or destructive actions | Low | High | PAL-036 and PAL-037 require stub-only Vast boundary and secret redaction tests. |

---

## Assumptions

1. PromptClaw remains the local control plane.
2. PAL router remains reachable over Tailscale at `http://pal-cloud-a6000:8000`.
3. The current Vast instance may be recreated in the future, so host, port, instance id, and SSH key path must be metadata/config, not hardcoded into source.
4. `sdp-cli` frontier agents can make better implementation choices than PAL's local 70B model; PAL should not self-modify this codebase.
5. Anthony prefers minimal involvement but still wants explicit approval for cost-bearing and mutating operations.
6. Phase 1 remains the active hardware target until Anthony explicitly authorizes Phase 2.

---

## Open Questions for SDP Agents to Resolve Without Blocking

These should not require Anthony unless the repo lacks enough information:

1. Whether to use SQLite FTS5 or a JSON-lines local index for PAL KB v0.
2. Whether approval replay writes into the original run directory or creates a linked child run.
3. Exact module boundaries for PAL workflows once implementation begins.
4. Whether deployment package files live under `pal-2026/deploy/` or `promptclaw/pal_deploy/` plus project templates.

If the agent makes a choice, document the decision in the relevant docs and artifacts.

---

## Operator Handoff to SDP

Validate the PRD without loading:

```bash
sdp-cli analyze --prd sdp/prd-pal-2026-agentic-ops-platform.md --validate-only
```

Load into the SDP queue when ready:

```bash
sdp-cli analyze --prd sdp/prd-pal-2026-agentic-ops-platform.md --load --merge append
```

Check task queue:

```bash
sdp-cli status
sdp-cli tasks list
```

Run the pipeline:

```bash
sdp-cli run-loop
```

After implementation tasks finish, stage/deploy using the SDP deploy path:

```bash
sdp-cli stage
sdp-cli deploy
```

Do not run mutating PAL deploy or cloud spend actions unless Anthony explicitly approves them after reading the generated dry-run plan.

---

## Project History

- v1.0 - 2026-05-15 - Initial SDP PRD for end-to-end PAL 2026 agentic operations, knowledge base, workflow engine, approval replay, deployment tooling, and verification gates.
