# PAL Product Surface

Consolidated reference for the PAL 2026 product surface PromptClaw exposes
today. It lists every shipped PAL CLI command, every PAL Python module, the
artifacts those commands write, and the host-managed `/opt/pal` deployment
layout PAL targets on a Phase 1 router host.

See also: `docs/architecture.md` (PAL platform component), `docs/command-reference.md`
(authoritative CLI flag reference), and `pal-2026/docs/PROJECT_GUIDE.md`
(operator loop and live verification commands).

## PAL Commands

All commands take a `PROJECT_ROOT` and read the `pal` section from
`promptclaw.json`. Commands are grouped by what they touch.

### Router calls (contact the live PAL router)

- `promptclaw pal health PROJECT_ROOT` — call `/health` on the configured PAL
  router.
- `promptclaw pal query PROJECT_ROOT --prompt TEXT [--system ...] [--model ...] [--temperature N] [--text]` —
  send a direct prompt to the configured PAL router.
- `promptclaw pal smoke PROJECT_ROOT [--output PATH] [--json]` — run the fixed
  restart smoke suite against the router.
- `promptclaw pal validate restart PROJECT_ROOT [--json]` — restart-validation
  workflow (router + smoke + Tailscale + optional read-only SSH process check).
- `promptclaw pal audit shutdown PROJECT_ROOT [--json]` — shutdown-audit
  workflow (read-only SSH inspection of shutdown config, cron, override flag,
  logs).
- `promptclaw pal report phase2-readiness PROJECT_ROOT [--json]` — score Phase 2
  prerequisites (read-only, no execution surface).
- `promptclaw pal diagnose slow-inference PROJECT_ROOT [--json]` — read-only
  slow-inference diagnosis (health, baseline token/s, optional GPU hints,
  optional router/Ollama log tails).
- `promptclaw pal agent triage PROJECT_ROOT` — bounded PAL agent triage
  workflow. PAL proposes a tool plan from the read-only allow-list; PromptClaw
  executes only `pal_health`, `pal_smoke_baseline`, `tailscale_status`, and
  (when `PAL_SSH_HOST` / `PAL_SSH_PORT` / `PAL_SSH_KEY` are set)
  `ssh_process_check`.
- `promptclaw pal agent actions PROJECT_ROOT [--approve ACTION_ID ...]` —
  approval-gated action layer. Executes nothing by default; `--approve` runs
  individual ids from the action allow-list.

### Local-only commands (no router contact)

- `promptclaw pal baseline PROJECT_ROOT [--json]` — summarize saved smoke
  reports.
- `promptclaw pal kb build PROJECT_ROOT [--max-chars N] [--output PATH] [--json]` —
  build the local PAL knowledge index from `pal.knowledge_sources`.
- `promptclaw pal kb query PROJECT_ROOT --query TEXT [--limit N] [--index PATH] [--json]` —
  query the local knowledge index for ranked snippets.
- `promptclaw pal deploy plan PROJECT_ROOT [--remote-inventory PATH] [--json]` —
  dry-run deployment plan for the repo-managed manifest; prints diff sets and
  service impacts without remote writes.
- `promptclaw pal deploy apply PROJECT_ROOT --remote-inventory PATH --approve-apply [--json]` —
  apply managed manifest changes to a supplied local fake remote inventory after
  explicit approval.
- `promptclaw pal deploy rollback PROJECT_ROOT --remote-inventory PATH --backup-id ID --approve-rollback [--json]` —
  restore a local PAL deploy backup into a supplied local fake remote inventory
  after explicit approval.

### Action allow-list

`promptclaw pal agent actions --approve ACTION_ID` accepts these ids today:

- `rerun_smoke` — run the PAL smoke suite and save a fresh local report.
- `inspect_logs_deep` — fixed read-only SSH log/resource inspection.
- `restart_router` — restart only the PAL FastAPI router service.
- `pause_shutdown_once` — create `/opt/pal/config/override.flag`.
- `resume_shutdown` — remove `/opt/pal/config/override.flag`.

The Vast connector is a stub boundary: `rent`, `destroy`, `start`, and `stop`
are recorded as blocked lifecycle operations with no callable action ids.

## PAL Modules

PAL ships as a set of Python modules in the `promptclaw` package:

- `promptclaw.pal_client` — `PALRouterClient`, `PALQueryResult`, and
  `PALClientError`. Thin HTTP client for the router `/health` and `/query`
  endpoints.
- `promptclaw.pal_smoke` — `run_pal_smoke`, smoke-report writer, and
  `summarize_pal_smoke_baseline` for the baseline command.
- `promptclaw.pal_knowledge` — local knowledge-base source discovery,
  deterministic chunking with `pal-kb:` chunk ids,
  `write_pal_knowledge_index`, and `query_pal_knowledge_index`.
