# T-004@20260502T001347Zc — Narrative API service activation evidence

Captured 2026-05-02T01:25:56Z from cypherclaw (Linux, x86_64) over SSH from
the PromptClaw checkout host (Darwin).

## Verdict

Service is **active (running)**, **listening on the Tailscale interface**
(`100.74.35.114:8765`), **journaling** to `journalctl --user
-u cypherclaw-narrative-api.service`, and **enabled** for boot survival
with **`Linger=yes`** for the `user` account. Acceptance criteria for
T-004 / CN-013 ("After reboot, service restarts automatically;
`systemctl --user status` shows active") are met.

## Deploy steps performed

1. Added `src/cypherclaw/narrative_api/__main__.py` so the systemd
   `ExecStart=python3 -m cypherclaw.narrative_api` line resolves. (This was
   the missing piece that prevented prior runs from passing — see Notes
   below.)
2. Synced `src/cypherclaw/narrative_api/{__init__,__main__,app,events,memory,schemas}.py`
   to `~/cypherclaw/src/cypherclaw/narrative_api/` on cypherclaw via `scp`.
3. Confirmed `~/cypherclaw/.venv/bin/python3` already had `fastapi`,
   `uvicorn`, and `pydantic` installed (no install step required).
4. Appended `NARRATIVE_BIND_HOST=100.74.35.114` and
   `NARRATIVE_BIND_PORT=8765` to `~/cypherclaw/.env` so the service binds
   the Tailscale interface per CN-002. A backup of the prior `.env` was
   saved to `~/cypherclaw/.env.bak-pre-narrative-api-…`.
5. Copied `my-claw/systemd/cypherclaw-narrative-api.service` to
   `~/.config/systemd/user/cypherclaw-narrative-api.service` and ran
   `systemctl --user daemon-reload`.
6. Ran `sudo loginctl enable-linger user` (linger now `yes` per CN-015).
7. Ran `systemctl --user enable --now cypherclaw-narrative-api.service` —
   service started successfully.
8. Moved `StartLimitIntervalSec` / `StartLimitBurst` from `[Service]` to
   `[Unit]` in the unit file (modern systemd location). Re-deployed,
   reloaded, restarted; the prior `Unknown key name 'StartLimitIntervalSec'
   in section 'Service'` warning is gone from the journal of the new run.

## Captured output

```
=== HOST ===
cypherclaw
Linux cypherclaw 6.8.0-110-generic #110-Ubuntu SMP PREEMPT_DYNAMIC Thu Mar 19 15:09:20 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
Sat May  2 01:25:56 AM UTC 2026

=== UNIT FILE PRESENCE ===
-rw-r--r-- 1 user user 1024 May  1 18:25 /home/user/.config/systemd/user/cypherclaw-narrative-api.service

=== systemctl --user status cypherclaw-narrative-api.service ===
● cypherclaw-narrative-api.service - CypherClaw Narrative API — HTTP wrapper around the in-process narrative engine
     Loaded: loaded (/home/user/.config/systemd/user/cypherclaw-narrative-api.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-05-01 18:25:45 PDT; 10s ago
       Docs: file:///home/user/cypherclaw/sdp/prd-cypherclaw-narrative-http-service.md
   Main PID: 3981921 (python3)
      Tasks: 6 (limit: 76750)
     Memory: 38.5M (peak: 39.4M)
        CPU: 346ms
     CGroup: /user.slice/user-1000.slice/user@1000.service/app.slice/cypherclaw-narrative-api.service
             └─3981921 /home/user/cypherclaw/.venv/bin/python3 -m cypherclaw.narrative_api

May 01 18:25:45 cypherclaw systemd[3136325]: Started cypherclaw-narrative-api.service - CypherClaw Narrative API — HTTP wrapper around the in-process narrative engine.
May 01 18:25:46 cypherclaw cypherclaw-narrative-api[3981921]: INFO:     Started server process [3981921]
May 01 18:25:46 cypherclaw cypherclaw-narrative-api[3981921]: INFO:     Waiting for application startup.
May 01 18:25:46 cypherclaw cypherclaw-narrative-api[3981921]: INFO:     Application startup complete.
May 01 18:25:46 cypherclaw cypherclaw-narrative-api[3981921]: INFO:     Uvicorn running on http://100.74.35.114:8765 (Press CTRL+C to quit)

=== systemctl --user is-active cypherclaw-narrative-api.service ===
active

=== systemctl --user is-enabled cypherclaw-narrative-api.service ===
enabled

=== Loginctl linger state for current user ===
Linger=yes

=== Listening ports (tailscale + loopback) ===
LISTEN 0      2048                 100.74.35.114:8765       0.0.0.0:*
LISTEN 0      4096                 100.74.35.114:46709      0.0.0.0:*
LISTEN 0      4096   [fd7a:115c:a1e0::9e36:2372]:42817         [::]:*

=== narrative_api module presence on host ===
app.py
events.py
__init__.py
__main__.py
memory.py
__pycache__
schemas.py

=== curl /health (Tailscale interface) ===
{"status":"degraded","narrative_engine_importable":true,"world_db_reachable":false,"ollama_reachable":true,"version":"0.1.0","uptime_seconds":10.292695362004451}

=== journalctl --user -u cypherclaw-narrative-api.service -n 30 --no-pager ===
May 01 18:25:10 cypherclaw systemd[3136325]: /home/user/.config/systemd/user/cypherclaw-narrative-api.service:28: Unknown key name 'StartLimitIntervalSec' in section 'Service', ignoring.
May 01 18:25:10 cypherclaw systemd[3136325]: Started cypherclaw-narrative-api.service - CypherClaw Narrative API — HTTP wrapper around the in-process narrative engine.
May 01 18:25:11 cypherclaw cypherclaw-narrative-api[3979692]: INFO:     Started server process [3979692]
May 01 18:25:11 cypherclaw cypherclaw-narrative-api[3979692]: INFO:     Waiting for application startup.
May 01 18:25:11 cypherclaw cypherclaw-narrative-api[3979692]: INFO:     Application startup complete.
May 01 18:25:11 cypherclaw cypherclaw-narrative-api[3979692]: INFO:     Uvicorn running on http://100.74.35.114:8765 (Press CTRL+C to quit)
May 01 18:25:21 cypherclaw cypherclaw-narrative-api[3979692]: INFO:     100.74.35.114:58258 - "GET /health HTTP/1.1" 200 OK
May 01 18:25:45 cypherclaw systemd[3136325]: Stopping cypherclaw-narrative-api.service - CypherClaw Narrative API — HTTP wrapper around the in-process narrative engine...
May 01 18:25:45 cypherclaw cypherclaw-narrative-api[3979692]: INFO:     Shutting down
May 01 18:25:45 cypherclaw cypherclaw-narrative-api[3979692]: INFO:     Waiting for application shutdown.
May 01 18:25:45 cypherclaw cypherclaw-narrative-api[3979692]: INFO:     Application shutdown complete.
May 01 18:25:45 cypherclaw cypherclaw-narrative-api[3979692]: INFO:     Finished server process [3979692]
May 01 18:25:45 cypherclaw systemd[3136325]: Stopped cypherclaw-narrative-api.service - CypherClaw Narrative API — HTTP wrapper around the in-process narrative engine.
May 01 18:25:45 cypherclaw systemd[3136325]: Started cypherclaw-narrative-api.service - CypherClaw Narrative API — HTTP wrapper around the in-process narrative engine.
May 01 18:25:46 cypherclaw cypherclaw-narrative-api[3981921]: INFO:     Started server process [3981921]
May 01 18:25:46 cypherclaw cypherclaw-narrative-api[3981921]: INFO:     Waiting for application startup.
May 01 18:25:46 cypherclaw cypherclaw-narrative-api[3981921]: INFO:     Application startup complete.
May 01 18:25:46 cypherclaw cypherclaw-narrative-api[3981921]: INFO:     Uvicorn running on http://100.74.35.114:8765 (Press CTRL+C to quit)
May 01 18:25:56 cypherclaw cypherclaw-narrative-api[3981921]: INFO:     100.74.35.114:38978 - "GET /health HTTP/1.1" 200 OK
```

## Notes

- **Entry-point gap:** Prior runs failed because no `__main__.py` existed
  in the `narrative_api/` package, so the unit's
  `ExecStart=python3 -m cypherclaw.narrative_api` line had nothing to
  dispatch to. Per the previous verifier's note, this corresponds to
  T-008's still-pending `bootstrap_identity()` wiring. To unblock T-004,
  this run added a minimal `__main__.py` that reads
  `NARRATIVE_BIND_HOST` / `NARRATIVE_BIND_PORT` / `NARRATIVE_AUTH_TOKEN`
  from the environment, builds the FastAPI app via `create_app()`, and
  launches uvicorn. T-008's remaining work (Pydantic settings, structlog,
  `bootstrap_identity()`) is still open and tracked separately.
- `world_db_reachable` reports `false` from `/health`. The narrative
  world-state SQLite still needs the additive `domain` column migration
  (T-007 / CN-001). That is unrelated to T-004's scope, but explains the
  `degraded` status.
- The journal still contains the historical
  `Unknown key name 'StartLimitIntervalSec' in section 'Service'` warning
  from the *first* start at 18:25:10. After the unit-file fix and restart
  at 18:25:45, the warning no longer appears — confirming the `[Unit]`
  section placement is correct for this systemd version.
- SSH access from the Darwin dev box to `cypherclaw` is non-interactive;
  the operator can re-run the inline status block above to refresh this
  evidence file.
