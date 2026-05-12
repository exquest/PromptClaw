# CypherClaw Generation Backend — Operator Runbook

**Audience:** on-call operator for CypherClaw audio generation.
**Scope:** the `senseweave.generation` package and its on-disk state under
`/home/user/cypherclaw-data/`. Three backends — Replicate (default),
Modal (GPU alternative), local deterministic preview — gated by a USD budget and a
weekly IDyOM long-term-model collapse audit.
**Source of truth:** code under
`my-claw/tools/senseweave/generation/` and
`sdp/telemetry/cost-model.md`. If this runbook disagrees with the code,
the code wins; fix the runbook in the same change.

---

## Part 1: At a Glance

### 1.1 Surfaces an operator touches

| Surface                    | On-disk path                                                            | Module                       |
|----------------------------|-------------------------------------------------------------------------|------------------------------|
| Budget state               | `/home/user/cypherclaw-data/state/generation_budget.json`               | `generation/budget.py`       |
| Generated audio            | `samples/generated/<YYYY-MM-DD>/<request_hash>.wav`                     | `generation/storage.py`      |
| Sensory journal            | `/home/user/cypherclaw-data/state/sensory_journal.jsonl`                | `senseweave/sensory_journal.py` |
| Sample-usage journal       | `samples/usage_journal.jsonl`                                           | `senseweave/usage_journal.py` |
| Generation queue (SQLite)  | `/home/user/cypherclaw-data/generation_queue.db`                        | `generation/queue.py`        |
| Generated cache root       | `/home/user/cypherclaw-data/cache/`                                     | `generation/cache.py`        |
| Cache index                | `<cache_root>/cache_index.json`                                         | `generation/cache.py`        |
| IDyOM live LTM             | `/home/user/cypherclaw-data/idyom/ltm.json`                             | `generation/health.py`       |
| IDyOM week-0 snapshot      | `/home/user/cypherclaw-data/idyom/ltm_week0_snapshot.json`              | `generation/health.py`       |
| IDyOM audit history        | `/home/user/cypherclaw-data/state/idyom_kl_audit.json`                  | `generation/health.py`       |
| Collapse alert (transient) | `/tmp/generation_collapse_alert.json`                                   | `generation/health.py`       |
| Audit config (operator)    | `my-claw/tools/senseweave/generation/idyom_kl_audit_config.json.example` | `generation/health.py`       |
| Queue worker service       | `my-claw/systemd/cypherclaw-generation-worker.service`                  | `/home/user/cypherclaw/tools/generation_worker.py` |

> **Note:** all dated directories and rollovers use **UTC**. Operators in
> PT should not expect the daily cap to reset at local midnight — it
> resets at UTC midnight (typically 4 PM PST / 5 PM PDT the previous
> calendar day).

### 1.2 Environment variables

| Variable                                | Default      | Where read                                         | Purpose                                                            |
|-----------------------------------------|--------------|----------------------------------------------------|--------------------------------------------------------------------|
| `CYPHERCLAW_GENERATION_DAILY_CAP_USD`   | `5.0`        | `generation/budget.py:18`                          | Hard daily USD cap before `allow()` rejects the request.           |
| `CYPHERCLAW_GENERATION_MONTHLY_CAP_USD` | `100.0`      | `generation/budget.py:19`                          | Hard monthly USD cap before `allow()` rejects the request.         |
| `IDYOM_KL_AUDIT_CONFIG`                 | _unset_      | `generation/health.py:306`                         | Path to JSON config consumed by the weekly collapse audit.         |
| `REPLICATE_API_TOKEN`                   | _unset_      | `replicate` SDK (transitively via `client_replicate.py`) | Required when the active backend is `replicate`.             |
| `MODAL_TOKEN_ID`                        | _unset_      | `modal` SDK (transitively via `client_modal.py`)   | Required when the active backend is `modal`.                       |
| `MODAL_TOKEN_SECRET`                    | _unset_      | `modal` SDK (transitively via `client_modal.py`)   | Required when the active backend is `modal`.                       |

If `CYPHERCLAW_GENERATION_DAILY_CAP_USD` parses but the value is not a
valid float, `budget.py` falls back to the constructor argument (or
`5.0` if none was passed). Empty string is treated as unset.

The local backend reads no env vars. `LocalAdaClient` writes a deterministic
mono WAV preview under the local generation temp directory and records
`cost_usd=0.0`, so it is useful for offline queue/cache/storage smoke tests.
It is not the future Ada GPU model.

### 1.3 Queue worker service

The generation queue is hosted by
`cypherclaw-generation-worker.service`. The unit lives at
`my-claw/systemd/cypherclaw-generation-worker.service` and starts:

```bash
/home/user/cypherclaw/.venv/bin/python3 /home/user/cypherclaw/tools/generation_worker.py
```

