# PRD: Home Resilience — Durable State, Safe Reboot, and Recovery

## Incident Trigger

On 2026-03-31, a reboot wiped tmpfs-backed runtime queue state. The live `sdp-cli` backlog dropped from `134/276` progress to an 11-task fallback graph and had to be manually reconstructed from partial backups, run logs, and PRD sources. That failure mode is unacceptable for CypherClaw's home.

This PRD turns that incident into immediate operational work. The goal is not "better backups" in the abstract. The goal is that a clean reboot, an I/O-guard intervention, or a single-service crash must never again destroy or materially rewind the authoritative queue.

This PRD narrows and overrides the tmpfs-as-authority assumptions in [prd-server-optimization.md](./prd-server-optimization.md). From this point forward:

1. Disk is authority.
2. Tmpfs is acceleration only.
3. Every important process is systemd-managed.
4. Every reboot begins with a checkpoint and ends with a verification gate.

## Overview

CypherClaw is not a stateless bot. It is a long-running organism with memory, queue state, observatory history, and in-flight orchestration decisions. Its home must behave accordingly.

This PRD hardens four specific areas:

1. **State authority** — the queue DB and observatory DB must survive reboot without reconstruction.
2. **Process authority** — the daemon and runner must start, stop, and recover through systemd rather than ad hoc shell sessions.
3. **Maintenance authority** — reboot must become a scripted maintenance flow with checkpoint, drain, shutdown, boot validation, and resume.
4. **Recovery authority** — backup and restore must be direct, tested, and observable.

## Execution Role

This is **Stage 1** of the execution spine. Do not treat it as one PRD among many. It is the foundation for everything that follows.

The intended order after this PRD is:

1. `prd-home-resilience.md`
2. `prd-restructure.md`
3. `prd-model-awareness.md`
4. `prd-agent-runtime-substrate.md`
5. `prd-capability-approval-framework.md`
6. `prd-verification-system.md`
7. `prd-context-engine.md`
8. `prd-introspector.md`
9. `prd-web-platform.md`

Work that depends on durable state, continuous queue execution, or trustworthy reboot behavior should not outrun this PRD.

## Design Principles

1. **No critical memory lives only in RAM.**
   Tmpfs is allowed for caches, workspaces, logs, and transient model scratch space. It is not allowed to be the sole authority for queue state or observatory history.

2. **No critical process runs outside systemd.**
   If a process matters after reboot, it must have a unit file, health expectations, restart policy, and ordered dependencies.

3. **No reboot without a checkpoint.**
   A reboot is a maintenance action. It must produce a durable checkpoint artifact before shutdown and a validated resume decision after boot.

4. **No restore path that has not been drilled.**
   Backups that have never been restored are only hopeful copies.

5. **Safety beats speed.**
   A slower clean shutdown is preferable to a fast reboot that risks silent state loss.

## Scope

**In scope**
- `sdp-cli` queue durability
- Observatory durability
- tmpfs bootstrap behavior
- runner lifecycle management
- I/O guard behavior during distress
- safe reboot workflow
- backup, restore, and validation tooling
- secret hygiene for operational scripts and units

**Out of scope**
- new product features
- agent routing improvements unrelated to durability
- UI redesigns
- non-essential performance tuning

## Affected Runtime Paths

