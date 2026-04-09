#!/usr/bin/env python3
# ruff: noqa: E402
"""CypherClaw Daemon v2 — always-on Telegram orchestrator.

Fixes over v1:
- Persistent conversation memory across messages
- Multi-step workflow execution (agent chaining)
- Parallel agent dispatch
- Background task queue with async reporting
- Scheduled recurring tasks (cron-like)
- Shared artifact workspace between agents
- Proactive messaging (health checks, monitors)
- Better routing via structured orchestrator plans

Usage:
    python cypherclaw_daemon.py              # Run in foreground
    python cypherclaw_daemon.py --install    # Install as launchd service
    python cypherclaw_daemon.py --uninstall  # Remove launchd service
    python cypherclaw_daemon.py --status     # Check if running
"""

import argparse
import concurrent.futures
import hashlib
import json
import logging
import os
import platform
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    from runtime_paths import resolve_runtime_paths
except ImportError:  # pragma: no cover - package layout
    from cypherclaw.runtime_paths import resolve_runtime_paths

# GlyphWeave art system
PATHS = resolve_runtime_paths(__file__)
TOOLS_DIR_EARLY = PATHS.tools_dir
sys.path.insert(0, str(TOOLS_DIR_EARLY))
from glyphweave.scenes import CypherClawArt
from glyphweave.player import AEAFPlayer, build_spinner_frames
from sdp_runtime import run_sdp_command
from tamagotchi import PetManager
_art = CypherClawArt()
pet_manager = PetManager()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    "",
)
CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

POLL_INTERVAL = 5
MAX_MESSAGE_LEN = 4000
CONVERSATION_WINDOW = 10  # messages to keep in rolling context (smaller = faster routing)
MAX_AGENT_TIMEOUT = 300   # 5 min max for agent tasks (was 10 — too long)

# Health-check endpoints — override via env or edit this dict
HEALTH_CHECK_SITES: dict[str, str] = {}
_hc_env = os.environ.get("HEALTH_CHECK_SITES", "")
if _hc_env:
    # Format: "label1=url1,label2=url2"
    for pair in _hc_env.split(","):
        if "=" in pair:
            lbl, url = pair.split("=", 1)
            HEALTH_CHECK_SITES[lbl.strip()] = url.strip()
else:
    HEALTH_CHECK_SITES = {
        "tickets.cascadiantech.com": "https://tickets.cascadiantech.com/api/health/",
        "cascadiantech.com": "https://cascadiantech.com/healthz/",
        "promptlab": "https://promptlab.cascadiantech.com/",
    }


# === STABILITY: Agent concurrency limiter ===
# Max 2 concurrent agent processes to prevent disk I/O saturation
# (jbd2 ext4 journal freezes when too many processes write simultaneously)
_SEMAPHORE_MAX = 2
_SEMAPHORE_IO_REVERT_THRESHOLD = 2
_agent_semaphore = threading.Semaphore(_SEMAPHORE_MAX)
_agent_semaphore_limit = _SEMAPHORE_MAX
_io_guard_trigger_count = 0
_agent_count = 0
_agent_count_lock = threading.Lock()


def _notify_watchdog():
    """Notify systemd watchdog that we are alive."""
    try:
        import socket
        addr = os.environ.get("NOTIFY_SOCKET")
        if not addr:
            return
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        if addr[0] == "@":
            addr = "\0" + addr[1:]
        sock.sendto(b"WATCHDOG=1", addr)
        sock.close()
    except Exception:
        pass