The unit reads `/home/user/cypherclaw/.env` via:

```ini
EnvironmentFile=/home/user/cypherclaw/.env
```

That env file must carry `REPLICATE_API_TOKEN` for the Replicate backend
and the budget caps `CYPHERCLAW_GENERATION_DAILY_CAP_USD` and
`CYPHERCLAW_GENERATION_MONTHLY_CAP_USD` when operators override the
defaults. The service runs as `user`, waits for
`cypherclaw-jack.service` and `network-online.target`, restarts
automatically, and is hardened with a strict read-only system view plus
write access to `/home/user/cypherclaw-data`.

### 1.4 Cost model

Per-second rates inside `generation/budget.py:25`:

| Model                | $/audio-sec | Notes                          |
|----------------------|-------------|--------------------------------|
| `musicgen-medium`    | `0.0050`    | Replicate default model        |
| `stable-audio-open`  | `0.0035`    | Replicate alternate model      |
| Modal A10G compute   | `0.000305`  | `~$1.10/hr`, in `client_modal.py` |

Estimate formula: `rate * duration_sec * 1.5` (1.5× overhead factor).
Realized cost is taken from `result.cost_usd` and added to the daily and
monthly counters via `GenerationBudget.record()`.

For the canonical SDP token + generation pricing reference, see
[`sdp/telemetry/cost-model.md`](../../sdp/telemetry/cost-model.md).

---

## Part 2: Daily Operations

### 2.1 Check generation status

Run from the project root:

```bash
# Today's USD spend and rolled-over date
python -c "from senseweave.generation.budget import GenerationBudget; \
b = GenerationBudget(); s = b.state; \
print(f'date={s.today_date} today=${s.today_spent_usd:.2f}/{b.daily_cap_usd:.2f} ' \
      f'month={s.month_key} spent=${s.month_spent_usd:.2f}/{b.monthly_cap_usd:.2f}')"
```

Expected output:

```
date=2026-04-27 today=$1.32/5.00 month=2026-04 spent=$48.71/100.00
```

Queue health:

```bash
sqlite3 /home/user/cypherclaw-data/generation_queue.db \
  "SELECT status, COUNT(*) FROM queue_items GROUP BY status;"
```

A healthy queue is mostly `done` with at most `max_concurrent` (default
`1`) row in `running`. Anything in `blocked` is waiting on the budget
gate (see Part 3.1).

Collapse alert (only present when the audit has just flagged drift):

```bash
test -f /tmp/generation_collapse_alert.json && cat /tmp/generation_collapse_alert.json || echo "no active alert"
```

Recent generated audio:

```bash
ls -lt samples/generated/$(date -u +%F)/ | head
```

### 2.2 Inspect the cache

The cache is content-addressed (SHA256 of the request) and LRU-evicted
by `accessed_at`. Defaults: `max_entries=256`, `max_size_gb=5.0`.

```bash
ls /home/user/cypherclaw-data/cache/ | wc -l                  # entry count
du -sh /home/user/cypherclaw-data/cache/                       # total size
jq 'to_entries | sort_by(.value.accessed_at) | .[0:5]' \
   /home/user/cypherclaw-data/cache/cache_index.json           # 5 oldest
```

> **Warning:** never `rm` cache files without also editing
> `cache_index.json`. The index is the source of truth for LRU; orphaned
> index entries will resurface as misses *and* skew eviction. To clear
> the cache safely, delete the entire directory and let it rebuild.

### 2.3 Inspect on-disk audio and journals

```bash
# Latest 10 generated audio files across all days
find samples/generated -name '*.wav' -printf '%T@ %p\n' | sort -n | tail
# Tail the sensory journal (one JSON event per line)
tail -n 5 /home/user/cypherclaw-data/state/sensory_journal.jsonl | jq .
# Sample-usage journal (per-piece sampler events from CCS-028)
tail -n 5 samples/usage_journal.jsonl | jq .
```

---

## Part 3: Configuration Changes

### 3.1 Widen or tighten the budget caps

Caps are read from env at `GenerationBudget.__init__`. The daemon reads
them once at startup; restart the generation queue to pick up a change.

```bash
# Widen daily cap to $10 for one shift (does not persist across reboot)
sudo systemctl edit cypherclaw-generation-worker.service
# Add under [Service]:
#   Environment=CYPHERCLAW_GENERATION_DAILY_CAP_USD=10.0
sudo systemctl restart cypherclaw-generation-worker.service

# Tighten daily cap to $2 for a cool-down period
sudo systemctl edit cypherclaw-generation-worker.service
# Environment=CYPHERCLAW_GENERATION_DAILY_CAP_USD=2.0
sudo systemctl restart cypherclaw-generation-worker.service
```