- Queue DB: `/home/user/cypherclaw/.sdp/state.db`
- Observatory DB: `/home/user/cypherclaw/.promptclaw/observatory.db`
- Tmpfs root: `/run/cypherclaw-tmp/`
- Bootstrap script: `tools/init_workdir.sh`
- I/O guard: `tools/io_guard.sh`
- Runner command: `sdp-cli run`
- Daemon service: `cypherclaw.service`

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| HOME-001 | Make the live queue DB authoritative on disk. `sdp.toml` must point to the persistent disk path for `state.db`, and no reboot/bootstrap path may replace the live disk DB with a tmpfs copy. | MUST | T1 | - Live queue authority is `/home/user/cypherclaw/.sdp/state.db`<br/>- Reboot preserves queue counts without reconstruction<br/>- `tools/init_workdir.sh` no longer promotes tmpfs DB copies over disk authority |
| HOME-002 | Make the Observatory DB authoritative on disk and explicitly preserve it across reboot. Tmpfs may cache reads or logs, but not replace observatory authority. | MUST | T1 | - Live observatory authority is `/home/user/cypherclaw/.promptclaw/observatory.db`<br/>- Reboot preserves observatory row counts and WAL integrity<br/>- Bootstrap does not create a fresh empty authoritative observatory DB |
| HOME-003 | Replicate the live authority DBs directly. `litestream` must replicate the live `state.db` and `observatory.db` paths, not indirect backup copies. | MUST | T1 | - `/etc/litestream.yml` points at live DB files<br/>- snapshot/restore from litestream succeeds for both DBs<br/>- replication lag is visible in logs or status output |
| HOME-004 | Add a checkpoint exporter. Create `tools/runtime_checkpoint.py` that writes a timestamped checkpoint manifest containing queue totals, per-PRD totals, active task, recent `task_runs`, DB file size, and integrity-check result. | MUST | T1 | - Manifest written to `.sdp/recovery/` before maintenance actions<br/>- Manifest contains enough data to detect rewind after reboot<br/>- Export runs in under 10 seconds |
| HOME-005 | Add a preflight validator. Create `tools/preflight.py` that validates DB integrity, service prerequisites, queue sanity, lock-file sanity, and backup freshness before allowing the runner to start. | MUST | T1 | - Fails closed on invalid DB or missing dependencies<br/>- Detects orphaned lock files and stale tmpfs state<br/>- Emits machine-readable and human-readable output |
| HOME-006 | Create `cypherclaw-sdp-runner.service` and move `sdp-cli run` under systemd. The queue runner must no longer rely on `nohup`, ad hoc shells, or manual restart. | MUST | T1 | - Runner starts via `systemctl start cypherclaw-sdp-runner.service`<br/>- `Restart=on-failure` is enabled<br/>- Logs are journaled and visible without tailing a custom shell log<br/>- Reboot restores runner under ordered startup |
| HOME-007 | Create a dedicated bootstrap layer for tmpfs and workdir prep. Add `cypherclaw-bootstrap.service` to initialize caches, workdirs, and symlinks without owning the authority DBs. | MUST | T1 | - Bootstrap runs before daemon and runner<br/>- tmpfs directories exist after boot<br/>- bootstrap is idempotent<br/>- bootstrap never downgrades live DB state |
| HOME-008 | Add maintenance mode. Create a script or daemon hook that stops new intake, opens the circuit breaker, and drains or pauses runner work before shutdown or disruptive maintenance. | MUST | T1 | - Maintenance mode can be entered explicitly<br/>- New tasks stop entering the queue during maintenance<br/>- Current task is either drained cleanly or returned to a safe pending state |
| HOME-009 | Create `tools/safe_reboot.sh` to perform checkpoint, maintenance-mode drain, service shutdown, reboot, post-boot validation, and resume. | MUST | T2 | - Script checkpoints before reboot<br/>- Stops services in a defined order<br/>- Verifies post-boot counts against checkpoint manifest<br/>- Refuses to resume runner if validation fails |
| HOME-010 | Rework `tools/io_guard.sh` to prefer graceful protection over kill-first behavior. The I/O guard must checkpoint and request controlled runner shutdown before escalating to hard kills. | MUST | T2 | - First response is maintenance + stop/drain, not `SIGKILL`<br/>- Hard kill only happens after configurable timeout or repeated failure<br/>- I/O guard emits a checkpoint before forced termination whenever possible |
| HOME-011 | Remove hardcoded operational secrets from scripts and unit files. API keys and bot tokens must come from environment files or a secret store, not inline shell variables. | MUST | T1 | - No hardcoded Telegram bot token in `io_guard.sh`<br/>- No hardcoded model/API secret in systemd unit files<br/>- Secret source is documented and permission-scoped |
| HOME-012 | Add a restore tool and drill procedure. Create `tools/restore_checkpoint.sh` or equivalent to restore from local snapshots or litestream, and define a monthly recovery drill. | MUST | T2 | - Restore path works from local snapshot and litestream snapshot<br/>- Drill procedure is documented and repeatable<br/>- Recovery objective is measured after each drill |
| HOME-013 | Add reboot and recovery alerts. Telegram must receive concise messages for maintenance mode entry, checkpoint success/failure, boot validation pass/fail, runner resume, and restore actions. | SHOULD | T1 | - Every major maintenance step emits an alert<br/>- Alerts stay under 300 chars<br/>- Failures are obvious and actionable |
| HOME-014 | Add a post-boot reconciliation check. After boot, compare current queue totals, per-PRD totals, and recent run history to the latest checkpoint manifest before reopening the runner. | MUST | T1 | - Reconciliation detects count mismatch and refuses auto-resume<br/>- Differences are summarized in one report<br/>- Successful reconciliation records an explicit observatory event |
| HOME-015 | Ensure task-level escalation does not halt the entire queue. When a task exhausts retries or is marked `blocked`, the runner must record the failure, alert Anthony, and continue to the next pending task. Only infrastructure failure, failed preflight, or explicit maintenance mode may stop the whole queue. | MUST | T1 | - Escalated tasks become `blocked` without terminating the queue loop<br/>- Next pending task starts automatically<br/>- Whole-run stop is reserved for infrastructure failure, failed preflight, or maintenance mode<br/>- Continuation behavior is visible in logs and Observatory |