def _child_process_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build a subprocess env without systemd watchdog variables.

    Child CLIs should not inherit sd_notify/watchdog variables from the daemon,
    otherwise systemd logs noisy "Got notification message from PID ..." warnings
    when a child process talks to the inherited NOTIFY_SOCKET.
    """
    env = os.environ.copy()
    for key in ("NOTIFY_SOCKET", "WATCHDOG_PID", "WATCHDOG_USEC"):
        env.pop(key, None)
    if extra:
        env.update(extra)
    return env


def _kill_orphan_agents():
    """Kill any orphaned agent processes on startup."""
    for pattern in ["claude --", "codex exec", "gemini -p", "gemini --yolo"]:
        try:
            subprocess.run(
                ["pkill", "-f", pattern],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass

TOOLS_DIR = PATHS.tools_dir
STATE_FILE = TOOLS_DIR / ".daemon_state.json"
LOG_FILE = TOOLS_DIR / "cypherclaw_daemon.log"
WORKSPACE_DIR = PATHS.workspace_dir
TASKS_DIR = PATHS.tasks_dir

PLIST_LABEL = "com.cypherclaw.daemon"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"

PROJECT_ROOT = PATHS.project_root

# Ensure workspace exists
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
TASKS_DIR.mkdir(parents=True, exist_ok=True)

# Observatory & Healer
from observatory import Observatory
from healer import Healer, Failure

OBSERVATORY_DB = PROJECT_ROOT / ".promptclaw" / "observatory.db"
OBSERVATORY_DB.parent.mkdir(parents=True, exist_ok=True)
observatory = Observatory(str(OBSERVATORY_DB))

from reviewer import Reviewer
reviewer = Reviewer(observatory)

from researcher import Researcher
from lifeimprover_bridge import LifeImproverBridge
import ollama_health as ollama_probe
li_bridge = LifeImproverBridge()

from quota_monitor import QuotaMonitor, is_quota_error
quota_monitor = QuotaMonitor(
    observatory=observatory,
    poll_interval=60,
)

try:
    from io_watchdog import IOWatchdog  # type: ignore[import-not-found]
except ImportError:
    IOWatchdog = None  # type: ignore[assignment]

from agent_selector import AgentSelector, PROVIDERS, get_ollama_route
agent_selector = AgentSelector(
    observatory=observatory,
    quota_monitor=quota_monitor,
    state_file=TOOLS_DIR / ".agent_selector_state.json",
)

OLLAMA_HEALTH_PORTS: tuple[tuple[str, int], ...] = (
    ("socket0", 11434),
    ("socket1", 11435),
)


def _on_io_guard_triggered() -> None:
    """Tighten concurrency when the I/O guard kills agent processes repeatedly."""
    global _agent_semaphore, _agent_semaphore_limit, _io_guard_trigger_count
    _io_guard_trigger_count += 1
    observatory.record(
        "io_guard_triggered",
        {
            "trigger_count": _io_guard_trigger_count,
            "semaphore_limit": _agent_semaphore_limit,
        },
    )
    if _agent_semaphore_limit > 1 and _io_guard_trigger_count > _SEMAPHORE_IO_REVERT_THRESHOLD:
        previous_limit = _agent_semaphore_limit
        _agent_semaphore = threading.Semaphore(1)
        _agent_semaphore_limit = 1
        observatory.record(
            "semaphore_reverted",
            {
                "from": previous_limit,
                "to": _agent_semaphore_limit,
                "trigger_count": _io_guard_trigger_count,
            },
        )


def _make_io_watchdog():
    if IOWatchdog is None:
        return None
    return IOWatchdog(
        alert_fn=tg_send,
        kill_fn=_kill_orphan_agents,
        on_io_kill=_on_io_guard_triggered,
    )


io_watchdog = None

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

# Logging — configured once, no duplicates
# Logging — file only (launchd captures stderr separately)
logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("cypherclaw")
log.setLevel(logging.INFO)
log.handlers.clear()
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_fh = logging.FileHandler(LOG_FILE)
_fh.setFormatter(_fmt)
log.addHandler(_fh)
log.propagate = False

# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

def tg_api(method: str, data: dict | None = None) -> dict:
    url = f"{API_BASE}/{method}"
    payload = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=payload)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:200]
        except Exception:
            pass
        log.warning("Telegram HTTP %s: %s — %s", e.code, method, body)
        return {"ok": False, "error": str(e)}
    except urllib.error.URLError as e:
        log.warning("Telegram API error: %s", e)
        return {"ok": False, "error": str(e)}


def _has_code_block(text: str) -> bool:
    """Check if text contains triple backtick code blocks."""
    return "```" in text


def tg_send(text: str) -> dict:
    """Send a message. Auto-detects Markdown for code blocks."""
    result = {}
    for chunk in _split_message(text):
        data: dict = {"chat_id": CHAT_ID, "text": chunk}
        # Use Markdown parse mode if the message contains code blocks
        if _has_code_block(chunk):
            data["parse_mode"] = "Markdown"
        result = tg_api("sendMessage", data)
        # If Markdown fails (bad formatting), retry without parse_mode
        if not result.get("ok") and "parse_mode" in data:
            del data["parse_mode"]
            result = tg_api("sendMessage", data)
        time.sleep(0.2)
    return result


if io_watchdog is None:
    io_watchdog = _make_io_watchdog()


quota_monitor.alert_callback = lambda message: tg_send(message)


def tg_edit(message_id: int, text: str) -> None:
    """Edit an existing message. Auto-detects Markdown for code blocks."""
    try:
        data: dict = {
            "chat_id": CHAT_ID,
            "message_id": message_id,
            "text": text[:MAX_MESSAGE_LEN],
        }
        if _has_code_block(text):
            data["parse_mode"] = "Markdown"
        result = tg_api("editMessageText", data)
        # If Markdown fails, retry without parse_mode
        if not result.get("ok") and "parse_mode" in data:
            del data["parse_mode"]
            result = tg_api("editMessageText", data)
            if not result.get("ok"):
                log.warning("tg_edit failed (msg_id=%s): %s", message_id,
                           str(result)[:100])
    except Exception as e:
        log.warning("tg_edit exception (msg_id=%s): %s", message_id, e)


def tg_send_file(filepath: str, caption: str = "") -> None:
    """Send a file via Telegram. Uses sendPhoto for images, sendDocument for others.
    Also records the file send in conversation memory so the daemon remembers."""
    # Record in conversation memory
    filename = os.path.basename(filepath)
    state.add_message("assistant", f"[file sent] {filename}: {caption}")
    import mimetypes
    mime = mimetypes.guess_type(filepath)[0] or ""
    method = "sendPhoto" if mime.startswith("image/") else "sendDocument"
    field = "photo" if method == "sendPhoto" else "document"

    try:
        import urllib.request
        boundary = "----CypherClawUpload"
        filename = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            file_data = f.read()

        parts = []
        # chat_id field
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{CHAT_ID}".encode())
        # caption field
        if caption:
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption[:1024]}".encode())
        # file field
        file_header = f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\nContent-Type: {mime or 'application/octet-stream'}\r\n\r\n".encode()
        parts.append(file_header + file_data)
        # closing
        body = b"\r\n".join(parts) + f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(f"{API_BASE}/{method}", data=body)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            if not result.get("ok"):
                log.warning("File send failed: %s", result)
    except Exception as e:
        log.warning("tg_send_file error: %s — falling back to telegram.py", e)
        # Fallback to the old method
        cmd = [sys.executable, str(TOOLS_DIR / "telegram.py"), "file", filepath]
        if caption:
            cmd.append(caption)
        subprocess.run(cmd, capture_output=True, timeout=30)


def _split_message(text: str) -> list[str]:
    if len(text) <= MAX_MESSAGE_LEN:
        return [text]
    chunks = []
    while text:
        if len(text) <= MAX_MESSAGE_LEN:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, MAX_MESSAGE_LEN)
        if split_at == -1:
            split_at = MAX_MESSAGE_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# ---------------------------------------------------------------------------
# Persistent state — conversation memory + task queue + schedules
# ---------------------------------------------------------------------------

class DaemonState:
    def __init__(self):
        self.last_update_id = 0
        self.conversation: deque[dict] = deque(maxlen=CONVERSATION_WINDOW)
        self.tasks: dict[str, dict] = {}  # task_id -> {status, agent, prompt, result, ...}
        self.schedules: list[dict] = []   # [{name, interval_s, command, last_run, enabled}]
        self.pending_confirm: dict | None = None
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        try:
            data = json.loads(STATE_FILE.read_text())
            self.last_update_id = data.get("last_update_id", 0)
            for msg in data.get("conversation", []):
                self.conversation.append(msg)
            self.tasks = data.get("tasks", {})
            self.schedules = data.get("schedules", [])
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def save(self):
        with self._lock:
            STATE_FILE.write_text(json.dumps({
                "last_update_id": self.last_update_id,
                "conversation": list(self.conversation),
                "tasks": self.tasks,
                "schedules": self.schedules,
            }, default=str, indent=2))

    def add_message(self, role: str, text: str):
        self.conversation.append({
            "role": role,
            "text": text,
            "time": datetime.now(timezone.utc).isoformat(),
        })
        self.save()

    def conversation_context(self) -> str:
        if not self.conversation:
            return "(no prior conversation)"
        lines = []
        for msg in self.conversation:
            prefix = "Anthony" if msg["role"] == "user" else "CypherClaw"
            lines.append(f"[{msg.get('time', '')}] {prefix}: {msg['text']}")
        return "\n".join(lines)

    def create_task(self, task_id: str, agent: str, prompt: str) -> None:
        self.tasks[task_id] = {
            "status": "running",
            "agent": agent,
            "prompt": prompt[:200],
            "created": datetime.now(timezone.utc).isoformat(),
            "result": None,
        }
        self.save()

    def complete_task(self, task_id: str, result: str) -> None:
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = "done"
            self.tasks[task_id]["result"] = result[:500]
            self.tasks[task_id]["finished"] = datetime.now(timezone.utc).isoformat()
            self.save()

    def fail_task(self, task_id: str, error: str) -> None:
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = "failed"
            self.tasks[task_id]["result"] = error[:500]
            self.save()


state = DaemonState()


def _healer_notify(msg):
    tg_send(f"\U0001f527 Auto-healed: {msg}")


def _healer_ask(msg):
    tg_send(f"\u26a0\ufe0f Healing needs approval:\n{msg}\n\nReply 'yes' to proceed")
    # For now, return None (will be enhanced later with actual Telegram reply waiting)
    return None


healer = Healer(notify_fn=_healer_notify, ask_fn=_healer_ask)

# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------

def run_shell(command: str, timeout: int = 120) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=str(PROJECT_ROOT), env=_child_process_env(),
        )
        observatory.record('shell_executed', data={'command': command[:100], 'exit_code': result.returncode})
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr] {result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"[timed out after {timeout}s]"
    except Exception as e:
        return f"[error: {e}]"


class AgentSpinner:
    """Shows animated status updates while an agent works, using AEAFPlayer."""

    def __init__(self, agent: str, task_desc: str = "", msg_id: int | None = None):
        self.agent = agent
        self.task_desc = task_desc[:60] or agent
        self.msg_id = msg_id
        self._player: AEAFPlayer | None = None

    def _make_phases(self) -> list[str]:
        """Generate work-relevant status messages based on agent and task."""
        a = self.agent.lower()
        t = self.task_desc.lower()
        phases = []
        if a == "claude" or a == "brain":
            phases = ["reading context", "analyzing request", "reasoning", "drafting response", "reviewing output"]
        elif a == "codex":
            phases = ["scanning codebase", "planning changes", "writing code", "running checks", "finalizing"]
        elif a == "gemini":
            phases = ["gathering sources", "reading docs", "synthesizing", "composing output", "polishing"]
        else:
            phases = ["starting up", "processing", "working", "wrapping up"]

        # Add task-specific detail
        if "health" in t or "check" in t:
            phases = ["connecting to server", "pinging endpoints", "collecting status", "formatting results"]
        elif "deploy" in t:
            phases = ["syncing files", "installing deps", "running migrations", "restarting services", "health check"]
        elif "test" in t:
            phases = ["discovering tests", "running test suite", "collecting results", "checking coverage"]
        elif "review" in t or "fix" in t:
            phases = ["reading source", "identifying issues", "planning fix", "applying changes", "verifying"]
        elif "search" in t or "research" in t or "find" in t:
            phases = ["searching codebase", "reading matches", "cross-referencing", "compiling findings"]
        elif "image" in t or "generat" in t:
            phases = ["preparing prompt", "calling model", "generating output", "processing result"]
        return phases

    def start(self):
        phases = self._make_phases()
        pet = pet_manager.get(self.agent)
        pet_frames = pet.get_frames()
        frames, frame_ms = build_spinner_frames(self.agent, self.task_desc, phases, pet_frames=pet_frames)

        if not self.msg_id:
            # Send the first frame as the initial message (with Markdown for code blocks)
            first_frame = frames[0] if frames else f"🦀 {self.agent} working..."
            data: dict = {"chat_id": CHAT_ID, "text": first_frame}
            if "```" in first_frame:
                data["parse_mode"] = "Markdown"
            r = tg_api("sendMessage", data)
            # If Markdown failed, retry without
            if not r.get("ok") and "parse_mode" in data:
                del data["parse_mode"]
                r = tg_api("sendMessage", data)
            self.msg_id = r.get("result", {}).get("message_id")

        if frames and self.msg_id:
            self._player = AEAFPlayer(
                frames=frames,
                frame_ms=frame_ms,
                loop=True,
                message_id=self.msg_id,
                edit_fn=tg_edit,
            )
            self._player.start()

    def stop(self):
        if self._player:
            self._player.stop()
        if self.msg_id:
            tg_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": self.msg_id})


@dataclass
class AgentCommandResult:
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    timed_out: bool = False


def _local_only_enabled() -> bool:
    value = os.environ.get("LOCAL_ONLY", "").strip().casefold()
    return value in {"1", "true", "yes", "on"}


def _available_agents(
    agents: list[str] | tuple[str, ...] | None = None,
    *,
    disabled_agents: set[str] | None = None,
) -> list[str]:
    if _local_only_enabled():
        candidates = ["ollama"]
    else:
        candidates = list(agents or ["claude", "codex", "gemini"])
    disabled = set(disabled_agents or ())
    filtered = [agent for agent in candidates if agent not in disabled]
    if not filtered:
        filtered = ["ollama"] if _local_only_enabled() else candidates
    try:
        available = quota_monitor.get_available_agents(filtered)
        if available:
            return ["ollama"] if _local_only_enabled() else available
    except Exception:
        pass
    return ["ollama"] if _local_only_enabled() else filtered


def _best_available_agent(
    agents: list[str] | tuple[str, ...] | None = None,
    *,
    disabled_agents: set[str] | None = None,
) -> str:
    available = _available_agents(agents, disabled_agents=disabled_agents)
    return available[0] if available else ("ollama" if _local_only_enabled() else "gemini")


def _build_agent_command(agent: str, prompt: str) -> tuple[list[str], dict[str, str], bool]:
    env = _child_process_env()
    use_stdin = True
    if agent == "claude":
        env.pop("CLAUDECODE", None)
        cmd = ["claude", "--dangerously-skip-permissions", "--print", "-p", "-"]
    elif agent == "codex":
        cmd = ["codex", "exec", "--full-auto", "-"]
    elif agent == "gemini":
        cmd = ["gemini", "--yolo", "-p", prompt]
        use_stdin = False
    else:
        raise ValueError(f"Unknown agent: {agent}")
    return cmd, env, use_stdin


def _invoke_agent_process(agent: str, prompt: str, timeout: int) -> AgentCommandResult:
    cmd, env, use_stdin = _build_agent_command(agent, prompt)
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if use_stdin else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=env,
        start_new_session=True,
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def _write_stdin() -> None:
        if not use_stdin or process.stdin is None:
            return
        try:
            process.stdin.write(prompt)
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                process.stdin.close()
            except Exception:
                pass

    def _drain_stdout() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            stdout_lines.append(line)

    def _drain_stderr() -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            stderr_lines.append(line)

    stdin_t = threading.Thread(target=_write_stdin, daemon=True)
    stdout_t = threading.Thread(target=_drain_stdout, daemon=True)
    stderr_t = threading.Thread(target=_drain_stderr, daemon=True)
    stdin_t.start()
    stdout_t.start()
    stderr_t.start()

    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        stdout_t.join(timeout=3)
        stderr_t.join(timeout=3)
        return AgentCommandResult(
            stdout="".join(stdout_lines).strip(),
            stderr="".join(stderr_lines).strip(),
            returncode=-1,
            timed_out=True,
        )

    stdout_t.join(timeout=5)
    stderr_t.join(timeout=5)
    return AgentCommandResult(
        stdout="".join(stdout_lines).strip(),
        stderr="".join(stderr_lines).strip(),
        returncode=process.returncode,
    )


def _ollama_base_url(port: int) -> str:
    if port == 11434:
        env_url = os.environ.get("OLLAMA_URL_SOCKET0", "").strip()
    elif port == 11435:
        env_url = os.environ.get("OLLAMA_URL_SOCKET1", "").strip()
    else:
        env_url = ""

    if env_url:
        return env_url.rstrip("/")
    return f"http://localhost:{port}"


def _ollama_instance_health(socket_name: str, port: int) -> dict[str, object]:
    started = time.perf_counter()
    healthy = bool(ollama_probe.check_health(port))
    latency_ms = int(round((time.perf_counter() - started) * 1000)) if healthy else None
    models = ollama_probe.check_models(port) if healthy else []
    return {
        "socket": socket_name,
        "port": port,
        "healthy": healthy,
        "status": "healthy" if healthy else "unreachable",
        "models": models,
        "latency_ms": latency_ms,
    }


def ollama_health() -> dict[str, object]:
    """Return dual-socket Ollama health for later status/Telegram formatting."""
    instances = [
        _ollama_instance_health(socket_name, port)
        for socket_name, port in OLLAMA_HEALTH_PORTS
    ]
    return {
        "healthy": any(bool(instance["healthy"]) for instance in instances),
        "instances": instances,
    }


def _invoke_ollama(
    prompt: str,
    timeout: int = 120,
    *,
    task_category: str | None = None,
    task_label: str = "",
) -> str:
    category = (task_category or "").strip() or agent_selector.detect_category(task_label or prompt)
    route = get_ollama_route(category)
    model = str(route.get("model", "")).strip()
    port = int(route.get("port", 11434))
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 2048},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{_ollama_base_url(port)}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            detail = ""
        suffix = f" {detail}" if detail else ""
        return f"[ollama error: HTTP {exc.code}{suffix}]"
    except urllib.error.URLError as exc:
        return f"[ollama error: {exc.reason}]"
    except TimeoutError:
        return f"[ollama error: timed out after {timeout}s]"
    except Exception as exc:
        return f"[ollama error: {exc}]"

    response_text = body.get("response")
    if isinstance(response_text, str):
        return response_text.strip()
    return "[ollama error: invalid response payload]"


def run_agent(agent: str, prompt: str, timeout: int = MAX_AGENT_TIMEOUT,
              task_label: str = "", _retry_count: int = 0,
              _disabled_agents: set[str] | None = None) -> str:
    """Run a CLI agent with animated spinner. Uses sdp-cli patterns for reliability."""
    if not prompt or not prompt.strip():
        return "(no prompt provided)"

    # STABILITY: Limit concurrent agent processes to prevent disk I/O saturation
    global _agent_count
    acquired = _agent_semaphore.acquire(timeout=30)
    if not acquired:
        observatory.record(
            "semaphore_rejected",
            {"agent": agent, "task_label": task_label or prompt[:80], "limit": _agent_semaphore_limit},
        )
        log.warning("Agent semaphore full (%d agents running). Rejecting %s call.", _agent_semaphore_limit, agent)
        return f"[{agent} busy — 2 agents already running. Try again in a moment.]"
    with _agent_count_lock:
        _agent_count += 1
        log.info("Agent started: %s (concurrent: %d)", agent, _agent_count)
    observatory.record(
        "semaphore_acquired",
        {"agent": agent, "task_label": task_label or prompt[:80], "concurrent": _agent_count, "limit": _agent_semaphore_limit},
    )

    spinner = AgentSpinner(agent, task_label or prompt[:60])
    start_time = time.time()
    try:
        spinner.start()
        pet_manager.on_task_start(agent)
        if agent == "ollama":
            output = _invoke_ollama(prompt, timeout=timeout, task_label=task_label)
            output = output or "(no output)"
            duration_s = time.time() - start_time
            success = not output.startswith("[")
            _, evolved, pet = pet_manager.on_task_end(
                agent,
                success=success,
                duration_s=duration_s,
            )
            if evolved:
                tg_send(pet_manager.evolution_announcement(pet))
            pet_manager.schedule_idle(agent)
            observatory.record_task_result(
                agent=agent,
                task_id=task_label or prompt[:50],
                success=success,
                duration_ms=int(duration_s * 1000),
                tokens=0,
                gate_pass=True,
            )

            if output.startswith("[") and ("timed out" in output or "error" in output or "not found" in output):
                failure = Failure(
                    type="agent_error",
                    error_message=output,
                    context={"agent": agent, "prompt": prompt[:200], "retry_count": _retry_count},
                    timestamp=time.time(),
                )
                heal_result = healer.handle_failure(failure)
                if heal_result and heal_result.resolved:
                    observatory.record_healing(failure.type, heal_result.severity, heal_result.action_taken, True, {})
            elif not success:
                failure = Failure(
                    type="agent_error",
                    error_message=output,
                    context={"agent": agent, "prompt": prompt[:200], "retry_count": _retry_count},
                    timestamp=time.time(),
                )
                heal_result = healer.handle_failure(failure)
                if heal_result and heal_result.resolved:
                    observatory.record_healing(failure.type, heal_result.severity, heal_result.action_taken, True, {})
            return output

        result = _invoke_agent_process(agent, prompt, timeout)
        duration_s = time.time() - start_time
        if result.timed_out:
            pet_manager.on_task_end(agent, success=False, duration_s=duration_s)
            pet_manager.schedule_idle(agent)
            timeout_output = f"[{agent} timed out after {timeout}s]"
            observatory.record_task_result(
                agent=agent,
                task_id=task_label or prompt[:50],
                success=False,
                duration_ms=int(duration_s * 1000),
                tokens=0,
                gate_pass=True,
            )
            failure = Failure(
                type="agent_error",
                error_message=timeout_output,
                context={"agent": agent, "prompt": prompt[:200], "retry_count": _retry_count},
                timestamp=time.time(),
            )
            heal_result = healer.handle_failure(failure)
            if heal_result and heal_result.resolved:
                observatory.record_healing(failure.type, heal_result.severity, heal_result.action_taken, True, {})
            return timeout_output

        output = result.stdout.strip() or result.stderr.strip() or "(no output)"
        duration_s = time.time() - start_time
        success = result.returncode == 0
        _, evolved, pet = pet_manager.on_task_end(
            agent,
            success=success,
            duration_s=duration_s,
        )
        if evolved:
            tg_send(pet_manager.evolution_announcement(pet))
        pet_manager.schedule_idle(agent)
        observatory.record_task_result(
            agent=agent,
            task_id=task_label or prompt[:50],
            success=success,
            duration_ms=int(duration_s * 1000),
            tokens=0,
            gate_pass=True,
        )

        if not success and is_quota_error(result.stderr):
            provider = PROVIDERS.get(agent)
            if provider:
                quota_monitor.force_status(
                    provider,
                    "paused",
                    headroom=0.0,
                    confidence="runtime",
                    reason=result.stderr[:200] or "quota error",
                )
            fallback_agent = _best_available_agent(disabled_agents=set(_disabled_agents or set()) | {agent})
            observatory.record_healing(
                "quota_exhausted",
                2,
                f"retry {agent}->{fallback_agent}",
                True,
                {
                    "failed_agent": agent,
                    "fallback_agent": fallback_agent,
                    "stderr": result.stderr[:500],
                    "task_label": task_label or prompt[:80],
                },
            )
            if _retry_count == 0 and fallback_agent != agent:
                return run_agent(
                    fallback_agent,
                    prompt,
                    timeout=timeout,
                    task_label=task_label,
                    _retry_count=_retry_count + 1,
                    _disabled_agents=set(_disabled_agents or set()) | {agent},
                )

        if output.startswith("[") and ("timed out" in output or "error" in output or "not found" in output):
            failure = Failure(
                type="agent_error",
                error_message=output,
                context={"agent": agent, "prompt": prompt[:200], "retry_count": _retry_count},
                timestamp=time.time(),
            )
            heal_result = healer.handle_failure(failure)
            if heal_result and heal_result.resolved:
                observatory.record_healing(failure.type, heal_result.severity, heal_result.action_taken, True, {})
        elif not success:
            failure = Failure(
                type="agent_error",
                error_message=output,
                context={"agent": agent, "prompt": prompt[:200], "retry_count": _retry_count},
                timestamp=time.time(),
            )
            heal_result = healer.handle_failure(failure)
            if heal_result and heal_result.resolved:
                observatory.record_healing(failure.type, heal_result.severity, heal_result.action_taken, True, {})
        return output

    except FileNotFoundError:
        pet_manager.on_task_end(agent, success=False, duration_s=time.time() - start_time)
        pet_manager.schedule_idle(agent)
        notfound_output = f"[{agent} CLI not found]"
        observatory.record_task_result(
            agent=agent,
            task_id=task_label or prompt[:50],
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            tokens=0,
            gate_pass=True,
        )
        failure = Failure(
            type="agent_error",
            error_message=notfound_output,
            context={"agent": agent, "prompt": prompt[:200], "retry_count": 0},
            timestamp=time.time(),
        )
        heal_result = healer.handle_failure(failure)
        if heal_result and heal_result.resolved:
            observatory.record_healing(failure.type, heal_result.severity, heal_result.action_taken, True, {})
        return notfound_output
    except Exception as e:
        pet_manager.on_task_end(agent, success=False, duration_s=time.time() - start_time)
        pet_manager.schedule_idle(agent)
        error_output = f"[{agent} error: {e}]"
        observatory.record_task_result(
            agent=agent,
            task_id=task_label or prompt[:50],
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            tokens=0,
            gate_pass=True,
        )
        failure = Failure(
            type="agent_error",
            error_message=error_output,
            context={"agent": agent, "prompt": prompt[:200], "retry_count": 0},
            timestamp=time.time(),
        )
        heal_result = healer.handle_failure(failure)
        if heal_result and heal_result.resolved:
            observatory.record_healing(failure.type, heal_result.severity, heal_result.action_taken, True, {})
        return error_output
    finally:
        spinner.stop()
        # STABILITY: Release agent semaphore
        _agent_semaphore.release()
        with _agent_count_lock:
            _agent_count -= 1
            log.info("Agent finished: %s (concurrent: %d)", agent, _agent_count)
        observatory.record(
            "semaphore_released",
            {"agent": agent, "task_label": task_label or prompt[:80], "concurrent": _agent_count, "limit": _agent_semaphore_limit},
        )


def run_agents_parallel(dispatches: list[dict]) -> list[dict]:
    """Run multiple agents in parallel with a shared spinner."""
    # Create one spinner for the parallel group
    agent_names = [d["agent"] for d in dispatches]
    pet_manager.on_communicate(agent_names)
    collab_scene = pet_manager.interaction_scene(agent_names)
    tg_send(collab_scene)
    agents_str = " + ".join(agent_names)
    r = tg_api("sendMessage", {"chat_id": CHAT_ID,
        "text": f"🔀 parallel: {agents_str}\n{'○ ' * len(dispatches)}"})
    group_msg_id = r.get("result", {}).get("message_id")

    results = []
    done_count = 0

    def _run_one(d):
        return {"label": d.get("label", d["agent"]), "agent": d["agent"],
                "output": run_agent(d["agent"], d["prompt"])}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_run_one, d): d for d in dispatches}
        for f in concurrent.futures.as_completed(futures):
            result = f.result()
            results.append(result)
            done_count += 1
            if group_msg_id:
                dots = "● " * done_count + "○ " * (len(dispatches) - done_count)
                tg_edit(group_msg_id,
                    f"🔀 parallel: {agents_str}\n{dots}\n✓ {result['agent']} done!")

    if group_msg_id:
        tg_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": group_msg_id})
    return results


# ---------------------------------------------------------------------------
# Artifact workspace — shared context between agents
# ---------------------------------------------------------------------------

def save_artifact(name: str, content: str) -> Path:
    """Save an artifact to the shared workspace."""
    path = WORKSPACE_DIR / name
    path.write_text(content)
    return path


def read_artifact(name: str) -> str | None:
    """Read an artifact from workspace."""
    path = WORKSPACE_DIR / name
    if path.exists():
        return path.read_text()
    return None


def list_artifacts() -> list[str]:
    return [f.name for f in WORKSPACE_DIR.iterdir() if f.is_file()]


# ---------------------------------------------------------------------------
# Deep Research Engine
# ---------------------------------------------------------------------------

# Lazy-init: researcher needs run_agent which is defined above
_researcher: Researcher | None = None

def get_researcher() -> Researcher:
    global _researcher
    if _researcher is None:
        _researcher = Researcher(
            send_fn=tg_send,
            send_file_fn=tg_send_file,
            observatory=observatory,
        )
    return _researcher


# ---------------------------------------------------------------------------
# Background task queue
# ---------------------------------------------------------------------------

task_pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)


def submit_background_task(task_id: str, agent: str, prompt: str) -> None:
    """Submit work to run in the background. Reports back via Telegram when done."""
    state.create_task(task_id, agent, prompt)

    def _run():
        try:
            output = run_agent(agent, prompt)
            state.complete_task(task_id, output)
            # Save full output as artifact
            artifact_path = save_artifact(f"task_{task_id}.md", output)
            # Notify
            if len(output) > 2000:
                tg_send(f"✅ Background task `{task_id}` ({agent}) complete. Output saved.")
                tg_send_file(str(artifact_path), f"Task {task_id} result")
            else:
                tg_send(f"✅ Background task `{task_id}` ({agent}) complete:\n{output}")
        except Exception as e:
            state.fail_task(task_id, str(e))
            tg_send(f"❌ Background task `{task_id}` failed: {e}")

    task_pool.submit(_run)
    log.info("Background task submitted: %s -> %s", task_id, agent)


# ---------------------------------------------------------------------------
# Scheduler — recurring tasks
# ---------------------------------------------------------------------------

class Scheduler(threading.Thread):
    """Runs scheduled tasks on intervals."""
    daemon = True

    def __init__(self):
        super().__init__(name="scheduler")
        self._stop_event = threading.Event()
        self._sent_today = {}

    def _run_time_based_reviews(self, now_local: datetime) -> None:
        today_key = now_local.strftime("%Y-%m-%d")

        # Daily rollup (needed for aggregate stats)
        if not self._sent_today.get("daily_rollup") == today_key:
            self._sent_today["daily_rollup"] = today_key
            try:
                observatory.rollup_daily()
            except Exception:
                log.exception("Daily rollup error")

        # 30-minute heartbeat at :00 and :30
        heartbeat_key = _heartbeat_slot_key(now_local)
        if heartbeat_key and self._sent_today.get("half_hour_heartbeat") != heartbeat_key:
            self._sent_today["half_hour_heartbeat"] = heartbeat_key
            try:
                heartbeat, payload = format_half_hour_heartbeat(now_local)
                tg_send(heartbeat)
                observatory.record("half_hour_heartbeat_sent", data=payload)
            except Exception:
                log.exception("Half-hour heartbeat error")

        # LDP daily briefing at 7:30am
        if now_local.hour == 7 and now_local.minute >= 30 and not self._sent_today.get("ldp_briefing") == today_key:
            self._sent_today["ldp_briefing"] = today_key
            try:
                briefing = li_bridge.get_daily_briefing()
                if briefing.success:
                    tg_send(f"🏠 LDP Daily Briefing\n\n{briefing.content[:3500]}")
            except Exception:
                pass

        # Daily brief at 8am
        if now_local.hour == 8 and not self._sent_today.get("daily_brief") == today_key:
            self._sent_today["daily_brief"] = today_key
            try:
                brief = reviewer.daily_brief()
                pet_section = CypherClawArt.pet_xp_summary(pet_manager.pets)
                tg_send(f"{brief}\n\n{pet_section}")
                observatory.record("daily_brief_sent", data={"date": today_key})
            except Exception:
                log.exception("Daily brief error")

        # Weekly retro on Sunday at 8pm
        if now_local.weekday() == 6 and now_local.hour == 20 and not self._sent_today.get("weekly_retro") == today_key:
            self._sent_today["weekly_retro"] = today_key
            try:
                retro = reviewer.weekly_retro()
                pet_section = CypherClawArt.pet_xp_summary(pet_manager.pets)
                tg_send(f"{retro}\n\n{pet_section}")
                observatory.record("weekly_retro_sent", data={"date": today_key})
            except Exception:
                log.exception("Weekly retro error")

        # Monthly review on 1st at 9am
        if now_local.day == 1 and now_local.hour == 9 and not self._sent_today.get("monthly_review") == today_key:
            self._sent_today["monthly_review"] = today_key
            try:
                review = reviewer.monthly_review()
                tg_send(review)
                observatory.record("monthly_review_sent", data={"date": today_key})
            except Exception:
                log.exception("Monthly review error")

        # Server health check every 6 hours (6am, 12pm, 6pm, midnight)
        if now_local.hour % 6 == 0 and now_local.minute < 1:
            hour_key = f"{today_key}-{now_local.hour}"
            if self._sent_today.get("health_check") != hour_key:
                self._sent_today["health_check"] = hour_key
                try:
                    from server_health import check_health, auto_maintain, telegram_report
                    health = check_health()
                    actions = auto_maintain()
                    # Only send to Telegram if there are warnings
                    if health["warnings"] or actions:
                        tg_send(telegram_report(health, actions))
                    observatory.record("health_check", data={
                        "healthy": health["healthy"],
                        "warnings": len(health["warnings"]),
                        "actions": len(actions),
                    })
                except Exception:
                    log.exception("Health check error")

    def run(self):
        log.info("Scheduler started")
        while not self._stop_event.is_set():
            now = time.time()
            for sched in state.schedules:
                if not sched.get("enabled", True):
                    continue
                last_run = sched.get("last_run", 0)
                interval = sched.get("interval_s", 3600)
                if now - last_run >= interval:
                    log.info("Running scheduled task: %s", sched["name"])
                    sched["last_run"] = now
                    state.save()
                    try:
                        output = run_shell(sched["command"], timeout=60)
                        if sched.get("notify", True):
                            tg_send(f"🕐 Scheduled: {sched['name']}\n```\n{output[:2000]}\n```")
                    except Exception as e:
                        log.exception("Scheduled task error: %s", sched["name"])
                        tg_send(f"❌ Scheduled task {sched['name']} failed: {e}")

            self._run_time_based_reviews(datetime.now())

            self._stop_event.wait(30)  # Check every 30s

    def stop(self):
        self._stop_event.set()


# ---------------------------------------------------------------------------
# Orchestrator routing — the brain
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = ""  # Not used — routing prompt is built inline in route_message()


def fast_route(user_text: str) -> list[dict] | None:
    """Handle messages locally without calling Claude when possible."""
    lower = user_text.lower().strip()
    # Greetings
    if lower in ("hi", "hello", "hey", "yo", "sup", "ping", "you there?", "alive?"):
        claw_portrait = pet_manager.get("cypherclaw").get_portrait()
        return [{"type": "reply", "text": _art.greeting(pet_portrait=claw_portrait)}]

    # Context Pulse — live readout of system context
    if lower in ("pulse", "context", "context pulse", "/pulse"):
        from context_pulse import pulse
        return [{"type": "reply", "text": pulse()}]

    # Status shortcuts
    if lower in ("status", "health", "how are things", "check health", "health check"):
        parts = []
        for label, url in HEALTH_CHECK_SITES.items():
            parts.append(f"echo '{label}:' && curl -sf -o /dev/null -w '%{{http_code}}' {url} 2>&1")
        cmd = " && echo '' && ".join(parts) if parts else "echo 'No health check sites configured'"
        return [
            {"type": "shell", "command": cmd, "label": "🏥 health check all sites"},
        ]

    # Direct shell commands
    if lower.startswith("run ") or lower.startswith("$ "):
        cmd = user_text[4:] if lower.startswith("run ") else user_text[2:]
        return [{"type": "shell", "command": cmd, "label": cmd[:50]}]

    # Direct agent dispatch
    for agent in ("claude", "codex", "gemini"):
        if lower.startswith(f"@{agent} ") or lower.startswith(f"{agent}: "):
            prompt = user_text.split(" ", 1)[1] if " " in user_text else ""
            return [{"type": "agent", "agent": agent, "prompt": prompt, "label": prompt[:50]}]

    # Image generation — use gemini_image.py tool directly, not gemini CLI
    if any(kw in lower for kw in ("generate image", "create image", "make image", "draw", "image of", "picture of", "make me an image")):
        return [{"type": "image_gen", "prompt": user_text}]

    # Explicit research requests
    if lower.startswith("research ") or lower.startswith("investigate "):
        query = user_text.split(" ", 1)[1] if " " in user_text else ""
        return [{"type": "research", "query": query, "scope": "auto", "label": f"research: {query[:40]}"}]

    # Simple yes/no/confirmation — always let the router handle with full context
    if lower in ("yes", "y", "go", "do it", "proceed", "ok", "sure", "both", "both. go.", "apply", "go ahead"):
        if state.pending_confirm:
            return None  # Let the confirmation handler deal with it
        # Let the full router handle this with conversation context
        return None

    return None


def _invoke_router_agent(agent: str, route_prompt: str, route_env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    if agent == "gemini":
        route_cmd = ["gemini", "--approval-mode", "plan", "-p", route_prompt]
        route_input = None
    elif agent == "codex":
        route_cmd = ["codex", "exec", "--full-auto", "-"]
        route_input = route_prompt
    else:
        route_cmd = ["claude", "--dangerously-skip-permissions", "--print", "--effort", "low", "-p", "-"]
        route_input = route_prompt
    return subprocess.run(
        route_cmd,
        input=route_input,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
        env=route_env,
    )


def route_message(user_text: str) -> list[dict]:
    """Route a message — try fast path first, then the best available router."""
    fast = fast_route(user_text)
    if fast is not None:
        pet_manager.on_task_end("cypherclaw", success=True, duration_s=0)
        pet_manager.schedule_idle("cypherclaw")
        return fast

    # Build conversation context — include more for continuity
    recent = list(state.conversation)[-8:]
    convo_lines = []
    for m in recent:
        role = "Anthony" if m["role"] == "user" else "Claw"
        # Include more text for user messages (they contain the intent)
        max_len = 300 if m["role"] == "user" else 150
        convo_lines.append(f"{role}: {m['text'][:max_len]}")
    convo = "\n".join(convo_lines) if convo_lines else "(first message)"

    # Include workspace artifacts in context so router knows about files
    artifacts = list_artifacts()
    artifacts_ctx = ""
    if artifacts:
        artifacts_ctx = f"\nWorkspace files (tools/workspace/): {', '.join(artifacts[:15])}\n"

    route_prompt = (
        "You are CypherClaw's router. Output ONLY a JSON array of steps.\n"
        "Types: reply, shell, agent, research, dev_task, background\n"
        "Agents: claude(architecture/review), codex(coding/impl), gemini(research/writing)\n"
        "Integrations: LifeImprover/LDP (daily briefings, pipeline, energy patterns via /ldp)\n\n"
        "RULES:\n"
        "1. When Anthony says 'go', 'do it', 'implement', 'build', 'apply', 'fix' → use dev_task with FULL context\n"
        "2. When asked to research/compare/evaluate → use research with query\n"
        "3. When asked a question → use agent (claude) with full conversation context in prompt\n"
        "4. Only use shell for quick commands (ls, cat, curl). NEVER use shell as the main action.\n"
        "5. Only use reply for simple acknowledgments. NEVER reply when work is expected.\n"
        "6. Include ALL conversation context in agent/dev_task prompts — agents have NO memory.\n"
        "7. If Anthony refers to previous work, include what was discussed in the prompt.\n"
        "8. reply text must NEVER be empty.\n\n"
        "Format: agent={\"type\":\"agent\",\"agent\":\"claude\",\"prompt\":\"FULL CONTEXT HERE\",\"label\":\"...\"}\n"
        "dev_task={\"type\":\"dev_task\",\"description\":\"FULL SPEC WITH ALL CONTEXT\",\"label\":\"...\"}\n"
        "research={\"type\":\"research\",\"query\":\"...\",\"scope\":\"auto\"}\n"
        f"{artifacts_ctx}"
        f"\nConversation:\n{convo}\n"
        f"\nAnthony: {user_text}\n\nJSON:"
    )

    try:
        pet_manager.on_task_start("cypherclaw")
        route_env = _child_process_env()
        route_env.pop("CLAUDECODE", None)
        available_agents = _available_agents(["claude", "codex", "gemini"])
        router_agent = agent_selector.select(user_text, available_agents=available_agents)
        router_candidates = [router_agent] + [agent for agent in available_agents if agent != router_agent]
        response = ""

        for candidate in router_candidates:
            try:
                result = _invoke_router_agent(candidate, route_prompt, route_env, timeout=60)
            except subprocess.TimeoutExpired:
                log.warning("Routing timed out for %s", candidate)
                continue
            if result.returncode != 0:
                stderr = result.stderr.strip()
                log.warning("Routing failed for %s: rc=%s stderr=%s", candidate, result.returncode, stderr[:200])
                if is_quota_error(stderr):
                    provider = PROVIDERS.get(candidate)
                    if provider:
                        quota_monitor.force_status(
                            provider,
                            "paused",
                            headroom=0.0,
                            confidence="runtime",
                            reason=stderr[:200] or "router quota error",
                        )
                continue
            response = result.stdout.strip() or result.stderr.strip()
            router_agent = candidate
            break

        # Extract JSON array
        cleaned = re.sub(r"```json?\s*", "", response)
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        arr_start = cleaned.find("[")
        arr_end = cleaned.rfind("]") + 1
        if arr_start >= 0 and arr_end > arr_start:
            steps = json.loads(cleaned[arr_start:arr_end])
            if isinstance(steps, list) and steps:
                # Validate: ensure no empty reply texts
                for s in steps:
                    if isinstance(s, dict) and s.get("type") == "reply" and not s.get("text", "").strip():
                        s["text"] = "🦀 (working on it)"
                pet_manager.on_task_end("cypherclaw", success=True, duration_s=0)
                pet_manager.schedule_idle("cypherclaw")
                observatory.record('routing_decision', data={'input': user_text[:100], 'steps': [s.get('type') for s in steps if isinstance(s, dict)]})
                return steps

        # Claude returned text but not JSON — just relay it as a reply
        if response:
            pet_manager.on_task_end("cypherclaw", success=False, duration_s=0)
            pet_manager.schedule_idle("cypherclaw")
            return [{"type": "reply", "text": response[:MAX_MESSAGE_LEN]}]

        direct_agent = _best_available_agent(["claude", "codex", "gemini"])
        full_context = f"Conversation so far:\n{convo}\n\nAnthony's latest message: {user_text}\n\nRespond helpfully and concisely (this is Telegram chat)."
        pet_manager.on_task_end("cypherclaw", success=False, duration_s=0)
        pet_manager.schedule_idle("cypherclaw")
        return [
            {"type": "reply", "text": f"🦀 Routing failed — sending to best available agent ({direct_agent})..."},
            {"type": "agent", "agent": direct_agent, "prompt": full_context, "label": user_text[:50]},
        ]
    except Exception as e:
        log.exception("Route error")
        pet_manager.on_task_end("cypherclaw", success=False, duration_s=0)
        pet_manager.schedule_idle("cypherclaw")
        return [{"type": "reply", "text": f"❌ Error: {e}"}]


# ---------------------------------------------------------------------------
# Step executor
# ---------------------------------------------------------------------------

def execute_plan(steps: list[dict]) -> None:
    """Execute a sequence of orchestrator steps."""
    total = len(steps)
    progress_msg_id = None

    # Show progress tracker for multi-step plans
    if total > 1:
        dots = "○ " * total
        r = tg_api("sendMessage", {"chat_id": CHAT_ID, "text": f"🦀 Executing {total} steps\n{dots}"})
        progress_msg_id = r.get("result", {}).get("message_id")

    for i, step in enumerate(steps):
        # Guard: skip malformed steps (e.g. router returned a string instead of dict)
        if not isinstance(step, dict):
            log.warning("Skipping non-dict step: %s", repr(step)[:100])
            continue
        step_type = step.get("type", "reply")
        log.info("Executing step %d/%d: %s", i + 1, len(steps), step_type)

        # Update progress message with animated dots
        if progress_msg_id:
            label = step.get("label", step.get("text", step_type)[:40])
            tg_edit(progress_msg_id, _art.step_progress(i + 1, total, label))

        try:
            if step_type == "reply":
                text = step.get("text", "")
                tg_send(text)
                state.add_message("assistant", text)

            elif step_type == "shell":
                cmd = step.get("command", "")
                label = step.get("label", cmd[:50])
                tg_send(f"⚙️ running: {label}")
                output = run_shell(cmd)
                response = f"```\n{output[:3500]}\n```"
                tg_send(response)
                state.add_message("assistant", f"[shell: {label}] {output[:200]}")
                if len(output) > 500:
                    save_artifact(f"shell_{int(time.time())}.txt", output)

            elif step_type == "agent":
                agent = step.get("agent") or _best_available_agent()
                prompt = step.get("prompt", "")
                label = step.get("label", f"{agent} task")
                context_ref = step.get("context_artifact")
                if context_ref:
                    prior = read_artifact(context_ref)
                    if prior:
                        prompt = f"Context from previous step:\n{prior}\n\n---\n\n{prompt}"
                output = run_agent(agent, prompt, task_label=label)
                agent_selector.record_outcome(agent, label, success=not output.startswith("["))
                artifact_name = step.get("save_as", f"{agent}_{int(time.time())}.md")
                save_artifact(artifact_name, output)
                pet = pet_manager.get(agent)
                pet_portrait = pet.get_portrait()
                if output.startswith("[") and ("error" in output or "timed out" in output or "not found" in output):
                    tg_send(_art.task_failed(agent, output[:500], pet_portrait=pet_portrait))
                elif len(output) > 2000:
                    tg_send(_art.task_complete(agent, label, pet_portrait=pet_portrait))
                    tg_send_file(str(WORKSPACE_DIR / artifact_name), label)
                else:
                    tg_send(_art.task_complete(agent, label, pet_portrait=pet_portrait))
                    tg_send(output)
                state.add_message("assistant", f"[{agent}: {label}] {output[:200]}")

            elif step_type == "parallel":
                dispatches = step.get("dispatches", [])
                agent_tags = []
                for d in dispatches:
                    ico = {"claude": "🟣", "codex": "🟢", "gemini": "🔵"}.get(d["agent"], "🤖")
                    agent_tags.append(f"{ico}{d.get('label', d['agent'])}")
                tg_send("🔀 parallel launch!\n" + " ┃ ".join(agent_tags))
                results = run_agents_parallel(dispatches)
                for r in results:
                    artifact_name = f"{r['agent']}_{int(time.time())}.md"
                    save_artifact(artifact_name, r["output"])
                    if len(r["output"]) > 1500:
                        tg_send(f"✅ {r['label']} done → `{artifact_name}`")
                        tg_send_file(str(WORKSPACE_DIR / artifact_name), r["label"])
                    else:
                        tg_send(f"✅ {r['label']}:\n{r['output']}")
                    state.add_message("assistant", f"[parallel:{r['label']}] {r['output'][:200]}")

            elif step_type == "background":
                agent = step.get("agent") or _best_available_agent()
                prompt = step.get("prompt", "")
                label = step.get("label", "background task")
                task_id = hashlib.md5(f"{agent}{prompt}{time.time()}".encode()).hexdigest()[:8]
                submit_background_task(task_id, agent, prompt)
                tg_send(f"📋 Queued background task `{task_id}`: {label}\nI'll notify you when it's done.")
                state.add_message("assistant", f"[bg:{task_id}] {label}")

            elif step_type == "schedule":
                name = step.get("name", "unnamed")
                command = step.get("command", "")
                interval = step.get("interval_s", 3600)
                notify = step.get("notify", True)
                # Check for existing schedule with same name
                state.schedules = [s for s in state.schedules if s["name"] != name]
                state.schedules.append({
                    "name": name,
                    "command": command,
                    "interval_s": interval,
                    "notify": notify,
                    "enabled": True,
                    "last_run": 0,
                })
                state.save()
                mins = interval // 60
                tg_send(f"🕐 Scheduled `{name}` every {mins}m: `{command[:80]}`")
                state.add_message("assistant", f"[scheduled: {name} every {mins}m]")

            elif step_type == "confirm":
                text = step.get("text", "")
                # Store remaining steps for after confirmation
                remaining = steps[i + 1:]
                state.pending_confirm = {"text": text, "remaining_steps": remaining}
                state.save()
                tg_send(_art.confirmation_prompt(text))
                state.add_message("assistant", f"[confirm] {text}")
                return  # Stop executing — wait for confirmation

            elif step_type == "artifact":
                action = step.get("action", "list")
                if action == "save":
                    name = step.get("name", f"artifact_{int(time.time())}.md")
                    content = step.get("content", "")
                    save_artifact(name, content)
                    tg_send(f"💾 Saved artifact: `{name}`")
                elif action == "read":
                    name = step.get("name", "")
                    content = read_artifact(name)
                    if content:
                        tg_send(f"📄 `{name}`:\n{content[:3000]}")
                    else:
                        tg_send(f"❌ Artifact not found: `{name}`")
                elif action == "list":
                    artifacts = list_artifacts()
                    if artifacts:
                        tg_send("📁 Workspace:\n" + "\n".join(f"  • {a}" for a in artifacts))
                    else:
                        tg_send("📁 Workspace is empty.")
            elif step_type == "image_gen":
                img_prompt = step.get("prompt", "")
                tg_send("🎨 Generating image...")
                try:
                    result = subprocess.run(
                        [sys.executable, str(TOOLS_DIR / "gemini_image.py"), img_prompt],
                        capture_output=True, text=True, timeout=120,
                        cwd=str(TOOLS_DIR.parent),
                        env=_child_process_env({"GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", "")}),
                    )
                    output = result.stdout.strip()
                    stderr = result.stderr.strip()
                    if result.returncode != 0:
                        tg_send(f"❌ Image generation failed:\n{stderr[:500]}")
                        state.add_message("assistant", f"[image_gen failed] {stderr[:200]}")
                    else:
                        # Parse output for image_path
                        image_path = None
                        caption = ""
                        for line in output.splitlines():
                            if line.startswith("image_path:"):
                                image_path = line.split(":", 1)[1].strip()
                            elif line.startswith("caption:"):
                                caption = line.split(":", 1)[1].strip()
                        if image_path and os.path.isfile(image_path):
                            tg_send_file(image_path, caption or f"🎨 {img_prompt[:50]}")
                            tg_send(f"✅ Image saved: `{image_path}`")
                            state.add_message("assistant", f"[image generated] {image_path}")
                        else:
                            tg_send(f"⚠️ Model responded but no image file.\n{output[:500]}")
                except subprocess.TimeoutExpired:
                    tg_send("⏱️ Image generation timed out (2min limit)")
                except Exception as e:
                    tg_send(f"❌ Image error: {e}")

            elif step_type == "research":
                query = step.get("query", "")
                scope = step.get("scope", "auto")
                label = step.get("label", f"research: {query[:40]}")
                if not query:
                    tg_send("❌ research step requires a query")
                    continue
                try:
                    researcher = get_researcher()
                    research_result = researcher.research(query, scope=scope)
                    if len(research_result.summary) > 3500:
                        tg_send(research_result.summary[:2000] + "\n\n📄 Full report saved to workspace.")
                    else:
                        tg_send(research_result.summary)
                    if research_result.full_report and len(research_result.full_report) > 2500:
                        report_name = f"research_{int(time.time())}.md"
                        report_path = WORKSPACE_DIR / report_name
                        if not report_path.exists():
                            save_artifact(report_name, research_result.full_report)
                        tg_send_file(str(report_path), label)
                    state.add_message("assistant", f"[research: {label}] {research_result.summary[:200]}")
                except Exception as exc:
                    log.exception("Research step failed")
                    tg_send(f"❌ Research failed: {exc}\n\nTry /research {query[:50]}")
                    state.add_message("assistant", f"[research failed: {label}] {exc}")

            elif step_type == "dev_task":
                desc = step.get("description", "")
                label = step.get("label", "dev task")
                if not desc:
                    tg_send("\u274c dev_task requires a description")
                    continue

                task_id = hashlib.md5(f"dev_{desc}_{time.time()}".encode()).hexdigest()[:8]

                sdp_env = _child_process_env()
                sdp_env.pop("CLAUDECODE", None)
                sdp_env["PATH"] = f"{Path.home() / '.local' / 'bin'}:/usr/local/bin:/usr/bin:/bin"

                def _sdp(cmd, timeout_s=60):
                    return run_sdp_command(
                        cmd,
                        project_root=PROJECT_ROOT,
                        env=sdp_env,
                        timeout_s=timeout_s,
                    )

                try:
                    # ── Phase 1: Generate PRD table from request ──
                    tg_send(f"\U0001f6e0\ufe0f {label}\n\n\U0001f4cb Phase 1: Generating PRD...")

                    prd_prompt = (
                        f"Generate a PRD requirements table for this request.\n\n"
                        f"Request: {desc}\n\nProject: {PROJECT_ROOT}\n\n"
                        f"Output ONLY a markdown table:\n"
                        f"| ID | Requirement | Priority | Tier | Acceptance Criteria |\n"
                        f"|---|---|---|---|---|\n\n"
                        f"IDs: REQ-001, etc. Priority: MUST/SHOULD/COULD. "
                        f"Tier: T1 (<45min), T2 (<2hr), T3 (<6hr). "
                        f"Break large features into multiple rows. "
                        f"Output ONLY the table."
                    )
                    prd_output = run_agent(_best_available_agent(), prd_prompt, task_label=f"\U0001f4cb PRD: {label}")

                    prd_dir = PROJECT_ROOT / "sdp"
                    prd_dir.mkdir(parents=True, exist_ok=True)
                    prd_file = prd_dir / f"prd-{task_id}.md"
                    prd_file.write_text(f"# PRD: {label}\n\n{prd_output}")
                    save_artifact(f"prd_{task_id}.md", f"# PRD: {label}\n\n{prd_output}")
                    tg_send_file(str(prd_file), f"\U0001f4cb PRD: {label}")

                    # ── Phase 2: Analyze PRD → task graph ──
                    tg_send("\U0001f4e6 Phase 2: Analyzing PRD \u2192 generating task graph...")

                    out, err, rc = _sdp(["sdp-cli", "analyze", "--prd", str(prd_file), "--load"])
                    if rc != 0:
                        log.warning("sdp-cli analyze: %s", err[:300])
                        tg_send(f"\u26a0\ufe0f Analyze: {err[:300] or out[:300]}")

                    # Send generated artifacts
                    for artifact in ["task-graph.md", "implementation-plan.md"]:
                        p = prd_dir / artifact
                        if p.exists():
                            tg_send_file(str(p), f"\U0001f4ca {artifact}")

                    # Show task count
                    out, _, _ = _sdp(["sdp-cli", "tasks", "list"])
                    pending = out.count("pending") if out else 0
                    tg_send(f"\U0001f4e6 {pending} tasks queued")

                    # ── Phase 3: Run pipeline ──
                    tg_send("\U0001f680 Phase 3: Running pipeline (lead \u2192 gates \u2192 verify \u2192 merge)...")

                    # Start monitor thread to show sdp-cli progress on Telegram
                    monitor_msg = tg_api("sendMessage", {"chat_id": CHAT_ID, "text": "\U0001f680 sdp-cli pipeline starting..."})
                    monitor_msg_id = monitor_msg.get("result", {}).get("message_id")
                    monitor_stop = threading.Event()

                    def _monitor_sdp():
                        state_file = PROJECT_ROOT / ".sdp" / "run-state.json"
                        while not monitor_stop.is_set():
                            try:
                                if state_file.exists():
                                    data = json.loads(state_file.read_text())
                                    # Extract useful info from run state
                                    current = data.get("current_task", "")
                                    phase = data.get("phase", "")
                                    agent = data.get("active_agent", "")
                                    elapsed = data.get("elapsed_seconds", 0)

                                    status_text = (
                                        f"\U0001f680 sdp-cli running ({int(elapsed)}s)\n"
                                        f"\U0001f4cb {str(current)[:60]}\n"
                                        f"\U0001f504 Phase: {phase}\n"
                                        f"\U0001f916 Agent: {agent}"
                                    )
                                    if monitor_msg_id:
                                        tg_edit(monitor_msg_id, status_text)
                            except Exception:
                                pass
                            monitor_stop.wait(5)

                    monitor_thread = threading.Thread(target=_monitor_sdp, daemon=True)
                    monitor_thread.start()

                    out, err, rc = _sdp(["sdp-cli", "run"], timeout_s=None)

                    monitor_stop.set()
                    monitor_thread.join(timeout=3)
                    if monitor_msg_id:
                        tg_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": monitor_msg_id})

                    save_artifact(f"sdp_run_{task_id}.md", f"STDOUT:\n{out}\n\nSTDERR:\n{err}")

                    if rc == 0:
                        if len(out) > 2000:
                            tg_send_file(str(WORKSPACE_DIR / f"sdp_run_{task_id}.md"), f"\u2705 {label}")
                        tg_send(f"\u2705 Pipeline complete: {label}")
                    else:
                        tg_send(f"\u274c Pipeline failed (exit {rc})\n{err[:500]}")

                    # ── Phase 4: Final status ──
                    out, _, _ = _sdp(["sdp-cli", "status"])
                    if out:
                        tg_send(f"\U0001f4ca Final status:\n{out[:1500]}")

                    state.add_message("assistant",
                        f"[dev_task: {label}] PRD \u2192 analyze({pending} tasks) \u2192 run(exit={rc})")

                except subprocess.TimeoutExpired:
                    tg_send("\u23f1\ufe0f sdp-cli timed out. Check: sdp-cli status")
                    state.add_message("assistant", f"[dev_task: {label}] timeout")
                except FileNotFoundError:
                    tg_send("\u274c sdp-cli not found. Install: pip install sdp-cli")
                except Exception as exc:
                    log.exception("dev_task error")
                    tg_send(f"\u274c Dev task error: {exc}")
                    state.add_message("assistant", f"[dev_task: {label}] error: {exc}")

            else:
                tg_send(f"⚠️ Unknown step type: {step_type}")

        except Exception as e:
            log.exception("Step execution error")
            tg_send(f"❌ Step {i+1} failed: {e}")

    # Clean up progress message
    if progress_msg_id:
        tg_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": progress_msg_id})


# ---------------------------------------------------------------------------
# Built-in commands (no agent routing needed)
# ---------------------------------------------------------------------------

BUILTIN_COMMANDS = {
    "/status": "Show daemon status, running tasks, schedules",
    "/local": "Show local Ollama health and loaded models",
    "/monitor": "Show live queue progress, active task, and runner status",
    "/quota": "Show provider quota headroom and active agents",
    "/prd": "Show the ordered PRD roadmap and current implementation status",
    "/tasks": "Show actionable queue tasks (usage: /tasks [pending|needs_split|blocked|attention|running|frozen|all] [limit])",
    "/schedules": "List scheduled tasks",
    "/workspace": "List workspace artifacts",
    "/art": "Generate ASCII art",
    "/pets": "Check your agent pets' status and evolution",
    "/feed": "Feed a pet to reduce hunger (usage: /feed claude)",
    "/play": "Play with a pet to boost mood (usage: /play claude)",
    "/stats": "Agent performance stats",
    "/retro": "Generate a retrospective now",
    "/brief": "Generate today's daily brief",
    "/research": "Deep research (usage: /research <topic>)",
    "/ldp": "LifeImprover daily briefing & status",
    "/health": "Server health check",
    "/promptclaw": "Run a task through PromptClaw orchestrator (routing \u2192 lead \u2192 verify)",
    "/pulse": "Context pulse — see the AI's own context",
    "/help": "Show available commands",
}

DEFAULT_PRD_ROADMAP = [
    ("Home Resilience", ("20260331T232739Z",)),
    ("Restructure", ("20260328T142659Z",)),
    ("GlyphWeave Studio Loop", ("20260401T195527Z",)),
    ("GlyphWeave Art", ("20260327T172236Z",)),
    ("GlyphWeave Art B2", ("20260327T182001Z", "20260327T182001Za", "20260327T182001Zb", "20260327T182001Zc", "20260327T182001Zd")),
    ("Pet System v2", ("20260327T221957Z",)),
    ("Narrative Engine", ("20260329T183119Z",)),
    ("SenseWeave", ("20260331T210000Z",)),
    ("Proactive Intel", ("20260327T234426Z",)),
    ("Web Platform", ("20260327T233208Z",)),
    ("Federation", ("20260329T205115Z",)),
]

DEFAULT_PRD_COMPLETED = [
    ("Demo Fixes", ("20260326T185852Z",)),
    ("Pet Animation", ("20260326T195444Z", "20260326T195444Za", "20260326T195444Zb", "20260326T195444Zc", "20260326T195444Zd")),
    ("Model Awareness", ("20260327T154047Z", "20260327T154047Za", "20260327T154047Zb", "20260327T154047Zc", "20260327T154047Zd")),
    ("Server Optimization", ("20260327T223909Z",)),
    ("Verification", ("20260327T235215Z",)),
    ("Introspector", ("20260329T191308Z",)),
    ("Gap Analyzer", ("20260329T202017Z",)),
    ("Hotfixes", ("20260330T235959Z",)),
]

_ROADMAP_ROW_RE = re.compile(r"^\|\s*\d+\s*\|\s*\[[^\]]+\]\(([^)]+)\)\s*\|")

_TASK_PROGRESS_CATEGORY_BY_STATUS = {
    "complete": "complete",
    "running": "running",
    "pending": "pending",
    "blocked": "blocked",
    "needs_review": "needs_attention",
    "rolled_back": "needs_attention",
    "quarantined": "needs_attention",
    "needs_split": "needs_split",
    "split": "skipped",
}

_TASK_FILTERS: dict[str, dict[str, object]] = {
    "running": {"label": "Running", "statuses": ("running",), "frozen_only": False},
    "pending": {"label": "Pending", "statuses": ("pending",), "frozen_only": False},
    "needs_split": {"label": "Needs Split", "statuses": ("needs_split",), "frozen_only": False},
    "blocked": {"label": "Blocked", "statuses": ("blocked",), "frozen_only": False},
    "attention": {
        "label": "Needs Attention",
        "statuses": ("needs_review", "rolled_back", "quarantined"),
        "frozen_only": False,
    },
    "skipped": {"label": "Decomposed Parents", "statuses": ("split",), "frozen_only": False},
    "frozen": {"label": "Frozen", "statuses": None, "frozen_only": True},
    "all": {"label": "All Tasks", "statuses": None, "frozen_only": None},
}

_TASK_FILTER_ALIASES = {
    "running": "running",
    "active": "running",
    "pending": "pending",
    "queued": "pending",
    "needs_split": "needs_split",
    "needs-split": "needs_split",
    "needssplit": "needs_split",
    "split_needed": "needs_split",
    "split-needed": "needs_split",
    "needs_attention": "attention",
    "needs-attention": "attention",
    "needsattention": "attention",
    "attention": "attention",
    "blocked": "blocked",
    "frozen": "frozen",
    "decomposed": "skipped",
    "skipped": "skipped",
    "split_parents": "skipped",
    "split-parents": "skipped",
    "all": "all",
}


def _empty_rollup() -> dict[str, int]:
    return {
        "total": 0,
        "complete": 0,
        "running": 0,
        "pending": 0,
        "needs_split": 0,
        "blocked": 0,
        "needs_attention": 0,
        "skipped": 0,
        "frozen": 0,
    }


def _progress_category(status: str) -> str:
    return _TASK_PROGRESS_CATEGORY_BY_STATUS.get(status, "pending")


def _queue_db_path() -> Path:
    return PROJECT_ROOT / ".sdp" / "state.db"


def _roadmap_doc_path() -> Path:
    return PROJECT_ROOT / "sdp" / "execution-roadmap.md"


def _roadmap_batch_map_path() -> Path:
    return PROJECT_ROOT / "sdp" / "execution-roadmap.queue-map.json"


def _humanize_prd_filename(filename: str) -> str:
    stem = Path(filename).stem
    if stem.startswith("prd-"):
        stem = stem[4:]
    parts = []
    for piece in stem.split("-"):
        lowered = piece.lower()
        if lowered == "v2":
            parts.append("v2")
        elif lowered == "midi":
            parts.append("MIDI")
        else:
            parts.append(piece.capitalize())
    return " ".join(parts)


def _read_prd_title(prd_filename: str) -> str:
    prd_path = _roadmap_doc_path().parent / prd_filename
    try:
        for line in prd_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            title = stripped.lstrip("#").strip()
            if title.startswith("PRD:"):
                title = title[4:].strip()
            if " — " in title:
                title = title.split(" — ", 1)[0].strip()
            return title or _humanize_prd_filename(prd_filename)
    except OSError:
        pass
    return _humanize_prd_filename(prd_filename)


def _load_prd_roadmap() -> tuple[list[tuple[str, tuple[str, ...]]], list[tuple[str, tuple[str, ...]]]]:
    doc_path = _roadmap_doc_path()
    batch_map_path = _roadmap_batch_map_path()
    if not doc_path.exists() or not batch_map_path.exists():
        return DEFAULT_PRD_ROADMAP, DEFAULT_PRD_COMPLETED

    try:
        roadmap_map = json.loads(batch_map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_PRD_ROADMAP, DEFAULT_PRD_COMPLETED

    if not isinstance(roadmap_map, dict):
        return DEFAULT_PRD_ROADMAP, DEFAULT_PRD_COMPLETED

    stages = roadmap_map.get("stages", {})
    if not isinstance(stages, dict):
        return DEFAULT_PRD_ROADMAP, DEFAULT_PRD_COMPLETED

    roadmap: list[tuple[str, tuple[str, ...]]] = []
    for line in doc_path.read_text(encoding="utf-8").splitlines():
        match = _ROADMAP_ROW_RE.match(line.strip())
        if not match:
            continue
        prd_filename = Path(match.group(1)).name
        batch_ids = stages.get(prd_filename, ())
        if not isinstance(batch_ids, list):
            batch_ids = ()
        roadmap.append(
            (
                _read_prd_title(prd_filename),
                tuple(str(batch_id) for batch_id in batch_ids if batch_id),
            )
        )

    if not roadmap:
        return DEFAULT_PRD_ROADMAP, DEFAULT_PRD_COMPLETED

    completed_earlier: list[tuple[str, tuple[str, ...]]] = []
    completed_entries = roadmap_map.get("completed_earlier", [])
    if isinstance(completed_entries, list):
        for entry in completed_entries:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label", "")).strip()
            batch_ids = entry.get("batches", ())
            if not label or not isinstance(batch_ids, list):
                continue
            completed_earlier.append(
                (label, tuple(str(batch_id) for batch_id in batch_ids if batch_id))
            )

    return roadmap, completed_earlier


def _queue_db_exists() -> bool:
    return _queue_db_path().exists()


def _settings_path() -> Path:
    return PROJECT_ROOT / "sdp.toml"


def _table_exists(con: sqlite3.Connection, table_name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _runner_service_state() -> str:
    system = platform.system().lower()
    if system == "linux":
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "cypherclaw-sdp-runner.service"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return "unknown"
        state = (result.stdout or "").strip()
        return state or "inactive"

    try:
        result = subprocess.run(
            ["pgrep", "-af", "sdp-cli run"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return "unknown"
    return "active" if result.returncode == 0 and (result.stdout or "").strip() else "inactive"


def _batch_rollups() -> dict[str, dict[str, int]]:
    db_path = _queue_db_path()
    if not db_path.exists():
        return {}

    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            """
            SELECT
                substr(
                    CASE
                        WHEN COALESCE(parent_task_id, '') = '' THEN task_id
                        ELSE parent_task_id
                    END,
                    instr(
                        CASE
                            WHEN COALESCE(parent_task_id, '') = '' THEN task_id
                            ELSE parent_task_id
                        END,
                        '@'
                    ) + 1
                ) AS batch,
                status,
                COALESCE(frozen, 0) AS frozen,
                COUNT(*) AS count
            FROM tasks
            GROUP BY batch, status, frozen
            """
        ).fetchall()
    finally:
        con.close()

    rollups: dict[str, dict[str, int]] = {}
    for batch, status, frozen, count in rows:
        batch_key = str(batch)
        bucket = rollups.setdefault(batch_key, _empty_rollup())
        if int(frozen or 0):
            bucket["frozen"] += int(count)
            continue
        category = _progress_category(str(status))
        bucket[category] = bucket.get(category, 0) + int(count)
        if category != "skipped":
            bucket["total"] += int(count)
    return rollups


def _root_queue_counts() -> dict[str, int]:
    db_path = _queue_db_path()
    if not db_path.exists():
        return _empty_rollup()

    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            """
            SELECT status, COALESCE(frozen, 0) AS frozen, COUNT(*)
            FROM tasks
            GROUP BY status, frozen
            """
        ).fetchall()
    finally:
        con.close()

    counts = _empty_rollup()
    for status, frozen, count in rows:
        if int(frozen or 0):
            counts["frozen"] += int(count or 0)
            continue
        category = _progress_category(str(status))
        counts[category] = counts.get(category, 0) + int(count or 0)
        if category != "skipped":
            counts["total"] += int(count or 0)
    return counts


def _active_task_snapshot() -> dict[str, str] | None:
    db_path = _queue_db_path()
    if not db_path.exists():
        return None

    con = sqlite3.connect(db_path)
    try:
        task_row = con.execute(
            """
            SELECT task_id, COALESCE(parent_task_id, ''), status
            FROM tasks
            WHERE status='running'
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """
        ).fetchone()
        if task_row is None:
            return None
        task_id, parent_task_id, status = task_row
        run_row = con.execute(
            """
            SELECT COALESCE(lead_agent, ''), COALESCE(verify_agent, ''), COALESCE(started_at, ''), COALESCE(verdict, '')
            FROM task_runs
            WHERE task_id=?
              AND TRIM(COALESCE(completed_at, '')) = ''
            ORDER BY started_at DESC, rowid DESC
            LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        if run_row is None:
            run_row = con.execute(
                """
                SELECT COALESCE(lead_agent, ''), COALESCE(verify_agent, ''), COALESCE(started_at, ''), COALESCE(verdict, '')
                FROM task_runs
                WHERE task_id=?
                ORDER BY started_at DESC, rowid DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
    finally:
        con.close()

    lead = ""
    verify = ""
    started_at = ""
    verdict = ""
    if run_row is not None:
        lead, verify, started_at, verdict = (str(value or "") for value in run_row)

    return {
        "task_id": str(task_id),
        "parent_task_id": str(parent_task_id),
        "status": str(status),
        "lead_agent": lead,
        "verify_agent": verify,
        "started_at": started_at,
        "verdict": verdict,
    }


def _queue_state_drift() -> dict[str, int]:
    db_path = _queue_db_path()
    if not db_path.exists():
        return {"running_without_open": 0, "stale_open_runs": 0, "duplicate_open_runs": 0}

    con = sqlite3.connect(db_path)
    try:
        if not _table_exists(con, "tasks") or not _table_exists(con, "task_runs"):
            return {"running_without_open": 0, "stale_open_runs": 0, "duplicate_open_runs": 0}
        row = con.execute(
            """
            WITH open_runs AS (
                SELECT task_id, COUNT(*) AS open_count
                FROM task_runs
                WHERE TRIM(COALESCE(completed_at, '')) = ''
                GROUP BY task_id
            )
            SELECT
                (
                    SELECT COUNT(*)
                    FROM tasks t
                    WHERE t.status = 'running'
                      AND NOT EXISTS (
                          SELECT 1 FROM open_runs o WHERE o.task_id = t.task_id
                      )
                ) AS running_without_open,
                (
                    SELECT COUNT(*)
                    FROM open_runs o
                    LEFT JOIN tasks t ON t.task_id = o.task_id
                    WHERE COALESCE(t.status, '') != 'running'
                ) AS stale_open_runs,
                (
                    SELECT COUNT(*)
                    FROM open_runs
                    WHERE open_count > 1
                ) AS duplicate_open_runs
            """
        ).fetchone()
    finally:
        con.close()

    if row is None:
        return {"running_without_open": 0, "stale_open_runs": 0, "duplicate_open_runs": 0}

    return {
        "running_without_open": int(row[0] or 0),
        "stale_open_runs": int(row[1] or 0),
        "duplicate_open_runs": int(row[2] or 0),
    }


def _format_background_tasks_fallback() -> str:
    if not state.tasks:
        return "🧾 Queue Tasks\nQueue DB unavailable and no daemon background tasks are active."

    lines = ["🧾 Queue Tasks", "Queue DB unavailable. Showing daemon background tasks instead:"]
    for tid, task in sorted(
        state.tasks.items(),
        key=lambda item: item[1].get("created", ""),
        reverse=True,
    )[:10]:
        icon = {"running": "🔄", "done": "✅", "failed": "❌"}.get(task.get("status", ""), "❓")
        agent = task.get("agent", "unknown")
        status = task.get("status", "unknown")
        lines.append(f"{icon} `{tid}` ({agent}) — {status}")
    return "\n".join(lines)


def _normalize_task_filter(words: list[str]) -> str | None:
    if not words:
        return None
    normalized = "_".join(word.strip().lower() for word in words if word.strip())
    if not normalized:
        return None
    normalized = normalized.replace("-", "_")
    return _TASK_FILTER_ALIASES.get(normalized)


def _parse_tasks_args(args: list[str]) -> tuple[str | None, int]:
    limit = 10
    words: list[str] = []
    for arg in args:
        stripped = arg.strip()
        if not stripped:
            continue
        if stripped.isdigit():
            limit = max(1, min(25, int(stripped)))
            continue
        words.append(stripped)

    filter_key = _normalize_task_filter(words)
    return filter_key, limit


def _normalize_stage_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _parse_task_stage_args(args: list[str]) -> tuple[str | None, str | int | None, int]:
    if not args:
        return None, None, 10

    mode = args[0].strip().lower()
    if mode not in {"prd", "stage"}:
        return None, None, 10

    tail = [arg.strip() for arg in args[1:] if arg.strip()]
    if not tail:
        return mode, None, 10

    limit = 10
    if mode == "prd":
        stage_ref = tail[0]
        if len(tail) > 1 and tail[1].isdigit():
            limit = max(1, min(25, int(tail[1])))
        if stage_ref.isdigit():
            return mode, int(stage_ref), limit
        return mode, stage_ref, limit

    if tail[-1].isdigit():
        limit = max(1, min(25, int(tail[-1])))
        tail = tail[:-1]
    stage_query = " ".join(tail).strip()
    return mode, stage_query or None, limit


def _resolve_stage_reference(stage_ref: str | int) -> tuple[int, str, tuple[str, ...]] | None:
    roadmap, _ = _load_prd_roadmap()
    if isinstance(stage_ref, int):
        if 1 <= stage_ref <= len(roadmap):
            label, batches = roadmap[stage_ref - 1]
            return stage_ref, label, batches
        return None

    query = _normalize_stage_label(str(stage_ref))
    if not query:
        return None

    exact_matches = [
        (idx, label, batches)
        for idx, (label, batches) in enumerate(roadmap, start=1)
        if _normalize_stage_label(label) == query
    ]
    if exact_matches:
        return exact_matches[0]

    substring_matches = [
        (idx, label, batches)
        for idx, (label, batches) in enumerate(roadmap, start=1)
        if query in _normalize_stage_label(label)
    ]
    if len(substring_matches) == 1:
        return substring_matches[0]
    return None


def _stage_suggestions(stage_ref: str) -> list[str]:
    query = _normalize_stage_label(stage_ref)
    roadmap, _ = _load_prd_roadmap()
    if not query:
        return []
    matches = [
        f"{idx}. {label}"
        for idx, (label, _batches) in enumerate(roadmap, start=1)
        if query in _normalize_stage_label(label)
    ]
    return matches[:5]


def _task_filter_config(filter_key: str) -> tuple[str, tuple[str, ...] | None, bool | None]:
    config = _TASK_FILTERS[filter_key]
    label = str(config["label"])
    raw_statuses = config["statuses"]
    statuses = tuple(str(status) for status in raw_statuses) if raw_statuses is not None else None
    frozen_only = config["frozen_only"]
    return label, statuses, frozen_only if isinstance(frozen_only, bool) or frozen_only is None else None


def _task_batch_clause(batches: tuple[str, ...]) -> tuple[str, list[object]]:
    placeholders = ", ".join("?" for _ in batches)
    expr = """
        substr(
            CASE
                WHEN COALESCE(parent_task_id, '') = '' THEN task_id
                ELSE parent_task_id
            END,
            instr(
                CASE
                    WHEN COALESCE(parent_task_id, '') = '' THEN task_id
                    ELSE parent_task_id
                END,
                '@'
            ) + 1
        )
    """
    return f"{expr} IN ({placeholders})", [*batches]


def _task_match_count(
    filter_key: str,
    *,
    root_only: bool = False,
    batches: tuple[str, ...] | None = None,
) -> int:
    db_path = _queue_db_path()
    if not db_path.exists():
        return 0

    label, statuses, frozen_only = _task_filter_config(filter_key)
    del label

    clauses: list[str] = []
    params: list[object] = []
    if frozen_only is True:
        clauses.append("COALESCE(frozen, 0) = 1")
    elif frozen_only is False:
        clauses.append("COALESCE(frozen, 0) = 0")
    if statuses:
        placeholders = ", ".join("?" for _ in statuses)
        clauses.append(f"status IN ({placeholders})")
        params.extend(statuses)
    if root_only:
        clauses.append("COALESCE(parent_task_id, '') = ''")
    if batches:
        clause, batch_params = _task_batch_clause(batches)
        clauses.append(clause)
        params.extend(batch_params)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    con = sqlite3.connect(db_path)
    try:
        if not _table_exists(con, "tasks"):
            return 0
        row = con.execute(f"SELECT COUNT(*) FROM tasks {where_sql}", params).fetchone()
    finally:
        con.close()

    return int(row[0] or 0) if row is not None else 0


def _task_rows(
    filter_key: str,
    *,
    limit: int,
    root_only: bool = False,
    batches: tuple[str, ...] | None = None,
) -> list[dict[str, object]]:
    db_path = _queue_db_path()
    if not db_path.exists():
        return []

    _, statuses, frozen_only = _task_filter_config(filter_key)
    clauses: list[str] = []
    params: list[object] = []
    if frozen_only is True:
        clauses.append("COALESCE(frozen, 0) = 1")
    elif frozen_only is False:
        clauses.append("COALESCE(frozen, 0) = 0")
    if statuses:
        placeholders = ", ".join("?" for _ in statuses)
        clauses.append(f"status IN ({placeholders})")
        params.extend(statuses)
    if root_only:
        clauses.append("COALESCE(parent_task_id, '') = ''")
    if batches:
        clause, batch_params = _task_batch_clause(batches)
        clauses.append(clause)
        params.extend(batch_params)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    order_sql = "ORDER BY updated_at DESC, created_at DESC, task_id ASC"
    if frozen_only is True:
        order_sql = "ORDER BY COALESCE(frozen_at, '') DESC, updated_at DESC, task_id ASC"
    elif statuses == ("pending",):
        order_sql = "ORDER BY priority DESC, created_at ASC, task_id ASC"
    elif statuses == ("needs_split",):
        order_sql = "ORDER BY priority DESC, updated_at DESC, task_id ASC"

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        if not _table_exists(con, "tasks"):
            return []
        rows = con.execute(
            f"""
            SELECT
                task_id,
                COALESCE(description, '') AS description,
                COALESCE(tier, '') AS tier,
                COALESCE(status, '') AS status,
                COALESCE(priority, 0) AS priority,
                COALESCE(parent_task_id, '') AS parent_task_id,
                COALESCE(status_reason, '') AS status_reason,
                COALESCE(frozen, 0) AS frozen,
                COALESCE(frozen_reason, '') AS frozen_reason,
                COALESCE(created_at, '') AS created_at,
                COALESCE(updated_at, '') AS updated_at
            FROM tasks
            {where_sql}
            {order_sql}
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    finally:
        con.close()

    return [dict(row) for row in rows]


def _task_icon(task: dict[str, object]) -> str:
    if int(task.get("frozen", 0) or 0):
        return "🧊"
    return {
        "running": "🔄",
        "pending": "🟡",
        "needs_split": "✂️",
        "blocked": "⛔",
        "needs_review": "⚠️",
        "rolled_back": "↩️",
        "quarantined": "🚧",
        "split": "🪓",
        "complete": "✅",
    }.get(str(task.get("status", "")), "❓")


def _task_line(task: dict[str, object], *, show_status: bool = False) -> str:
    task_id = str(task.get("task_id", ""))
    description = _truncate_summary(str(task.get("description", "") or "Untitled task"), limit=78)
    tier = str(task.get("tier", "")).strip()
    parent_task_id = str(task.get("parent_task_id", "")).strip()
    status = str(task.get("status", "")).strip()
    frozen = int(task.get("frozen", 0) or 0) == 1
    reason = str(task.get("frozen_reason" if frozen else "status_reason", "")).strip()

    extras: list[str] = []
    if tier:
        extras.append(tier)
    if show_status:
        extras.append("frozen" if frozen else status.replace("_", " "))
    if parent_task_id:
        extras.append(f"child of {parent_task_id}")
    if reason:
        extras.append(_truncate_summary(reason, limit=54))

    suffix = f" — {' · '.join(extras)}" if extras else ""
    return f"{_task_icon(task)} `{task_id}` {description}{suffix}"


def _append_task_section(
    lines: list[str],
    title: str,
    tasks: list[dict[str, object]],
    *,
    show_status: bool = False,
) -> None:
    if not tasks:
        return
    lines.append("")
    lines.append(f"{title}:")
    for task in tasks:
        lines.append(_task_line(task, show_status=show_status))


def _task_summary_line(summary: dict[str, int]) -> str:
    parts = [
        f"{summary.get('running', 0)} running",
        f"{summary.get('pending', 0)} pending",
    ]
    if summary.get("needs_split", 0):
        parts.append(f"{summary['needs_split']} needs split")
    if summary.get("blocked", 0):
        parts.append(f"{summary['blocked']} blocked")
    if summary.get("needs_attention", 0):
        parts.append(f"{summary['needs_attention']} needs attention")
    if summary.get("skipped", 0):
        parts.append(f"{summary['skipped']} decomposed")
    if summary.get("frozen", 0):
        parts.append(f"{summary['frozen']} frozen")
    return "Summary: " + " · ".join(parts)


def _format_stage_tasks_status(stage_number: int, label: str, batches: tuple[str, ...], limit: int) -> str:
    batch_rollups = _batch_rollups()
    summary = _merge_rollups(batches, batch_rollups)

    lines = [f"🧾 Tasks · PRD {stage_number} · {label}", _task_summary_line(summary)]
    if batches:
        lines.append("Batches: " + ", ".join(batches))

    _append_task_section(lines, "Running", _task_rows("running", limit=min(limit, 3), batches=batches))
    _append_task_section(lines, "Next Root Tasks", _task_rows("pending", limit=limit, root_only=True, batches=batches))
    _append_task_section(lines, "Needs Split", _task_rows("needs_split", limit=limit, root_only=True, batches=batches))
    _append_task_section(lines, "Blocked", _task_rows("blocked", limit=limit, root_only=True, batches=batches))
    _append_task_section(lines, "Needs Attention", _task_rows("attention", limit=limit, root_only=True, batches=batches))

    background_parts = []
    if summary.get("frozen", 0):
        background_parts.append(f"{summary['frozen']} frozen")
    if summary.get("skipped", 0):
        background_parts.append(f"{summary['skipped']} decomposed parents")
    if background_parts:
        lines.append("")
        lines.append("Background: " + " · ".join(background_parts))

    if len(lines) <= 3:
        lines.append("No tasks loaded for this roadmap stage.")

    lines.append("")
    lines.append(
        f"Use: `/tasks prd {stage_number} {limit}` · "
        f"`/tasks stage {label.lower()} {limit}`"
    )
    return "\n".join(lines)[:3500]


def format_tasks_status(args: list[str] | None = None) -> str:
    """Return an actionable queue-task summary for Telegram."""
    args = args or []
    if not _queue_db_exists():
        return _format_background_tasks_fallback()

    stage_mode, stage_ref, stage_limit = _parse_task_stage_args(args)
    if stage_mode is not None:
        if stage_ref is None:
            if stage_mode == "prd":
                return "🧾 Queue Tasks\nUsage: `/tasks prd <stage-number> [limit]`"
            return "🧾 Queue Tasks\nUsage: `/tasks stage <stage name> [limit]`"

        resolved = _resolve_stage_reference(stage_ref)
        if resolved is None:
            if stage_mode == "prd":
                return f"🧾 Queue Tasks\nUnknown roadmap stage `{stage_ref}`."
            suggestions = _stage_suggestions(str(stage_ref))
            if suggestions:
                return "🧾 Queue Tasks\nStage not found. Try: " + " · ".join(suggestions)
            return f"🧾 Queue Tasks\nStage not found: `{stage_ref}`."

        stage_number, label, batches = resolved
        return _format_stage_tasks_status(stage_number, label, batches, stage_limit)

    filter_key, limit = _parse_tasks_args(args)
    if args and filter_key is None:
        return (
            "🧾 Queue Tasks\n"
            "Unknown filter. Use `/tasks`, `/tasks pending 10`, `/tasks needs_split`, "
            "`/tasks blocked`, `/tasks attention`, `/tasks running`, `/tasks frozen`, or `/tasks all 20`."
        )

    if filter_key is None:
        counts = _root_queue_counts()
        lines = ["🧾 Queue Tasks", _task_summary_line(counts)]

        _append_task_section(lines, "Running", _task_rows("running", limit=3, root_only=False))
        _append_task_section(lines, "Next Root Tasks", _task_rows("pending", limit=5, root_only=True))
        _append_task_section(lines, "Needs Split", _task_rows("needs_split", limit=5, root_only=True))
        _append_task_section(lines, "Blocked", _task_rows("blocked", limit=5, root_only=True))
        _append_task_section(lines, "Needs Attention", _task_rows("attention", limit=5, root_only=True))

        if counts["frozen"] or counts["skipped"]:
            lines.append("")
            detail_parts = []
            if counts["frozen"]:
                detail_parts.append(f"{counts['frozen']} frozen")
            if counts["skipped"]:
                detail_parts.append(f"{counts['skipped']} decomposed parents")
            lines.append("Background: " + " · ".join(detail_parts))

        lines.append("")
        lines.append(
            "Use: `/tasks pending 10` · `/tasks needs_split` · `/tasks blocked` · "
            "`/tasks attention` · `/tasks frozen` · `/tasks prd 6` · `/tasks stage clone and home creation`"
        )
        return "\n".join(lines)[:3500]

    label, _, _ = _task_filter_config(filter_key)
    total_matches = _task_match_count(filter_key)
    tasks = _task_rows(filter_key, limit=limit, root_only=False)
    lines = [f"🧾 Tasks · {label}", f"Showing {len(tasks)} of {total_matches}"]
    if not tasks:
        lines.append(f"No {label.lower()} tasks.")
    else:
        show_status = filter_key == "all"
        for task in tasks:
            lines.append(_task_line(task, show_status=show_status))
    return "\n".join(lines)[:3500]


def _truncate_summary(text: str, limit: int = 72) -> str:
    stripped = " ".join(text.split())
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "…"


def _sdp_cli_env() -> dict[str, str]:
    env = _child_process_env()
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}:/usr/local/bin:/usr/bin:/bin"
    sibling_sdp_src = PROJECT_ROOT.parent / "sdp-cli" / "src"
    if sibling_sdp_src.exists():
        existing = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = (
            f"{sibling_sdp_src}:{existing}" if existing else str(sibling_sdp_src)
        )
    return env


