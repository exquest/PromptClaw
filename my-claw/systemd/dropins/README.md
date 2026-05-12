# Systemd resource-limits drop-ins

Per-service `MemoryHigh` / `MemoryMax` / `TasksMax` limits for the user-space
CypherClaw services. Drop-ins live at:

```
/etc/systemd/system/<service>.service.d/resource-limits.conf
```

## Why these exist

On 2026-05-02 CypherClaw deep-froze (TCP accept worked, app layer dead) because
44 duplicate `cypherclaw.daemon` processes had spawned via an agetty/login
auto-respawn loop in `cypherclaw_boot.sh`. Each daemon held ~3GB of RSS in its
cgroup; cumulative pressure swapped the box and crippled sshd.

The boot script was patched to be idempotent (`scripts/cypherclaw_boot.sh`).
These drop-ins are belt-and-suspenders defense: even if a future leak or
duplicate-spawn bug recurs, `MemoryMax` lets the kernel OOM-kill the offending
service rather than swap-thrash the whole box.

## Limits applied

| Service | MemoryHigh | MemoryMax | TasksMax |
|---|---|---|---|
| cypherclaw-main-daemon | 4G | 6G | 500 |
| cypherclaw-image-api | 1G | 1500M | 200 |
| cypherclaw-generation-worker | 1G | 1500M | 200 |
| cypherclaw-publisher | 512M | 1G | 200 |
| cypherclaw-scheduler | 512M | 1G | 200 |
| cypherclaw-sample-capture | 512M | 1G | 200 |
| cypherclaw-web-gallery | 512M | 1G | 200 |
| cypherclaw-observer-ollama | 512M | 1G | 200 |

`MemoryHigh` triggers reclaim pressure (soft); `MemoryMax` is the hard ceiling
(OOM-kill on overrun). `TasksMax` caps thread+process count to prevent fork
bombs.

## Reapplying after a re-image

```bash
for svc in main-daemon image-api generation-worker publisher scheduler sample-capture web-gallery observer-ollama; do
    sudo mkdir -p "/etc/systemd/system/cypherclaw-$svc.service.d"
    # copy the matching .conf from this dir, or use the generic template
done
sudo systemctl daemon-reload
```

Limits apply to running cgroups immediately after `daemon-reload`; no service
restart required (verified on 2026-05-02).
