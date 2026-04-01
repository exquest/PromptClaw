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
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# GlyphWeave art system
TOOLS_DIR_EARLY = Path(__file__).parent
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

TOOLS_DIR = Path(__file__).parent
STATE_FILE = TOOLS_DIR / ".daemon_state.json"
LOG_FILE = TOOLS_DIR / "cypherclaw_daemon.log"
WORKSPACE_DIR = TOOLS_DIR / "workspace"
TASKS_DIR = TOOLS_DIR / "workspace" / "tasks"

PLIST_LABEL = "com.cypherclaw.daemon"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"

PROJECT_ROOT = TOOLS_DIR.parent  # ~/Programming/PromptClaw/my-claw

# Ensure workspace exists
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
TASKS_DIR.mkdir(parents=True, exist_ok=True)

# Observatory & Healer
from observatory import Observatory
from healer import Healer, Failure

OBSERVATORY_DB = TOOLS_DIR.parent / ".promptclaw" / "observatory.db"
OBSERVATORY_DB.parent.mkdir(parents=True, exist_ok=True)
observatory = Observatory(str(OBSERVATORY_DB))

from reviewer import Reviewer
reviewer = Reviewer(observatory)

from researcher import Researcher
from lifeimprover_bridge import LifeImproverBridge
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

from agent_selector import AgentSelector, PROVIDERS
agent_selector = AgentSelector(
    observatory=observatory,
    quota_monitor=quota_monitor,
    state_file=TOOLS_DIR / ".agent_selector_state.json",
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
            timeout=timeout, cwd=str(PROJECT_ROOT),
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


def _available_agents(
    agents: list[str] | tuple[str, ...] | None = None,
    *,
    disabled_agents: set[str] | None = None,
) -> list[str]:
    candidates = list(agents or ["claude", "codex", "gemini"])
    disabled = set(disabled_agents or ())
    filtered = [agent for agent in candidates if agent not in disabled]
    if not filtered:
        filtered = candidates
    try:
        available = quota_monitor.get_available_agents(filtered)
        if available:
            return available
    except Exception:
        pass
    return filtered


def _best_available_agent(
    agents: list[str] | tuple[str, ...] | None = None,
    *,
    disabled_agents: set[str] | None = None,
) -> str:
    available = _available_agents(agents, disabled_agents=disabled_agents)
    return available[0] if available else "gemini"


def _build_agent_command(agent: str, prompt: str) -> tuple[list[str], dict[str, str], bool]:
    env = os.environ.copy()
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

            # ---------------------------------------------------------------
            # Time-based review triggers
            # ---------------------------------------------------------------
            import datetime as _dt
            now_local = _dt.datetime.now()
            today_key = now_local.strftime("%Y-%m-%d")

            # Daily rollup (needed for aggregate stats)
            if not self._sent_today.get("daily_rollup") == today_key:
                self._sent_today["daily_rollup"] = today_key
                try:
                    observatory.rollup_daily()
                except Exception:
                    log.exception("Daily rollup error")

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
        route_env = os.environ.copy()
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
                        env={**os.environ, "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", "")},
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

                sdp_env = os.environ.copy()
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
    "/quota": "Show provider quota headroom and active agents",
    "/tasks": "List background tasks",
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


def handle_builtin(text: str) -> bool:
    """Handle built-in slash commands. Returns True if handled."""
    cmd = text.strip().split()[0].lower()

    if cmd == "/help":
        tg_send(_art.help_menu(BUILTIN_COMMANDS))
        return True

    if cmd == "/status":
        running = [t for t in state.tasks.values() if t["status"] == "running"]
        scheds = [s for s in state.schedules if s.get("enabled", True)]
        n_artifacts = len(list_artifacts())
        n_convo = len(state.conversation)
        tg_send(_art.status_display(n_convo, len(running), len(scheds), n_artifacts, pets=pet_manager.pets))
        return True

    if cmd == "/quota":
        tg_send(format_quota_status())
        return True

    if cmd == "/tasks":
        if not state.tasks:
            tg_send("No tasks.")
            return True
        lines = []
        for tid, t in sorted(state.tasks.items(), key=lambda x: x[1].get("created", ""), reverse=True)[:10]:
            icon = {"running": "🔄", "done": "✅", "failed": "❌"}.get(t["status"], "❓")
            lines.append(f"{icon} `{tid}` ({t['agent']}) — {t['status']}")
        tg_send("\n".join(lines))
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
        parts = text.strip().split()
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
                env={**os.environ, "PATH": f"{Path.home() / '.local' / 'bin'}:/usr/local/bin:/usr/bin:/bin"},
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