def _normalize_monitor_snapshot(text: str) -> str:
    cleaned = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text or "")
    lines = [line.rstrip() for line in cleaned.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()


def _sdp_monitor_last_snapshot() -> str | None:
    settings_path = _settings_path()
    if not settings_path.exists():
        return None
    try:
        stdout, _stderr, returncode = run_sdp_command(
            ["sdp-cli", "monitor", "--last"],
            project_root=PROJECT_ROOT,
            env=_sdp_cli_env(),
            timeout_s=15,
        )
    except Exception:
        return None
    if returncode != 0:
        return None
    snapshot = _normalize_monitor_snapshot(stdout)
    if "SDP Monitor" not in snapshot:
        return None
    return snapshot[:3500]


def _latest_completion_gate_snapshot() -> dict[str, str] | None:
    db_path = _queue_db_path()
    if not db_path.exists():
        return None

    con = sqlite3.connect(db_path)
    try:
        if not _table_exists(con, "completion_gate_reports"):
            return None
        row = con.execute(
            """
            SELECT COALESCE(status, ''), COALESCE(summary, ''), COALESCE(created_at, '')
            FROM completion_gate_reports
            ORDER BY created_at DESC, report_id DESC
            LIMIT 1
            """
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()

    if row is None:
        return None

    return {
        "status": str(row[0] or ""),
        "summary": str(row[1] or ""),
        "created_at": str(row[2] or ""),
    }


def _latest_completed_run_snapshot() -> dict[str, str] | None:
    db_path = _queue_db_path()
    if not db_path.exists():
        return None

    con = sqlite3.connect(db_path)
    try:
        if not _table_exists(con, "task_runs"):
            return None
        row = con.execute(
            """
            SELECT
                COALESCE(task_id, ''),
                COALESCE(lead_agent, ''),
                COALESCE(verify_agent, ''),
                COALESCE(verdict, ''),
                COALESCE(completed_at, '')
            FROM task_runs
            WHERE TRIM(COALESCE(completed_at, '')) != ''
            ORDER BY completed_at DESC, started_at DESC, rowid DESC
            LIMIT 1
            """
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()

    if row is None:
        return None

    return {
        "task_id": str(row[0] or ""),
        "lead_agent": str(row[1] or ""),
        "verify_agent": str(row[2] or ""),
        "verdict": str(row[3] or ""),
        "completed_at": str(row[4] or ""),
    }


def _provider_monitor_line() -> str:
    provider_status = quota_monitor.get_provider_status()
    parts = []
    for agent in ("claude", "codex", "gemini"):
        info = provider_status.get(PROVIDERS[agent], {"status": "unknown", "headroom": 0.0})
        headroom = info.get("headroom", 0.0)
        if not isinstance(headroom, (int, float, str)):
            headroom = 0.0
        parts.append(f"{agent} {float(headroom):.0%} {info.get('status', 'unknown')}")
    return "Providers: " + " · ".join(parts)


def _selector_disabled_agents() -> set[str]:
    settings_path = _settings_path()
    if not settings_path.exists():
        return set()
    try:
        with settings_path.open("rb") as fh:
            settings = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return set()

    scope = settings
    nested = settings.get("sdp")
    if isinstance(nested, dict):
        scope = nested

    disabled: set[str] = set()
    for agent in ("claude", "codex", "gemini"):
        raw_value = scope.get(f"selector_{agent}_remaining_tokens")
        if raw_value is None:
            continue
        try:
            remaining = float(raw_value)
        except (TypeError, ValueError):
            continue
        if remaining <= 0:
            disabled.add(agent)
    return disabled


def _format_elapsed(started_at: str) -> str:
    if not started_at:
        return "unknown"
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return "unknown"
    elapsed = max(0, int((datetime.now(timezone.utc) - started).total_seconds()))
    minutes, seconds = divmod(elapsed, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _merge_rollups(batches: tuple[str, ...], batch_rollups: dict[str, dict[str, int]]) -> dict[str, int]:
    merged = _empty_rollup()
    for batch in batches:
        bucket = batch_rollups.get(batch)
        if not bucket:
            continue
        for key, value in bucket.items():
            merged[key] = merged.get(key, 0) + int(value)
    return merged


def _label_status(summary: dict[str, int]) -> str:
    total = summary.get("total", 0)
    complete = summary.get("complete", 0)
    running = summary.get("running", 0)
    blocked = summary.get("blocked", 0)
    needs_attention = summary.get("needs_attention", 0)
    pending = summary.get("pending", 0)
    needs_split = summary.get("needs_split", 0)
    frozen = summary.get("frozen", 0)
    skipped = summary.get("skipped", 0)
    active_blockers = blocked + needs_attention + needs_split

    if total == 0:
        if frozen:
            return "frozen"
        if skipped:
            return "decomposed"
        return "not loaded"
    if running:
        return "running"
    if complete == total:
        return "done"
    if active_blockers and pending == 0:
        return "blocked"
    if active_blockers:
        return "partially blocked"
    if complete:
        pct = int(round((complete / total) * 100))
        return f"{pct}% done"
    return "queued"


def _stage_detail(summary: dict[str, int]) -> str:
    total = summary.get("total", 0)
    if total:
        return f"{summary.get('complete', 0)}/{total}"

    zero_parts = []
    frozen = summary.get("frozen", 0)
    skipped = summary.get("skipped", 0)
    if frozen:
        zero_parts.append(f"{frozen} frozen")
    if skipped:
        zero_parts.append(f"{skipped} skipped")
    return ", ".join(zero_parts) if zero_parts else "not loaded"


def format_prd_status() -> str:
    """Return the ordered PRD roadmap summary for Telegram."""
    batch_rollups = _batch_rollups()
    roadmap, completed_earlier = _load_prd_roadmap()
    lines = ["🗺️ PRD Roadmap"]

    for idx, (label, batches) in enumerate(roadmap, start=1):
        summary = _merge_rollups(batches, batch_rollups)
        status = _label_status(summary)
        total = summary.get("total", 0)
        running = summary.get("running", 0)
        pending = summary.get("pending", 0)
        needs_split = summary.get("needs_split", 0)
        blocked = summary.get("blocked", 0)
        needs_attention = summary.get("needs_attention", 0)
        skipped = summary.get("skipped", 0)
        frozen = summary.get("frozen", 0)
        detail = _stage_detail(summary)
        suffix_parts = []
        if running:
            suffix_parts.append(f"{running} running")
        if pending:
            suffix_parts.append(f"{pending} pending")
        if needs_split:
            suffix_parts.append(f"{needs_split} needs split")
        if blocked:
            suffix_parts.append(f"{blocked} blocked")
        if needs_attention:
            suffix_parts.append(f"{needs_attention} needs attention")
        if skipped and total:
            suffix_parts.append(f"{skipped} skipped")
        if frozen and total:
            suffix_parts.append(f"{frozen} frozen")
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        lines.append(f"{idx}. {label} — {status} [{detail}]{suffix}")

    completed = []
    for label, batches in completed_earlier:
        summary = _merge_rollups(batches, batch_rollups)
        if summary.get("total", 0) and summary.get("complete", 0) == summary.get("total", 0):
            completed.append(label)
    if completed:
        lines.append("")
        lines.append("Completed Earlier: " + ", ".join(completed))

    return "\n".join(lines)[:3500]


def format_monitor_status() -> str:
    """Return a compact live queue monitor summary for Telegram."""
    preferred_snapshot = _sdp_monitor_last_snapshot()
    if preferred_snapshot:
        return preferred_snapshot

    if not _queue_db_exists():
        return "📡 SDP Monitor\nQueue DB unavailable."

    counts = _root_queue_counts()
    total = counts["total"]
    complete = counts["complete"]
    pending = counts["pending"]
    needs_split = counts["needs_split"]
    blocked = counts["blocked"]
    needs_attention = counts["needs_attention"]
    running = counts["running"]
    skipped = counts["skipped"]
    frozen = counts["frozen"]
    percent = int(round((complete / total) * 100)) if total else 0
    runner_state = _runner_service_state()
    active = _active_task_snapshot()
    if runner_state != "active":
        active = None

    lines = ["📡 SDP Monitor"]
    lines.append(f"Progress: {complete}/{total} complete ({percent}%)")
    queue_parts = [f"{pending} pending"]
    if needs_split:
        queue_parts.append(f"{needs_split} needs split")
    queue_parts.extend([f"{blocked} blocked", f"{running} running"])
    if needs_attention:
        queue_parts.append(f"{needs_attention} needs attention")
    if skipped:
        queue_parts.append(f"{skipped} skipped")
    if frozen:
        queue_parts.append(f"{frozen} frozen")
    lines.append("Queue: " + ", ".join(queue_parts))
    lines.append(f"Runner: {runner_state}")
    if active is None:
        lines.append("Current: idle")
    else:
        pair = " → ".join(agent for agent in (active["lead_agent"], active["verify_agent"]) if agent) or "pair unknown"
        current = active["task_id"]
        if active["parent_task_id"]:
            current += f" (child of {active['parent_task_id']})"
        lines.append(f"Current: {current}")
        lines.append(f"Pair: {pair}")
        lines.append(f"Elapsed: {_format_elapsed(active['started_at'])}")
    drift = _queue_state_drift()
    drift_parts = []
    if drift["running_without_open"]:
        drift_parts.append(f"{drift['running_without_open']} running without open run")
    if drift["stale_open_runs"]:
        drift_parts.append(f"{drift['stale_open_runs']} stale open runs")
    if drift["duplicate_open_runs"]:
        drift_parts.append(f"{drift['duplicate_open_runs']} duplicate open-run groups")
    if drift_parts:
        lines.append("State: drift — " + ", ".join(drift_parts))
    gate = _latest_completion_gate_snapshot()
    if gate is not None:
        gate_parts = [gate["status"] or "unknown"]
        if gate["summary"]:
            gate_parts.append(_truncate_summary(gate["summary"]))
        lines.append("Gate: " + " · ".join(gate_parts))
    recent = _latest_completed_run_snapshot()
    if recent is not None:
        recent_parts = [recent["task_id"]]
        if recent["verdict"]:
            recent_parts.append(recent["verdict"])
        pair = "→".join(
            agent for agent in (recent["lead_agent"], recent["verify_agent"]) if agent
        )
        if pair:
            recent_parts.append(pair)
        lines.append("Recent: " + " · ".join(recent_parts))
    lines.append(_provider_monitor_line())
    all_agents = ("claude", "codex", "gemini")
    quota_available = set(_available_agents(list(all_agents)))
    selector_disabled = _selector_disabled_agents()
    available = [agent for agent in all_agents if agent in quota_available and agent not in selector_disabled]
    if not available and quota_available:
        available = [agent for agent in all_agents if agent in quota_available]
    exclusion_reasons: dict[str, list[str]] = {agent: [] for agent in all_agents}
    for agent in all_agents:
        if agent not in quota_available:
            exclusion_reasons[agent].append("quota")
        if agent in selector_disabled:
            exclusion_reasons[agent].append("selector")
    excluded = [
        f"{agent} ({', '.join(exclusion_reasons[agent])})"
        for agent in all_agents
        if exclusion_reasons[agent]
    ]
    if available:
        agent_line = "Available: " + ", ".join(available)
        if excluded:
            agent_line += " | Excluded: " + ", ".join(excluded)
        lines.append(agent_line)
    else:
        agent_line = "Available: none"
        if excluded:
            agent_line += " | Excluded: " + ", ".join(excluded)
        lines.append(agent_line)
    return "\n".join(lines)[:1200]


def format_quota_status() -> str:
    """Return a compact provider quota summary for Telegram."""
    provider_status = quota_monitor.get_provider_status()
    icon_map = {
        "healthy": "🟢",
        "warn": "🟡",
        "degraded": "🟠",
        "paused": "🔴",
        "error": "⚪️",
    }
    lines = ["📊 Provider Quota"]
    for provider in ("google", "openai", "anthropic"):
        info = provider_status.get(provider, {"status": "healthy", "headroom": 1.0})
        headroom = info.get("headroom", 1.0)
        if not isinstance(headroom, (int, float, str)):
            headroom = 1.0
        lines.append(
            f"{icon_map.get(str(info.get('status', 'healthy')), '⚪️')} {provider}: "
            f"{float(headroom):.0%} headroom ({info.get('status', 'healthy')})"
        )
    active = _available_agents(["claude", "codex", "gemini"])
    excluded = [agent for agent in ("claude", "codex", "gemini") if agent not in active]
    if active:
        lines.append(
            "Active: " + ", ".join(
                f"{agent} ({provider_status.get(PROVIDERS[agent], {}).get('status', 'healthy')})"
                for agent in active
            )
        )
    if excluded:
        lines.append(
            "Excluded: " + ", ".join(
                f"{agent} ({provider_status.get(PROVIDERS[agent], {}).get('status', 'unknown')})"
                for agent in excluded
            )
        )
    text = "\n".join(lines)
    return text[:300]


def _heartbeat_slot_key(now_local: datetime) -> str | None:
    if now_local.minute not in {0, 30}:
        return None
    return now_local.strftime("%Y-%m-%d-%H") + f"-{now_local.minute:02d}"


def _heartbeat_gallery_url() -> str | None:
    for key in ("CYPHERCLAW_GALLERY_URL", "GALLERY_URL"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None


def _safe_ollama_health() -> dict[str, object]:
    try:
        return ollama_health()
    except Exception:
        return {"healthy": False, "instances": []}


def status_snapshot() -> dict[str, object]:
    """Return the shared daemon status snapshot used by Telegram built-ins."""
    running = [task for task in state.tasks.values() if task["status"] == "running"]
    enabled_schedules = [schedule for schedule in state.schedules if schedule.get("enabled", True)]
    return {
        "memory": len(state.conversation),
        "tasks": len(running),
        "schedules": len(enabled_schedules),
        "artifacts": len(list_artifacts()),
        "ollama": _safe_ollama_health(),
    }


def format_half_hour_heartbeat(now_local: datetime | None = None) -> tuple[str, dict[str, object]]:
    """Return the compact half-hour heartbeat message plus observatory payload."""
    current_time = now_local or datetime.now()

    from server_health import check_health

    health = check_health()
    checks = health.get("checks", {})
    counts = _root_queue_counts()
    total = counts["total"]
    complete = counts["complete"]
    pending = counts["pending"]
    needs_split = counts["needs_split"]
    blocked = counts["blocked"]
    running = counts["running"]
    skipped = counts["skipped"]
    frozen = counts["frozen"]
    percent = int(round((complete / total) * 100)) if total else 0
    available_agents = _available_agents(["claude", "codex", "gemini"])
    pet_section = CypherClawArt.pet_xp_summary(pet_manager.pets)
    gallery_url = _heartbeat_gallery_url()
    ollama = _safe_ollama_health()

    lines = [f"💓 CypherClaw Heartbeat · {current_time.strftime('%I:%M %p').lstrip('0')}"]
    lines.append(f"⏱ Uptime: {checks.get('uptime', '?')}")
    lines.append(f"💽 I/O: {checks.get('io_wait', '?')}")
    lines.append(f"🧠 Memory: {checks.get('memory', '?')}")
    lines.append(f"⚡ Load: {checks.get('load', '?')}")
    agent_summary = ", ".join(available_agents) if available_agents else "none"
    lines.append(f"🤖 Agents: {len(available_agents)}/3 available ({agent_summary})")
    lines.append(
        f"📡 SDP: {complete}/{total} complete ({percent}%) · "
        f"{pending} pending"
        + (f" · {needs_split} needs split" if needs_split else "")
        + f" · {blocked} blocked · {running} running"
        + (f" · {frozen} frozen" if frozen else "")
    )
    if skipped:
        lines.append(f"🪓 Split parents: {skipped}")

    # Ollama summary
    ollama_parts: list[str] = []
    for inst in ollama.get("instances", []):
        name = inst.get("socket", "?")
        if inst.get("healthy"):
            models = ", ".join(inst.get("models", [])) or "no models"
            latency = inst.get("latency_ms")
            lat_str = f"{latency:.0f}ms" if latency is not None else "?"
            ollama_parts.append(f"{name} ok({lat_str}) {models}")
        else:
            ollama_parts.append(f"{name} down")
    if ollama_parts:
        healthy_tag = "up" if ollama.get("healthy") else "down"
        lines.append(f"🦙 Ollama ({healthy_tag}): {' · '.join(ollama_parts)}")
    else:
        lines.append("🦙 Ollama: unavailable")

    lines.append("")
    lines.append(pet_section)
    if gallery_url:
        lines.append("")
        lines.append(f"🖼 Gallery: {gallery_url}")

    payload = {
        "slot": _heartbeat_slot_key(current_time) or current_time.isoformat(),
        "complete": complete,
        "total": total,
        "pending": pending,
        "needs_split": needs_split,
        "blocked": blocked,
        "running": running,
        "skipped": skipped,
        "frozen": frozen,
        "percent": percent,
        "available_agents": list(available_agents),
        "agent_count": len(available_agents),
        "uptime": str(checks.get("uptime", "?")),
        "io_wait": str(checks.get("io_wait", "?")),
        "memory": str(checks.get("memory", "?")),
        "load": str(checks.get("load", "?")),
        "gallery_url": gallery_url or "",
        "ollama": ollama,
    }
    return "\n".join(lines)[:3500], payload


def handle_builtin(text: str) -> bool:
    """Handle built-in slash commands. Returns True if handled."""
    parts = text.strip().split()
    if not parts:
        return False
    cmd = parts[0].lower()
    args = parts[1:]

    if cmd == "/help":
        tg_send(_art.help_menu(BUILTIN_COMMANDS))
        return True

    if cmd == "/status":
        snapshot = status_snapshot()
        tg_send(
            _art.status_display(
                int(snapshot["memory"]),
                int(snapshot["tasks"]),
                int(snapshot["schedules"]),
                int(snapshot["artifacts"]),
                pets=pet_manager.pets,
                ollama=snapshot["ollama"],
            )
        )
        return True

    if cmd == "/local":
        snapshot = status_snapshot()
        tg_send(_art.local_status_display(snapshot.get("ollama")))
        return True

    if cmd == "/quota":
        tg_send(format_quota_status())
        return True

    if cmd == "/monitor":
        tg_send(format_monitor_status())
        return True

    if cmd == "/prd":
        tg_send(format_prd_status())
        return True

    if cmd == "/tasks":
        tg_send(format_tasks_status(args))
        return True

    if cmd == "/schedules":
        if not state.schedules:
            tg_send("No scheduled tasks.")
            return True
        lines = []
        for s in state.schedules:
            icon = "🟢" if s.get("enabled", True) else "⏸️"
            mins = s["interval_s"] // 60
            lines.append(f"{icon} `{s['name']}` every {mins}m: `{s['command'][:60]}`")
        tg_send("\n".join(lines))
        return True

    if cmd == "/workspace":
        artifacts = list_artifacts()
        if artifacts:
            tg_send("📁 Workspace:\n" + "\n".join(f"  • {a}" for a in artifacts))
        else:
            tg_send("📁 Workspace is empty.")
        return True

    if cmd == "/art":
        prompt = text[5:].strip() or "cypherclaw crab"
        tg_send(f"🎨 Generating: {prompt}")
        output = run_agent(_best_available_agent(), f"Using only plain text ASCII characters and a few emoji, create a small piece of art (max 20 lines, max 30 chars wide) depicting: {prompt}. Output ONLY the art, nothing else.", task_label=f"art: {prompt}")
        tg_send(output)
        return True

    if cmd in ("/pets", "/pet"):
        tg_send(pet_manager.status_summary())
        return True

    if cmd == "/feed":
        agent = parts[1].lower() if len(parts) > 1 else "cypherclaw"
        if agent not in pet_manager.AGENTS:
            tg_send(f"Unknown pet: {agent}. Options: {', '.join(pet_manager.AGENTS)}")
            return True
        with pet_manager._lock:
            pet = pet_manager.get(agent)
            pet.feed()
            pet_manager._save()
        tg_send(f"🍖 Fed {agent}! Hunger reset, mood boosted.\n{pet.status_line()}")
        return True

    if cmd == "/play":
        parts = text.strip().split()
        agent = parts[1].lower() if len(parts) > 1 else "cypherclaw"
        if agent not in pet_manager.AGENTS:
            tg_send(f"Unknown pet: {agent}. Options: {', '.join(pet_manager.AGENTS)}")
            return True
        with pet_manager._lock:
            pet = pet_manager.get(agent)
            pet.play()
            pet_manager._save()
        tg_send(f"🎮 Played with {agent}! Mood boosted, energy spent.\n{pet.status_line()}")
        return True

    if cmd == "/research":
        topic = text[len("/research"):].strip()
        if not topic:
            tg_send("Usage: /research <topic>\nExample: /research compare Redis vs Memcached for session caching")
            return True
        # Determine scope from flags
        scope = "auto"
        for flag in ("--quick", "--medium", "--deep"):
            if flag in topic:
                scope = flag[2:]
                topic = topic.replace(flag, "").strip()
        tg_send(f"🔬 Starting research: {topic[:80]}...")
        try:
            researcher = get_researcher()
            result = researcher.research(topic, scope=scope)
            # Researcher's send_fn already handles progress messages
            if len(result.summary) > 3500:
                tg_send(result.summary[:2000] + "\n\n📄 Full report saved to workspace.")
            else:
                tg_send(result.summary)
            # Send full report as file if substantial
            if result.full_report and len(result.full_report) > 2500:
                report_name = f"research_{int(time.time())}.md"
                save_artifact(report_name, result.full_report)
                tg_send_file(str(WORKSPACE_DIR / report_name), f"🔬 Research: {topic[:50]}")
            state.add_message("assistant", f"[research] {result.summary[:200]}")
        except Exception as e:
            tg_send(f"❌ Research error: {e}")
        return True

    if cmd == "/ldp":
        tg_send("\U0001f3e0 Fetching LifeImprover status...")
        try:
            summary = li_bridge.telegram_summary()
            tg_send(summary)
        except Exception as e:
            tg_send(f"\u274c LifeImprover error: {e}")
        return True

    if cmd == "/health":
        try:
            from server_health import check_health, auto_maintain, telegram_report
            health = check_health()
            actions = auto_maintain()
            tg_send(telegram_report(health, actions))
        except Exception as e:
            tg_send(f"\u274c Health check error: {e}")
        return True

    if cmd == "/promptclaw":
        args = text[len("/promptclaw"):].strip()
        if not args:
            tg_send("Usage: /promptclaw <task description>\nRuns the task through PromptClaw's orchestrator (routing \u2192 lead \u2192 verify)")
            return True
        # Write task to temp file
        task_file = WORKSPACE_DIR / f"promptclaw_task_{int(time.time())}.md"
        task_file.write_text(args)
        tg_send("\U0001f980 Running through PromptClaw orchestrator...")
        try:
            promptclaw_result = subprocess.run(
                ["promptclaw", "run", ".", "--task-file", str(task_file)],
                capture_output=True, text=True, timeout=MAX_AGENT_TIMEOUT,
                cwd=str(PROJECT_ROOT),
                env=_child_process_env({"PATH": f"{Path.home() / '.local' / 'bin'}:/usr/local/bin:/usr/bin:/bin"}),
            )
            output = promptclaw_result.stdout.strip()
            if promptclaw_result.returncode == 0:
                tg_send(f"\u2705 PromptClaw complete:\n{output[:2000]}")
            else:
                tg_send(f"\u274c PromptClaw failed:\n{promptclaw_result.stderr[:500]}")
        except subprocess.TimeoutExpired:
            tg_send("\u23f1\ufe0f PromptClaw timed out")
        except Exception as e:
            tg_send(f"\u274c Error: {e}")
        return True

    if cmd == "/retro":
        tg_send("📋 Generating retro...")
        try:
            retro = reviewer.weekly_retro()
            pet_section = CypherClawArt.pet_xp_summary(pet_manager.pets)
            tg_send(f"{retro}\n\n{pet_section}")
        except Exception as e:
            tg_send(f"❌ Retro error: {e}")
        return True

    if cmd == "/brief":
        tg_send("📊 Generating brief...")
        try:
            brief = reviewer.daily_brief()
            pet_section = CypherClawArt.pet_xp_summary(pet_manager.pets)
            tg_send(f"{brief}\n\n{pet_section}")
        except Exception as e:
            tg_send(f"❌ Brief error: {e}")
        return True

    if cmd == "/stats":
        stats_lines = ["\U0001f4ca Agent Performance (7 days)\n"]
        for agent_name in ("claude", "codex", "gemini"):
            s = observatory.get_agent_stats(agent_name, 7)
            if s and agent_name in s and s[agent_name]["total"] > 0:
                a = s[agent_name]
                rate = a["successes"] / a["total"] if a["total"] else 0
                stats_lines.append(
                    f"{agent_name}: {rate:.0%} success, {a['total']} tasks, avg {a['avg_duration']/1000:.1f}s"
                )
        stats_lines.append("\n\U0001f3af Routing accuracy (7d): {:.0%}".format(observatory.get_routing_accuracy(7)))
        tg_send("\n".join(stats_lines))
        return True

    return False


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def poll_loop() -> None:
    log.info("CypherClaw v2 daemon started")

    # Kill any orphaned agent processes from previous crashes
    _kill_orphan_agents()
    quota_monitor.start()

    tg_send(_art.startup_banner(pets=pet_manager.pets))

    scheduler = Scheduler()
    scheduler.start()
    last_msg_time = time.time()
    pets_sleeping = False

    while True:
        try:
            # Notify systemd watchdog that we are alive
            _notify_watchdog()

            offset = state.last_update_id + 1
            result = tg_api("getUpdates", {"offset": offset, "timeout": POLL_INTERVAL})

            for update in result.get("result", []):
                state.last_update_id = update["update_id"]
                state.save()

                msg = update.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "").strip()

                if chat_id != CHAT_ID or not text:
                    continue

                last_msg_time = time.time()
                if pets_sleeping:
                    pet_manager.wake_all()
                    pets_sleeping = False

                log.info("Message: %s", text[:100])
                state.add_message("user", text)
                observatory.record('user_message', data={'text': text[:200]})

                # Handle confirmation responses
                if state.pending_confirm:
                    if text.lower() in ("yes", "y", "go", "do it"):
                        remaining = state.pending_confirm.get("remaining_steps", [])
                        state.pending_confirm = None
                        state.save()
                        tg_send("✅ Confirmed.")
                        if remaining:
                            execute_plan(remaining)
                        continue
                    elif text.lower() in ("no", "n", "cancel", "stop"):
                        state.pending_confirm = None
                        state.save()
                        tg_send("❌ Cancelled.")
                        continue
                    # Not a yes/no — clear pending and process as new message

                state.pending_confirm = None

                # Built-in commands
                if text.startswith("/") and handle_builtin(text):
                    continue

                # Check fast path first (no animation needed)
                fast = fast_route(text)
                if fast is not None:
                    steps = fast
                    pet_manager.on_task_end("cypherclaw", success=True, duration_s=0)
                    pet_manager.schedule_idle("cypherclaw")
                else:
                    # Send thinking indicator immediately (with Markdown for code blocks)
                    claw_portrait = pet_manager.get("cypherclaw").get_portrait()
                    indicator_text = _art.processing_indicator(pet_portrait=claw_portrait)
                    indicator_data: dict = {"chat_id": CHAT_ID, "text": indicator_text}
                    if "```" in indicator_text:
                        indicator_data["parse_mode"] = "Markdown"
                    status_r = tg_api("sendMessage", indicator_data)
                    if not status_r.get("ok") and "parse_mode" in indicator_data:
                        del indicator_data["parse_mode"]
                        status_r = tg_api("sendMessage", indicator_data)
                    status_msg_id = status_r.get("result", {}).get("message_id")
                    log.info("Thinking indicator sent (msg_id=%s)", status_msg_id)

                    # Route through orchestrator
                    steps = route_message(text)

                    # Delete thinking indicator
                    if status_msg_id:
                        tg_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": status_msg_id})
                        log.info("Thinking indicator deleted")

                # Execute in a thread so the poll loop stays responsive
                def _safe_execute(steps_to_run):
                    try:
                        execute_plan(steps_to_run)
                    except Exception as exc:
                        log.exception("execute_plan thread crashed")
                        try:
                            tg_send(f"❌ Task crashed: {exc}\n\nI'm still running — try again or rephrase.")
                        except Exception:
                            pass

                threading.Thread(
                    target=_safe_execute, args=(steps,),
                    daemon=True, name="plan-exec",
                ).start()

            if not pets_sleeping and (time.time() - last_msg_time) > 300:
                pet_manager.on_sleep()
                pets_sleeping = True

        except KeyboardInterrupt:
            log.info("Shutting down")
            tg_send(_art.shutdown_banner())
            quota_monitor.stop()
            scheduler.stop()
            break
        except Exception:
            log.exception("Poll loop error")
            time.sleep(10)


# ---------------------------------------------------------------------------
# launchd management
# ---------------------------------------------------------------------------

PLIST_CONTENT = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{__file__}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{PROJECT_ROOT}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{LOG_FILE}</string>
    <key>StandardErrorPath</key>
    <string>{LOG_FILE}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{Path.home()}/.local/bin</string>
    </dict>
</dict>
</plist>
"""


def install_service():
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(PLIST_CONTENT)
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST_PATH)],
                   capture_output=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST_PATH)],
                   check=True)
    print(f"✅ Installed: {PLIST_LABEL}")
    print(f"   Log: {LOG_FILE}")


def uninstall_service():
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST_PATH)],
                   capture_output=True)
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
    print(f"✅ Removed: {PLIST_LABEL}")


def check_status():
    system = platform.system().lower()
    if system == "darwin":
        try:
            result = subprocess.run(
                ["launchctl", "print", f"gui/{os.getuid()}/{PLIST_LABEL}"],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            print("🟡 launchctl unavailable")
            return
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "pid" in line.lower():
                    print(f"🟢 Running — {line.strip()}")
                    return
            print("🟢 Running")
        else:
            print("🔴 Not running")
        return

    if system == "linux":
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "cypherclaw.service"],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            print("🟡 systemctl unavailable")
            return
        status = (result.stdout or "").strip()
        if status == "active":
            print("🟢 Running")
        else:
            print("🔴 Not running")
        return

    print(f"🟡 Status unavailable on {platform.system()}")


def main():
    parser = argparse.ArgumentParser(description="CypherClaw v2 daemon")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.install:
        install_service()
    elif args.uninstall:
        uninstall_service()
    elif args.status:
        check_status()
    else:
        def _handle_shutdown(*_args):
            quota_monitor.stop()
            sys.exit(0)

        signal.signal(signal.SIGTERM, _handle_shutdown)
        try:
            poll_loop()
        finally:
            quota_monitor.stop()


if __name__ == "__main__":
    main()