## Immediate Implementation Order

This work is P0. Do not treat it as background maintenance. It is the next operational feature set.

Implement in this exact order:

1. **HOME-001** — lock in disk authority for `state.db`.
2. **HOME-002** — lock in disk authority for `observatory.db`.
3. **HOME-003** — point `litestream` at the live authority DBs.
4. **HOME-006** — create `cypherclaw-sdp-runner.service`.
5. **HOME-007** — split bootstrap into a real pre-start service.
6. **HOME-015** — make blocked-task continuation the default queue behavior.
7. **HOME-004** — add checkpoint export.
8. **HOME-005** — add preflight validation.
9. **HOME-008** — add maintenance mode.
10. **HOME-009** — add `safe_reboot.sh`.
11. **HOME-010** — downgrade I/O guard from kill-first to checkpoint-and-drain-first.
12. **HOME-011** — remove hardcoded secrets from scripts and units.
13. **HOME-014** — add post-boot reconciliation gate.
14. **HOME-012** — add restore tooling.
15. **HOME-013** — add explicit maintenance and recovery alerts.
16. Run a full live drill: checkpoint, clean reboot, validation, runner resume, and restore test.

## Immediate Task Breakdown

These are the first concrete implementation tasks to queue right away:

1. Patch `tools/init_workdir.sh` so it never copies an authority DB into place over the live disk DB.
2. Patch runtime config so both queue and observatory authority are explicitly on disk.
3. Update `/etc/litestream.yml` to replicate the live DB files directly.
4. Create `systemd/cypherclaw-sdp-runner.service`.
5. Create `systemd/cypherclaw-bootstrap.service`.
6. Patch `sdp-cli` runner behavior so a blocked task does not stop the full queue.
7. Implement `tools/runtime_checkpoint.py`.
8. Implement `tools/preflight.py`.
9. Implement `tools/maintenance_mode.py` or `tools/maintenance_mode.sh`.
10. Implement `tools/safe_reboot.sh`.
11. Refactor `tools/io_guard.sh` to checkpoint first and hard-kill only as a last resort.
12. Move tokens and API keys out of scripts and unit files.
13. Implement `tools/restore_checkpoint.sh`.
14. Run a clean reboot drill and verify zero queue rewind.

## Phase Plan

### Phase 0: Authority Lock-In
HOME-001, HOME-002, HOME-003

State and backup authority must be correct before any other resilience work matters.

### Phase 1: Managed Lifecycle
HOME-006, HOME-007, HOME-015, HOME-008

Runner and bootstrap must become explicit services with a maintenance gate.

### Phase 2: Safe Reboot
HOME-004, HOME-005, HOME-009, HOME-014

Checkpoint, validation, reboot, reconciliation, and safe resume become one coherent flow.

### Phase 3: Distress Handling
HOME-010, HOME-013

The system must degrade gracefully under I/O or service distress and report what it is doing.

### Phase 4: Recovery Discipline
HOME-011, HOME-012

Secrets are cleaned up and restore drills become a standing operational habit.

## Success Metrics

| Metric | Target |
|--------|--------|
| Queue rewind after clean reboot | 0 tasks |
| RPO for queue state | <1 minute |
| RTO for clean reboot | <10 minutes |
| Runner restart path | 100% systemd-managed |
| Boot reconciliation false negative rate | 0 |
| Restore drill success rate | 100% monthly |
| Hardcoded operational secrets in repo-managed scripts | 0 |

## Definition of Done

This PRD is done only when all of the following are true:

1. A clean reboot preserves queue counts and active PRD totals without manual recovery.
2. A runner crash restarts under systemd after passing preflight.
3. A checkpoint manifest exists for every planned reboot.
4. `litestream` can restore the live queue DB directly.
5. The I/O guard no longer jumps straight to destructive termination.
6. A restore drill has been executed successfully and recorded.
