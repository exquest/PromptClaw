"""Server self-care — health monitoring and auto-maintenance for cypherclaw."""

import os
import platform
import subprocess


def check_health() -> dict:
    """Comprehensive server health check."""
    health = {"healthy": True, "checks": {}, "warnings": [], "actions_taken": []}

    # 1. Disk usage
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if "/" in line and "%" in line:
                usage = int(line.split()[-2].rstrip("%"))
                health["checks"]["disk_usage"] = f"{usage}%"
                if usage > 90:
                    health["healthy"] = False
                    health["warnings"].append(f"CRITICAL: Disk {usage}% full")
                elif usage > 75:
                    health["warnings"].append(f"Disk usage at {usage}%")
    except Exception as e:
        health["warnings"].append(f"Disk check failed: {e}")

    # 2. Memory
    try:
        if platform.system() == "Linux":
            result = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
            for line in result.stdout.splitlines():
                if line.startswith("Mem:"):
                    parts = line.split()
                    total, available = int(parts[1]), int(parts[-1])
                    pct_used = round((1 - available / total) * 100)
                    health["checks"]["memory"] = f"{pct_used}% used ({available}MB free)"
                    if pct_used > 90:
                        health["healthy"] = False
                        health["warnings"].append(f"CRITICAL: Memory {pct_used}% used")
                    elif pct_used > 75:
                        health["warnings"].append(f"Memory at {pct_used}%")
        else:
            # macOS — use vm_stat
            result = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
            page_size = 16384  # default on Apple Silicon
            free_pages = 0
            for line in result.stdout.splitlines():
                if "page size of" in line:
                    page_size = int(line.split()[-2])
                if "Pages free" in line:
                    free_pages = int(line.split()[-1].rstrip("."))
            # Also get total via sysctl
            sysctl = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
            total_bytes = int(sysctl.stdout.strip())
            total_mb = total_bytes // (1024 * 1024)
            free_mb = (free_pages * page_size) // (1024 * 1024)
            pct_used = round((1 - free_mb / total_mb) * 100) if total_mb else 0
            health["checks"]["memory"] = f"{pct_used}% used ({free_mb}MB free of {total_mb}MB)"
            if pct_used > 90:
                health["healthy"] = False
                health["warnings"].append(f"CRITICAL: Memory {pct_used}% used")
            elif pct_used > 75:
                health["warnings"].append(f"Memory at {pct_used}%")
    except Exception as e:
        health["warnings"].append(f"Memory check failed: {e}")

    # 3. Load average
    try:
        load = os.getloadavg()
        cores = os.cpu_count() or 12
        health["checks"]["load"] = f"{load[0]:.1f} / {load[1]:.1f} / {load[2]:.1f} ({cores} cores)"
        if load[0] > cores * 2:
            health["warnings"].append(f"High load: {load[0]:.1f} (cores: {cores})")
    except Exception as e:
        health["warnings"].append(f"Load check failed: {e}")

    # 4. Zombie/D-state processes
    try:
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        zombies = sum(1 for line in result.stdout.splitlines() if " Z" in line or " Ds " in line)
        health["checks"]["zombies"] = zombies
        if zombies > 3:
            health["warnings"].append(f"{zombies} zombie/D-state processes")
    except Exception:
        pass

    # 5. Daemon status
    if platform.system() == "Linux":
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "cypherclaw"], capture_output=True, text=True, timeout=5
            )
            status = result.stdout.strip()
            health["checks"]["daemon"] = status
            if status != "active":
                health["healthy"] = False
                health["warnings"].append(f"Daemon is {status}")
        except Exception:
            pass
    else:
        # macOS — check via launchctl
        try:
            result = subprocess.run(
                ["launchctl", "list", "com.cypherclaw.daemon"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                health["checks"]["daemon"] = "running"
            else:
                health["checks"]["daemon"] = "not loaded"
                health["warnings"].append("Daemon not loaded in launchctl")
        except Exception:
            health["checks"]["daemon"] = "unknown"

    # 6. Key services
    if platform.system() == "Linux":
        for svc in ["docker", "postgresql", "redis-server", "nginx", "ssh"]:
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", svc], capture_output=True, text=True, timeout=5
                )
                health["checks"][svc] = result.stdout.strip()
                if result.stdout.strip() != "active":
                    health["warnings"].append(f"Service {svc} is {result.stdout.strip()}")
            except Exception:
                pass
    else:
        # macOS — check common services via brew services or process list
        for svc in ["docker", "postgresql", "redis", "nginx"]:
            try:
                result = subprocess.run(
                    ["pgrep", "-x", svc], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    health["checks"][svc] = "running"
                else:
                    health["checks"][svc] = "not running"
            except Exception:
                pass

    # 7. Temperature
    if platform.system() == "Linux":
        try:
            result = subprocess.run(
                ["bash", "-c", "cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | head -1"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                temp_c = int(result.stdout.strip()) / 1000
                health["checks"]["temperature"] = f"{temp_c:.0f}C"
                if temp_c > 85:
                    health["warnings"].append(f"HIGH TEMP: {temp_c:.0f}C")
                elif temp_c > 75:
                    health["warnings"].append(f"Warm: {temp_c:.0f}C")
        except Exception:
            pass
    # macOS has no standard thermal interface; skip temperature check

    # 8. Uptime
    try:
        if platform.system() == "Linux":
            result = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=5)
            health["checks"]["uptime"] = result.stdout.strip()
        else:
            # macOS uptime doesn't support -p; parse standard uptime output
            result = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
            health["checks"]["uptime"] = result.stdout.strip()
    except Exception:
        pass

    # 9. Orphaned agent processes
    for pattern in ["claude", "codex", "gemini"]:
        try:
            result = subprocess.run(
                ["pgrep", "-c", "-f", pattern], capture_output=True, text=True, timeout=5
            )
            count = int(result.stdout.strip()) if result.returncode == 0 else 0
            if count > 3:
                health["warnings"].append(f"{count} {pattern} processes (may be orphaned)")
        except Exception:
            pass

    return health


def auto_maintain() -> list[str]:
    """Run automatic maintenance tasks. Returns list of actions taken."""
    actions = []

    # 1. Kill stale agent processes (running > 10 min)
    try:
        result = subprocess.run(
            ["bash", "-c",
             "ps -eo pid,etimes,comm | grep -E 'claude|codex|gemini' | awk '$2 > 600 {print $1}'"],
            capture_output=True, text=True, timeout=5,
        )
        for pid_str in result.stdout.strip().splitlines():
            if pid_str.strip().isdigit():
                pid = int(pid_str.strip())
                try:
                    os.kill(pid, 15)  # SIGTERM
                    actions.append(f"Killed stale agent process {pid}")
                except ProcessLookupError:
                    pass
    except Exception:
        pass

    # 2. Clean temp files older than 1 day
    try:
        subprocess.run(
            ["find", "/tmp", "-user", "user", "-mtime", "+1", "-delete"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass

    # 3. Truncate oversized log
    log_path = os.path.expanduser("~/cypherclaw/tools/cypherclaw_daemon.log")
    try:
        size = os.path.getsize(log_path)
        if size > 50 * 1024 * 1024:  # 50MB
            with open(log_path, "rb") as f:
                f.seek(-10 * 1024 * 1024, 2)
                tail = f.read()
            with open(log_path, "wb") as f:
                f.write(tail)
            actions.append(f"Truncated log from {size // 1024 // 1024}MB to 10MB")
    except Exception:
        pass

    return actions


def telegram_report(health: dict, actions: list[str]) -> str:
    """Format health check for Telegram."""
    if health["healthy"] and not health["warnings"]:
        emoji = "\U0001f7e2"
        status = "All systems nominal"
    elif health["warnings"] and health["healthy"]:
        emoji = "\U0001f7e1"
        status = "Minor warnings"
    else:
        emoji = "\U0001f534"
        status = "ATTENTION NEEDED"

    lines = [f"{emoji} Server Health: {status}\n"]

    checks = health["checks"]
    lines.append(f"\U0001f4be Disk: {checks.get('disk_usage', '?')}")
    lines.append(f"\U0001f9e0 RAM: {checks.get('memory', '?')}")
    lines.append(f"\u26a1 Load: {checks.get('load', '?')}")
    lines.append(f"\U0001f321 Temp: {checks.get('temperature', '?')}")
    lines.append(f"\u23f1 {checks.get('uptime', '?')}")
    lines.append(f"\U0001f980 Daemon: {checks.get('daemon', '?')}")

    if health["warnings"]:
        lines.append("\n\u26a0\ufe0f Warnings:")
        for w in health["warnings"]:
            lines.append(f"  \u2022 {w}")

    if actions:
        lines.append("\n\U0001f527 Auto-maintenance:")
        for a in actions:
            lines.append(f"  \u2022 {a}")

    return "\n".join(lines)


if __name__ == "__main__":
    h = check_health()
    a = auto_maintain()
    print(telegram_report(h, a))