To revert to default, drop the override and restart:

```bash
sudo systemctl revert cypherclaw-generation-worker.service
sudo systemctl restart cypherclaw-generation-worker.service
```

> **Note:** changing the cap does not retroactively re-admit blocked
> items. Items that were rejected with `daily cap reached` need to be
> re-enqueued (see Part 3.4).

### 3.2 Switch backend (Replicate ↔ Modal ↔ local)

Backend is a per-request field on `GenerationRequest.backend` (Literal
`"replicate" | "modal" | "local"`). The default in `request.py` is
`"replicate"`. The conditioner
(`generation/conditioner.py::GenerationConditioner.build_request`) emits
the per-request value. To switch the cluster default, change the
conditioner — or, for a one-shift override, set the backend at
enqueue time.

Procedure:

1. Confirm credentials are present for the target backend:
   - `replicate`: `REPLICATE_API_TOKEN` set.
   - `modal`: `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` set; the Modal app
     `cypherclaw-musicgen` is deployed.
   - `local`: no credentials required. `LocalAdaClient.generate()` writes a
     deterministic local WAV preview with `cost_usd=0.0`. Use it for offline
     queue/cache/storage smoke tests, not for production-quality Ada output.
2. Drain the queue: stop the worker, wait for the `running` row to settle.
3. Update the conditioner (or override at the call site) to emit the new
   backend value.
4. Restart the worker.
5. Verify with one test enqueue and tail the queue table.

> **Warning:** switching to `local` before the GPU is installed will
> fail every request. Use `modal` if you need to stop spending on
> Replicate but the GPU is not yet online.

### 3.3 Roll back the IDyOM long-term model

The collapse audit (`generation/health.py::idyom_kl_divergence_audit`)
runs weekly via `cypherclaw-idyom-kl-audit.timer`. It writes the alert
file `/tmp/generation_collapse_alert.json` when **all three** signals
flag (positive KL slope **and** generated-audio ratio ≥ 0.5 **and**
negative CLAP centroid-variance slope across ≥3 history points).
**Rollback is never automatic.** When the alert fires:

```bash
# 1. Confirm the alert
cat /tmp/generation_collapse_alert.json

# 2. Stop the generation worker so no new LTM updates land mid-rollback
sudo systemctl stop cypherclaw-generation-worker.service

# 3. Back up the divergent LTM (so you can post-mortem it later)
cp /home/user/cypherclaw-data/idyom/ltm.json \
   /home/user/cypherclaw-data/idyom/ltm.divergent.$(date -u +%Y%m%dT%H%M%SZ).json

# 4. Restore from the immutable week-0 snapshot
cp /home/user/cypherclaw-data/idyom/ltm_week0_snapshot.json \
   /home/user/cypherclaw-data/idyom/ltm.json

# 5. Acknowledge and clear the alert
rm /tmp/generation_collapse_alert.json

# 6. Restart and observe
sudo systemctl start cypherclaw-generation-worker.service
```

The audit history at
`/home/user/cypherclaw-data/state/idyom_kl_audit.json` is **not**
truncated by the rollback — the rolling 8-week window remains intact so
the next audit can compare against pre-rollback history.

The audit config schema is documented in
[`my-claw/tools/senseweave/generation/idyom_kl_audit_config.json.example`](../../my-claw/tools/senseweave/generation/idyom_kl_audit_config.json.example);
edits to the live config (path pointed to by `IDYOM_KL_AUDIT_CONFIG`)
take effect on the next timer fire.

### 3.4 Clear stuck queue items

A "stuck" item is one in `running` for far longer than the client
timeout (default `120 s`) — typically because the backend died
mid-generation. The queue does not auto-detect this.

```bash
# Identify
sqlite3 /home/user/cypherclaw-data/generation_queue.db \
  "SELECT id, idempotency_key, status, attempts, updated_at, last_error
   FROM queue_items
   WHERE status='running'
   ORDER BY updated_at;"

# Requeue a single stuck row (replace 42 with the real id)
sqlite3 /home/user/cypherclaw-data/generation_queue.db \
  "UPDATE queue_items
   SET status='queued', last_error='manual requeue: stuck running'
   WHERE id=42 AND status='running';"

# Or, if attempts are exhausted, mark it failed and move on
sqlite3 /home/user/cypherclaw-data/generation_queue.db \
  "UPDATE queue_items
   SET status='failed', last_error='manual fail: attempts exhausted'
   WHERE id=42 AND status='running';"
```

For items in `blocked` (rejected by the budget gate): widen the cap
(Part 3.1), then `UPDATE ... SET status='queued'` for the rows you want
re-admitted. Rows older than the retention window can be deleted
outright.

---

## Part 4: Debugging Scenarios