- `promptclaw.pal_agent` — bounded PAL workflows: `run_pal_ops_triage`,
  `run_pal_ops_actions`, `run_pal_slow_inference_diagnosis`,
  `run_pal_restart_validation`, `run_pal_shutdown_audit`, and
  `run_pal_phase2_readiness_report`. Also exposes the slow-inference context
  primitive `run_pal_slow_inference_context`.
- `promptclaw.pal_deploy` — deployment manifest loader,
  `diff_pal_deployment`, `build_fake_pal_remote_inventory` test helper,
  `build_pal_deploy_plan`, `format_pal_deploy_plan`,
  `apply_pal_deployment_changes`, `rollback_pal_deployment_backup`,
  `load_pal_deployment_backup`, and `load_pal_remote_inventory_snapshot`.
- `promptclaw.vast_connector` — non-executing Vast lifecycle stub boundary.
  Records blocked operations; exposes `callable_actions=[]`.

CLI wiring lives in `promptclaw.cli` under the `promptclaw pal` subparser.

## PAL Artifacts

Local files written by PAL commands. All paths are relative to `PROJECT_ROOT`.

### Knowledge base

- `.promptclaw/pal-kb/index.jsonl` — local JSONL knowledge index written by
  `pal kb build`.

### Smoke baseline

- `.promptclaw/pal-smoke/pal-smoke-<timestamp>.json` — full smoke report (one
  per `pal smoke` invocation; also produced by `rerun_smoke`).

### Workflow runs

Every PAL workflow writes a normal run directory under
`.promptclaw/runs/<run-id>/` with the standard PromptClaw run artifacts (plan,
events, state, route, summary, handoff) plus a workflow-specific output JSON:

| Command | Workflow output |
|---|---|
| `pal agent triage` | standard triage plan / observations / summary |
| `pal agent actions` | `outputs/action-results.json` (action plan + per-action results) |
| `pal diagnose slow-inference` | `outputs/slow-inference-diagnosis.json` |
| `pal validate restart` | `outputs/restart-validation.json` |
| `pal audit shutdown` | `outputs/shutdown-audit.json` |
| `pal report phase2-readiness` | `outputs/phase2-readiness.json` |
| `run_pal_slow_inference_context` (primitive) | `outputs/slow-inference-context.json` |

Every workflow `run-summary.json` carries `workflow_id`, a workflow-specific
status field, the executed tool list, and `mutating_actions` (empty for
read-only workflows).

### Deployment

- `pal-2026/ops/deployment-manifest.json` — repo-managed source of truth for
  intended `/opt/pal` files.
- `pal deploy plan` is dry-run only: it writes no run artifact and performs no
  remote writes. Output is stdout (human or `--json`).
- `pal deploy apply` writes changed backups under
  `.promptclaw/pal-deploy/backups/<backup-id>/` and mutates only the supplied
  fake remote inventory JSON after `--approve-apply`.
- `pal deploy rollback` restores from
  `.promptclaw/pal-deploy/backups/<backup-id>/` and mutates only the supplied
  fake remote inventory JSON after `--approve-rollback`.

## Host-managed `/opt/pal` Layout

PAL's Phase 1 router runs as a host-managed deployment under `/opt/pal`. The
manifest at `pal-2026/ops/deployment-manifest.json` lists the managed files
the deploy diff model compares against the remote host.

Managed files:

| Target path | Kind | Mode | Service impact |
|---|---|---|---|
| `/opt/pal/scripts/start_all.sh` | script | 0755 | all |
| `/opt/pal/scripts/start_ollama.sh` | script | 0755 | ollama |
| `/opt/pal/scripts/start_router.sh` | script | 0755 | router |
| `/opt/pal/scripts/auto_shutdown.sh` | script | 0755 | shutdown-scheduler |
| `/opt/pal/config/shutdown.conf` | config | 0644 | shutdown-scheduler |
| `/opt/pal/router/app.py` | router | 0644 | router |
| `/opt/pal/DEPLOYMENT_INFO.md` | metadata-template | 0644 | none |
| `/opt/pal/router/Dockerfile` | docker-fallback | 0644 | docker-fallback |
| `/opt/pal/docker-compose.yml` | docker-fallback | 0644 | docker-fallback |

Runtime directories the host owns but the manifest does not sync:
`/opt/pal/config`, `/opt/pal/logs`, `/opt/pal/ollama`, `/opt/pal/router`,
`/opt/pal/scripts`.

Excluded runtime paths (treated as unmanaged-remote, never compared):

- `/opt/pal/logs/*.log`
- `/opt/pal/logs/*.pid`
- `/opt/pal/ollama/**`
- `/opt/pal/config/override.flag`
- `/opt/pal/router/__pycache__/**`

The router prefers `/opt/pal/scripts/start_router.sh` when `restart_router`
runs; the Docker compose path under `/opt/pal/docker-compose.yml` is the
fallback when the host script is absent.