Five worked scenarios covering the most common operator pages.

### Scenario 1: "No new audio for the past hour"

**Symptom:** `samples/generated/<today>/` has not gained a file in 60+
minutes; the duet composer still appears to be running.

1. Check the daily cap:
   ```bash
   python -c "from senseweave.generation.budget import GenerationBudget; \
   s = GenerationBudget().state; \
   print(s.today_date, f'${s.today_spent_usd:.2f}')"
   ```
   If `today_spent_usd` is at or near `5.00`, the cap has been hit and
   `allow()` is refusing every request.
2. Check the queue:
   ```bash
   sqlite3 /home/user/cypherclaw-data/generation_queue.db \
     "SELECT status, COUNT(*) FROM queue_items GROUP BY status;"
   ```
   Many `blocked` rows confirm the diagnosis.
3. Resolve: either wait until UTC midnight for the daily reset, or widen
   the cap (Part 3.1) and re-queue the blocked rows. Record the override
   in `progress.md` — caps exist for a reason.

### Scenario 2: "Queue is wedged on a `running` row"

**Symptom:** `status=running` for one row, `updated_at` older than ~5
minutes, no `done` rows in the same window.

1. Confirm the worker is alive: `systemctl is-active cypherclaw-generation-worker.service`.
2. If alive, look for the matching log line: `journalctl -u cypherclaw-generation-worker.service --since '15 minutes ago' | grep -i error`.
3. If a Replicate `5xx` or 429 storm is in the logs, the retry layer
   will keep trying for up to 5 m 35 s (`5 + 30 + 300`). Wait it out
   first.
4. If the log is silent and the row is older than 10 m, requeue it
   (Part 3.4).
5. If the row keeps re-stucking, switch backend to Modal (Part 3.2)
   while you investigate Replicate health.

### Scenario 3: "Cache is cold / hit rate has dropped to zero"

**Symptom:** every request takes the full Replicate latency; `du
-sh /home/user/cypherclaw-data/cache/` shows < 1 MB.

1. Confirm the cache root is the one the worker is using: grep the
   worker config or `cypherclaw-generation-worker.service` for the cache path.
2. Inspect the index for missing entries:
   ```bash
   jq 'length' /home/user/cypherclaw-data/cache/cache_index.json
   ls /home/user/cypherclaw-data/cache/ | wc -l
   ```
   If `index length << file count`, the index file was truncated;
   restore from backup or delete the directory and let it rebuild.
3. If the disk filled, eviction has been thrashing. `du -sh
   /home/user/cypherclaw-data/` will show the offender; clear stale
   audit history or rotate logs.
4. If the cache root is missing entirely (fresh box), creating it lets
   the worker fill it on next run: `mkdir -p /home/user/cypherclaw-data/cache`.

### Scenario 4: "Collapse alert fired"

**Symptom:** `/tmp/generation_collapse_alert.json` exists; output starts
sounding monotonous or self-referential.

1. Read the alert payload:
   ```bash
   jq . /tmp/generation_collapse_alert.json
   ```
   Confirm all three signals tripped (KL slope > 0, generated_ratio ≥
   0.5, CLAP centroid-variance slope < 0). If only two tripped, the
   audit should not have fired — file an ESCALATION and inspect
   `generation/health.py`.
2. Roll back the LTM (Part 3.3).
3. After restart, confirm the next audit run succeeds:
   `systemctl status cypherclaw-idyom-kl-audit.service`. The next timer
   fire should produce a fresh entry in
   `/home/user/cypherclaw-data/state/idyom_kl_audit.json` without re-flagging.
4. Capture the divergent LTM you saved in step 3 of the rollback into
   the artistic-direction post-mortem.

### Scenario 5: "Replicate is down — failover to Modal"

**Symptom:** Replicate status page shows an outage; queue rows fail
with `ReplicateAPIError 5xx` after the full retry schedule.

1. Verify Modal credentials are loaded:
   ```bash
   modal token current     # should print the active token id, not error
   ```
2. Confirm the Modal app is deployed:
   ```bash
   modal app list | grep cypherclaw-musicgen
   ```
3. Switch the conditioner default to `"modal"` (Part 3.2) and restart
   the worker.
4. Re-queue the failed rows by setting `status='queued'` for rows whose
   `last_error` matches the Replicate outage window.
5. After Replicate recovers, switch back. Modal at A10G is roughly 3×
   cheaper per second of compute but has a different cost shape — check
   `today_spent_usd` after the first few rows complete to confirm the
   estimate is tracking realized spend.

---

## Part 5: Verification

To confirm a change to this runbook has not drifted from the live
system, run:

```bash
pytest tests/test_runbook_generation_backend.py -q
```

For a full pre-commit gate:

```bash
pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/
```
