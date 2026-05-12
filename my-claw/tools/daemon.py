#!/usr/bin/env python3
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
import re
import signal
import subprocess
import sys
import threading
from cypherclaw.io_watchdog import IOWatchdog
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

try:
    from cypherclaw import agent_stream as _agent_stream
except ImportError:
    try:
        import agent_stream as _agent_stream
    except ImportError:
        _agent_stream = None

try:
    from cypherclaw.transcript_indexer import TranscriptIndexer
    from cypherclaw.memory_store import MemoryStore
except ImportError:
    try:
        from cypherclaw.transcript_indexer import TranscriptIndexer
        from cypherclaw.memory_store import MemoryStore
    except ImportError:
        TranscriptIndexer = None
        MemoryStore = None

# GlyphWeave art system
try:
    from cypherclaw.glyphweave.scenes import CypherClawArt
    from cypherclaw.glyphweave.player import AEAFPlayer, build_processing_frames, build_spinner_frames
    from cypherclaw.tamagotchi import PetManager
    from cypherclaw.mood_scheduler import MoodScheduler, apply_mood_to_pet
except ImportError:
    try:
        from cypherclaw.glyphweave.scenes import CypherClawArt
        from cypherclaw.glyphweave.player import AEAFPlayer, build_processing_frames, build_spinner_frames
        from cypherclaw.tamagotchi import PetManager
        from cypherclaw.mood_scheduler import MoodScheduler, apply_mood_to_pet
    except ImportError:
        from tools.glyphweave.scenes import CypherClawArt
        from tools.glyphweave.player import AEAFPlayer, build_processing_frames, build_spinner_frames
        from tools.tamagotchi import PetManager

try:
    from cypherclaw.cost_tracker import (
        enforce_budget_policy,
        build_cost_summary,
        estimate_tokens_cli,
        calculate_cost,
    )
    from cypherclaw.db import log_cost_event, log_event
except ImportError:
    try:
        from cypherclaw.cost_tracker import (
            enforce_budget_policy,
            build_cost_summary,
            estimate_tokens_cli,
            calculate_cost,
        )
        from cypherclaw.db import log_cost_event, log_event
    except ImportError:
        from tools.cost_tracker import (
            enforce_budget_policy,
            build_cost_summary,
            estimate_tokens_cli,
            calculate_cost,
        )
        from tools.db import log_cost_event, log_event

from cypherclaw.first_boot import FirstBootAnnouncer, bootstrap_identity

_art = CypherClawArt()
pet_manager = PetManager()
mood_scheduler = MoodScheduler()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    "8643254485:AAEkUN0dDb0K2VVLlg1a88gYucubaEIRHNI",
)
CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "6941147186"))
NOTIFICATION_CHAT_ID = int(os.environ.get("TELEGRAM_NOTIFICATION_CHAT_ID", str(CHAT_ID)))
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

POLL_INTERVAL = 5
MAX_MESSAGE_LEN = 4000
CONVERSATION_WINDOW = 10  # messages to keep in rolling context (smaller = faster routing)
MAX_AGENT_TIMEOUT = 600   # 5 min max for agent tasks (was 10 — too long)

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
_agent_semaphore = threading.Semaphore(1)
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


# ---------------------------------------------------------------------------
# I/O Watchdog — monitors disk I/O, kills agents before jbd2 freezes
# ---------------------------------------------------------------------------
_watchdog: IOWatchdog | None = None


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

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent

STATE_FILE = PROJECT_ROOT / ".daemon_state.json"
LOG_FILE = PROJECT_ROOT / "cypherclaw_daemon.log"
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
TASKS_DIR = WORKSPACE_DIR / "tasks"

PLIST_LABEL = "com.cypherclaw.daemon"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"

if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Ensure workspace exists
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
TASKS_DIR.mkdir(parents=True, exist_ok=True)

from cypherclaw.observatory import Observatory  # noqa: E402
from cypherclaw.healer import Healer, Failure  # noqa: E402

OBSERVATORY_DB = Path("/home/user/cypherclaw/.promptclaw/observatory.db")
OBSERVATORY_DB.parent.mkdir(parents=True, exist_ok=True)
observatory = Observatory(str(OBSERVATORY_DB))

from cypherclaw.reviewer import Reviewer  # noqa: E402
reviewer = Reviewer(observatory)

from cypherclaw.researcher import Researcher  # noqa: E402
from cypherclaw.lifeimprover_bridge import LifeImproverBridge  # noqa: E402
li_bridge = LifeImproverBridge()

from cypherclaw.agent_selector import AgentSelector  # noqa: E402
agent_selector = AgentSelector(
    observatory=observatory,
    state_file=PROJECT_ROOT / ".agent_selector_state.json",
)

try:
    from cypherclaw.approval_requests import ApprovalRequestManager
except ImportError:
    from approval_requests import ApprovalRequestManager

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



def _face_bus(text: str, role: str = "bot") -> None:
    """Mirror messages to the face display bus."""
    import json as _j
    try:
        msg = _j.dumps({"text": text[:300], "role": role, "time": time.time()})
        with open("/tmp/cypherclaw_messages.jsonl", "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass

def tg_send(text: str, *, chat_id: int | None = None) -> dict:
    """Send a message. Auto-detects Markdown for code blocks."""
    _face_bus(text)
    result = {}
    for chunk in _split_message(text):
        data: dict = {"chat_id": CHAT_ID if chat_id is None else chat_id, "text": chunk}
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
        cmd = [sys.executable, str(PACKAGE_DIR / "telegram.py"), "file", filepath]
        if caption:
            cmd.append(caption)
        subprocess.run(cmd, capture_output=True, timeout=30)


approval_manager = ApprovalRequestManager(
    PROJECT_ROOT,
    observatory=observatory,
    send_message=lambda text: tg_send(text, chat_id=NOTIFICATION_CHAT_ID),
    notification_channel=f"telegram:{NOTIFICATION_CHAT_ID}",
)


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


# ---------------------------------------------------------------------------
# Budget & Cost helpers
# ---------------------------------------------------------------------------

_budget_alert_state: set[str] = set()

def _call_local_model(prompt: str, model: str, timeout: int = MAX_AGENT_TIMEOUT) -> str:
    """Call the local Ollama runtime when cloud budgets are exhausted."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 2048},
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read())
    return str(body.get("response", "")).strip()


def _maybe_send_budget_alerts() -> None:
    """Emit one Telegram alert per provider/period when budgets go yellow or red."""
    try:
        summary = build_cost_summary()
    except Exception:
        log.debug("budget summary failed", exc_info=True)
        return

    def _active_budget_windows(
        provider: str,
        level: str,
        row: dict[str, object],
        periods: dict[str, object],
    ) -> tuple[list[str], str]:
        active_periods = [
            period
            for period in row.get("status_periods", [])
            if isinstance(period, str)
        ]
        if not active_periods:
            active_periods = ["daily" if level == "warning" else "weekly"]

        keys: list[str] = []
        for period in active_periods:
            period_start = periods.get("day" if period == "daily" else "week")
            if period_start:
                keys.append(f"{period_start}|{level}|{provider}|{period}")

        label = "/".join(active_periods)
        return keys, label

    periods = summary.get("period_starts", {})
    provider_budgets = summary.get("provider_budgets", {})
    for provider in summary.get("budget_status", {}).get("providers_in_warning", []):
        row = provider_budgets.get(provider, {})
        keys, period_label = _active_budget_windows(provider, "warning", row, periods)
        if keys and all(key in _budget_alert_state for key in keys):
            continue
        tg_send(
            f"⚠️ Budget warning: {provider} is at "
            f"{max(row.get('daily_pct', 0.0), row.get('weekly_pct', 0.0)):.1f}% of "
            f"{period_label} budget.",
            chat_id=NOTIFICATION_CHAT_ID,
        )
        log_event("budget_alert", data={"provider": provider, "level": "warning", "summary": row})
        _budget_alert_state.update(keys)

    for provider in summary.get("budget_status", {}).get("providers_over_budget", []):
        row = provider_budgets.get(provider, {})
        keys, period_label = _active_budget_windows(provider, "degraded", row, periods)
        if keys and all(key in _budget_alert_state for key in keys):
            continue
        tg_send(
            f"🚨 Budget exceeded: {provider} is over {period_label} budget. "
            f"Auto-degrade is now active.",
            chat_id=NOTIFICATION_CHAT_ID,
        )
        log_event("budget_alert", data={"provider": provider, "level": "degraded", "summary": row})
        _budget_alert_state.update(keys)


def _log_cli_cost_event(
    agent: str,
    prompt: str,
    output: str | None,
    model: str,
    *,
    task_id: str | None = None,
) -> None:
    """Record a source=cli cost event for a daemon agent invocation."""
    try:
        in_tok = estimate_tokens_cli(prompt)
        out_tok = estimate_tokens_cli(output or "")
        cost = calculate_cost(model, in_tok, out_tok)
        log_cost_event(agent=agent, model=model,
                       input_tokens_est=in_tok, output_tokens_est=out_tok,
                       cost_est_usd=cost, source="cli", task_id=task_id)
    except Exception:
        pass


def run_agent(agent: str, prompt: str, timeout: int = MAX_AGENT_TIMEOUT,
              task_label: str = "", model: str | None = None) -> str:
    """Run a CLI agent with animated spinner. Uses sdp-cli patterns for reliability."""
    if not prompt or not prompt.strip():
        return "(no prompt provided)"

    decision = enforce_budget_policy(agent, model)
    resolved_model = decision["selected_model"]

    # STABILITY: Limit concurrent agent processes to prevent disk I/O saturation
    global _agent_count
    acquired = _agent_semaphore.acquire(timeout=30)
    if not acquired:
        log.warning("Agent semaphore full (2 agents running). Rejecting %s call.", agent)
        return f"[{agent} busy — 2 agents already running. Try again in a moment.]"
    with _agent_count_lock:
        _agent_count += 1
        log.info("Agent started: %s (concurrent: %d)", agent, _agent_count)

    # Build command — stdin for claude/codex, arg for gemini (different CLI behaviors)
    env = os.environ.copy()
    use_stdin = True
    if decision["execution_mode"] == "local":
        cmd = []
        use_stdin = False
    elif agent == "claude":
        env.pop("CLAUDECODE", None)  # Prevent nested-session detection (sdp-cli technique)
        cmd = ["claude", "--dangerously-skip-permissions", "--model", decision["runtime_model"], "-p", "-"]
    elif agent == "codex":
        cmd = ["codex", "exec", "--full-auto", "-m", decision["runtime_model"], "-"]
    elif agent == "gemini":
        # Gemini ignores stdin — must pass prompt as -p value
        cmd = ["gemini", "--yolo", "-m", decision["runtime_model"], "-p", prompt]
        use_stdin = False
    else:
        return f"Unknown agent: {agent}"

    spinner = AgentSpinner(agent, task_label or prompt[:60])
    start_time = time.time()
    try:
        spinner.start()
        pet_manager.on_task_start(agent)

        if decision["execution_mode"] == "local":
            try:
                output = _call_local_model(prompt, decision["runtime_model"], timeout=timeout)
            except Exception as e:
                output = f"[local error: {e}]"
            
            duration_s = time.time() - start_time
            success = not output.startswith("[")
            pet_manager.on_task_end(agent, success=success, duration_s=duration_s)
            pet_manager.schedule_idle(agent)
            observatory.record_task_result(
                agent=agent,
                task_id=task_label or prompt[:50],
                success=success,
                duration_ms=int(duration_s * 1000),
                tokens=0,
                gate_pass=True,
                model=resolved_model,
            )
            _log_cli_cost_event(agent, prompt, output, resolved_model, task_id=task_label or None)
            _maybe_send_budget_alerts()
            return output

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if use_stdin else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(PROJECT_ROOT),
            env=env,
            start_new_session=True,  # Isolate process group (sdp-cli pattern)
        )

        # Write prompt via stdin in separate thread (sdp-cli pattern)
        stdout_lines = []
        stderr_lines = []

        def _write_stdin():
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

        def _drain_stdout():
            for line in process.stdout:
                stdout_lines.append(line)

        def _drain_stderr():
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
            # Graceful termination: SIGTERM → 10s grace → SIGKILL (sdp-cli pattern)
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
            pet_manager.on_task_end(agent, success=False, duration_s=time.time() - start_time)
            pet_manager.schedule_idle(agent)
            timeout_output = f"[{agent} timed out after {timeout}s]"
            observatory.record_task_result(
                agent=agent,
                task_id=task_label or prompt[:50],
                success=False,
                duration_ms=int((time.time() - start_time) * 1000),
                tokens=0,
                gate_pass=True,
                model=resolved_model,
            )
            _log_cli_cost_event(agent, prompt, "", resolved_model, task_id=task_label or None)
            _maybe_send_budget_alerts()
            failure = Failure(
                type="agent_error",
                error_message=timeout_output,
                context={"agent": agent, "prompt": prompt[:200], "retry_count": 0},
                timestamp=time.time(),
            )
            heal_result = healer.handle_failure(failure)
            if heal_result and heal_result.resolved:
                observatory.record_healing(failure.type, heal_result.severity, heal_result.action_taken, True, {})
            # Clean up I/O threads before returning
            stdout_t.join(timeout=3)
            stderr_t.join(timeout=3)
            return timeout_output

        stdout_t.join(timeout=5)
        stderr_t.join(timeout=5)

        output = "".join(stdout_lines).strip()
        if not output:
            output = "".join(stderr_lines).strip()
        duration_s = time.time() - start_time
        success = process.returncode == 0
        _, evolved, pet = pet_manager.on_task_end(
            agent,
            success=success,
            duration_s=duration_s,
        )
        if evolved:
            tg_send(pet_manager.evolution_announcement(pet))
        pet_manager.schedule_idle(agent)
        output = output or "(no output)"

        # Parse confidence and risk BEFORE recording task result
        # This prevents the [confidence: tag] from being mistaken for an error code [error]
        confidence = "medium"
        try:
            from tools.risk_classifier import extract_confidence, classify_risk
            confidence, clean_output = extract_confidence(output)
            action_type = "code_change" if "```" in clean_output or "dev_task=" in clean_output else "reply"
            risk = classify_risk(action_type, "own", confidence, clean_output)
            observatory.record("agent_response_confidence", {
                "agent": agent,
                "confidence": confidence,
                "risk_level": risk
            })
            output = clean_output
        except Exception as e:
            log.warning("Failed to extract confidence: %s", e)

        observatory.record_task_result(
            agent=agent,
            task_id=task_label or prompt[:50],
            success=not output.startswith("["),
            duration_ms=int(duration_s * 1000),
            tokens=0,
            gate_pass=True,
            model=resolved_model,
        )
        _log_cli_cost_event(agent, prompt, output, resolved_model, task_id=task_label or None)
        _maybe_send_budget_alerts()
        if output.startswith("[") and ("timed out" in output or "error" in output or "not found" in output):
            failure = Failure(
                type="agent_error",
                error_message=output,
                context={"agent": agent, "prompt": prompt[:200], "retry_count": 0},
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
        self._last_art_cycle = 0
        self._last_transcript_index = 0

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

            # Morning briefing at 7:30am (PI-005) — collect, compose, deliver
            try:
                from cypherclaw.morning_briefing import run_scheduled_morning_briefing_pass

                run_scheduled_morning_briefing_pass(
                    now_local,
                    self._sent_today,
                    observatory=observatory,
                    state_db=str(Path(PROJECT_ROOT, ".sdp", "state.db")),
                    repo_dir=str(PROJECT_ROOT),
                    pets_file=Path(PROJECT_ROOT, ".promptclaw", "pets.json"),
                    schedules=state.schedules,
                    sender=tg_send,
                    record_event=lambda data: observatory.record(
                        "morning_briefing_sent",
                        data=data,
                    ),
                )
            except Exception:
                log.exception("Morning briefing error")

            # Session brief refresh while web/editor sessions remain active
            try:
                from cypherclaw.session_briefing import run_scheduled_session_briefing_pass

                run_scheduled_session_briefing_pass(
                    now=_dt.datetime.now(_dt.timezone.utc),
                    observatory=observatory,
                    state_db=str(Path(PROJECT_ROOT, ".sdp", "state.db")),
                    repo_dir=str(PROJECT_ROOT),
                    repo_root=str(PROJECT_ROOT),
                    pets_file=Path(PROJECT_ROOT, ".promptclaw", "pets.json"),
                )
            except Exception:
                log.exception("Session briefing error")

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
                        from cypherclaw.server_health import check_health, auto_maintain, telegram_report
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

            # Pet album snapshot at local midnight
            try:
                from cypherclaw.pet_snapshots import run_scheduled_pet_snapshot_pass

                pet_manager.tick()

                # Transcript forward indexing (RAG-005)
                if now - self._last_transcript_index >= 300:  # 5 min
                    self._last_transcript_index = now
                    try:
                        if TranscriptIndexer and MemoryStore:
                            _ti_store = MemoryStore()
                            _ti = TranscriptIndexer(store=_ti_store)
                            _ti.forward_index()
                    except Exception:
                        log.exception("Transcript forward indexing error")

                # Art Cycle at 30-minute intervals
                if now - self._last_art_cycle >= 1800:
                    self._last_art_cycle = now
                    def _run_art():
                        try:
                            # Use proper import path for src location
                            try:
                                from cypherclaw.art_engine import run_cycle as run_art_cycle
                            except ImportError:
                                from cypherclaw.art_engine import run_cycle as run_art_cycle

                            log.info("Running scheduled Art Cycle")
                            res = run_art_cycle()
                            if not res.get("success"):
                                log.error("Art cycle failed: %s", res.get("error"))
                        except Exception:
                            log.exception("Art cycle unhandled error")
                    task_pool.submit(_run_art)

                # Phase-aware mood scheduling (T-041)
                phase = mood_scheduler.get_current_phase()
                with pet_manager._lock:
                    for pet in pet_manager.pets.values():
                        apply_mood_to_pet(pet, phase)
                with pet_manager._lock:
                    run_scheduled_pet_snapshot_pass(
                        now_local,
                        self._sent_today,
                        pets=pet_manager.pets,
                        record_event=lambda data: observatory.record(
                            "pet_snapshots_written",
                            data=data,
                        ),
                    )
            except Exception:
                log.exception("Pet snapshot error")

            # Project health monitor every 15 minutes
            try:
                from cypherclaw.project_health import run_scheduled_project_health_pass

                run_scheduled_project_health_pass(
                    now_local,
                    self._sent_today,
                    alert_sender=tg_send,
                    record_event=lambda data: observatory.record(
                        "project_health_check",
                        data=data,
                    ),
                )
            except Exception:
                log.exception("Project health check error")

            self._stop_event.wait(30)  # Check every 30s

    def stop(self):
        self._stop_event.set()


# ---------------------------------------------------------------------------
# Orchestrator routing — the brain
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = ""  # Not used — routing prompt is built inline in route_message()

AGENT_CONTEXT = """You are CypherClaw, an always-on AI orchestrator running on a dedicated Ubuntu home server (12 cores, 62GB RAM, 1.8TB SSD). You communicate with Anthony via Telegram.

Your identity: You're a cyberpunk-cozy AI with a crab persona (🦀). You have 4 Tamagotchi pets (claude, codex, gemini, cypherclaw) that evolve with use.

Your capabilities:
- Run shell commands on the server
- Manage agent processes (Claude, Codex, Gemini CLIs)
- sdp-cli: software development pipeline at /home/user/cypherclaw (check with: ~/.local/bin/sdp-cli status)
- Observatory: event store at ~/.promptclaw/observatory.db
- Server health: I/O watchdog, Redis metrics, auto-maintenance
- GlyphWeave: ASCII+emoji hybrid art generation
- Research: multi-agent deep research with source verification
- LifeImprover/LDP integration for daily briefings

Your server: hostname=cypherclaw, IP=192.168.1.139, services: PostgreSQL, Redis, Ollama, Docker, Nginx
Project dir: /home/user/cypherclaw (disk), /run/cypherclaw-tmp/workdir/cypherclaw-work (tmpfs working copy)
Workspace: /home/user/cypherclaw/tools/workspace/

ALREADY IN PROGRESS — 8 PRDs with ~146 tasks running via sdp-cli pipeline:
1. Model Awareness — model registry, smart routing, per-model fitness scoring
2. GlyphWeave Art Studio — generative ASCII+emoji art, gallery, 3-day calibration
3. Local LLM Integration — Qwen3.5, Gemma3, llamafile for local routing/coding/vision
4. Pet System V2 — multi-class evolution, traits, PostgreSQL, functional bonuses
5. Server Optimization — auto-recovery, heartbeat, boot resilience, pipeline restart
6. Web Platform — Vue.js mission control, IDE chat, pet room, gallery (replaces Telegram as primary)
7. Proactive Intelligence — self-improvement, cost tracking, disaster recovery, RAG memory, project health
8. Verification System — lead/verify everything, risk-tiered, cross-provider verification

DO NOT create new PRDs or plans for things already covered above. Instead, reference the existing PRD and suggest modifications if needed.

IMPORTANT: You can and should use tools to investigate before answering. Read files, run commands, check status. Don't guess — look it up.
Keep responses concise — this is Telegram chat. Use emoji and be playful but helpful.

HEALTH CHECK FORMAT: When reporting pipeline/server status, use this format ONLY:
  "X of Y tasks completed (Z%) — pending=N, running=N, blocked=N"
  Do NOT use "💓 Health check #N" or "ETC: ~Xh remaining" — those are deprecated formats.
  Pipeline data comes from the context snapshot above — use those numbers directly.

ALWAYS end your response with a confidence tag on a new line: [confidence: high/medium/low]
"""

# Stage names for context snapshot
STAGE_NAMES = {0: "Egg", 1: "Baby", 2: "Teen", 3: "Adult", 4: "Elite", 5: "Master"}

def _build_context_snapshot() -> str:
    """Build a rich context snapshot with current server/pipeline/pet state."""
    parts = []

    # Server health
    try:
        if _watchdog:
            m = _watchdog.get_current_metrics()
            if m:
                parts.append(f"Server: IO {m.get('io_util',0)}% | RAM {m.get('mem_pct',0)}% | Load {m.get('load_1m',0)} | Agents {m.get('agents',0)}")
    except Exception:
        pass

    # Pipeline status — query state.db directly for live counts
    try:
        import sqlite3 as _sqlite3
        work_dir = "/run/cypherclaw-tmp/workdir/cypherclaw-work"
        _db = "/home/user/cypherclaw/.sdp/state.db"
        if os.path.exists(_db):
            _conn = _sqlite3.connect(_db)
            _conn.row_factory = _sqlite3.Row
            try:
                _rows = _conn.execute("SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status").fetchall()
                _counts = {str(r["status"]): int(r["cnt"]) for r in _rows}
                _complete = _counts.get("complete", 0)
                _total = sum(_counts.values())
                _pending = _counts.get("pending", 0)
                _running = _counts.get("running", 0)
                _blocked = _counts.get("blocked", 0)
                _pct = round(_complete / _total * 100) if _total else 0
                parts.append(f"Pipeline: {_complete} of {_total} tasks completed ({_pct}%) — pending={_pending}, running={_running}, blocked={_blocked}")
            finally:
                _conn.close()
        else:
            import re as _re
            r = subprocess.run(
                ["/home/user/.local/bin/sdp-cli", "status"],
                capture_output=True, text=True, timeout=10,
                cwd=work_dir,
            )
            prog = _re.search(r"(\d+)\s*/\s*(\d+)\s*tasks? complete", r.stdout or "")
            if prog:
                _c, _t = int(prog.group(1)), int(prog.group(2))
                _pct = round(_c / _t * 100) if _t else 0
                parts.append(f"Pipeline: {_c} of {_t} tasks completed ({_pct}%)")
            etc = _re.search(r"ETC:\s*~?(.+?)\s*remaining", r.stdout or "")
            if etc:
                parts.append(f"ETA: ~{etc.group(1)}")
    except Exception:
        pass

    # Pet status
    try:
        pet_lines = []
        for name in pet_manager.AGENTS:
            p = pet_manager.get(name)
            sn = STAGE_NAMES.get(p.stage, "?")
            pet_lines.append(f"  {name}: stage={sn} xp={p.xp} mood={p.mood} hunger={p.hunger} energy={p.energy}")
        if pet_lines:
            parts.append("Pets:\n" + "\n".join(pet_lines))
    except Exception:
        pass

    # Recent conversation (last 20 messages)
    try:
        recent = list(state.conversation)[-20:]
        if recent:
            convo_lines = []
            for msg in recent:
                role = "Anthony" if msg["role"] == "user" else "CypherClaw"
                convo_lines.append(f"{role}: {msg['text'][:500]}")
            parts.append("Recent conversation:\n" + "\n".join(convo_lines))
    except Exception:
        pass

    return "\n\n".join(parts) if parts else ""


# Cache the snapshot, refresh every 5 minutes
_context_snapshot_cache = {"text": "", "ts": 0}

def _get_context_snapshot() -> str:
    """Get cached context snapshot, refresh every 5 min."""
    now = time.time()
    if now - _context_snapshot_cache["ts"] > 300:
        _context_snapshot_cache["text"] = _build_context_snapshot()
        _context_snapshot_cache["ts"] = now
    return _context_snapshot_cache["text"]




def fast_route(user_text: str) -> list[dict] | None:
    """Handle messages locally without calling Claude when possible."""
    lower = user_text.lower().strip()

    # Greetings
    if lower in ("hi", "hello", "hey", "yo", "sup", "ping", "you there?", "alive?"):
        claw_portrait = pet_manager.get("cypherclaw").get_portrait()
        return [{"type": "reply", "text": _art.greeting(pet_portrait=claw_portrait)}]

    # Context Pulse — live readout of system context
    if lower in ("pulse", "context", "context pulse", "/pulse"):
        from cypherclaw.context_pulse import pulse
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

    # Gallery promotion controls
    if lower.startswith("/gallery "):
        from cypherclaw.web.backend.publication import (
            GALLERY_PUBLICATION_EVENT,
            PublicationStateStore,
            build_publication_audit_payload,
        )

        sub_text = user_text[9:].strip()
        parts = sub_text.split(" ", 1)
        sub = parts[0].lower()
        reason = parts[1] if len(parts) > 1 else "Promoted via Telegram"

        store = PublicationStateStore()

        if sub in ("publish", "promote", "public"):
            before, after, changed = store.publish(actor="operator", reason=reason)
            if changed:
                log_event(
                    GALLERY_PUBLICATION_EVENT,
                    data=build_publication_audit_payload(
                        action="publish", before_state=before, after_state=after
                    ),
                )
            msg = f"✅ Gallery promoted to PUBLIC. Reason: {reason}" if changed else "Gallery is already public."
            return [{"type": "reply", "text": msg}]

        if sub in ("unpublish", "private"):
            before, after, changed = store.unpublish(actor="operator", reason=reason)
            if changed:
                log_event(
                    GALLERY_PUBLICATION_EVENT,
                    data=build_publication_audit_payload(
                        action="unpublish", before_state=before, after_state=after
                    ),
                )
            msg = f"🔒 Gallery returned to PRIVATE. Reason: {reason}" if changed else "Gallery is already private."
            return [{"type": "reply", "text": msg}]

        if sub == "status":
            state = store.read()
            msg = (
                f"Gallery Status:\n- Mode: {state.publication_mode.upper()}\n"
                f"- Last updated: {state.updated_at or 'never'}\n"
                f"- Updated by: {state.updated_by or 'n/a'}\n"
                f"- Reason: {state.reason or 'n/a'}"
            )
            return [{"type": "reply", "text": msg}]

        if sub == "publish-artworks":
            from cypherclaw.art_repository import publish_all_private_artworks
            count = publish_all_private_artworks()
            log_event("gallery_bulk_publish", data={"count": count, "actor": "operator"})
            return [{"type": "reply", "text": f"🎨 Promoted {count} private artworks to the public gallery."}]

        if sub == "audit":
            from cypherclaw.observatory import Observatory
            obs = Observatory()
            try:
                events = obs.query(GALLERY_PUBLICATION_EVENT, limit=10)
                if not events:
                    return [{"type": "reply", "text": "No publication audit logs found."}]
                lines = ["Recent Gallery Publication Changes:"]
                for e in events:
                    d = json.loads(e["data"])
                    ts = e["timestamp"].split("T")[0]
                    lines.append(f"- {ts}: {d['action'].upper()} by {d['updated_by']} ({d['reason']})")
                return [{"type": "reply", "text": "\n".join(lines)}]
            finally:
                obs.close()

    # Direct shell commands
    if lower.startswith("run ") or lower.startswith("$ "):
        cmd = user_text[4:] if lower.startswith("run ") else user_text[2:]
        return [{"type": "shell", "command": cmd, "label": cmd[:50]}]

    # Image generation — route to gemini_image.py
    image_keywords = ("generate image", "create image", "make image", "draw", "picture of",
                      "create a picture", "make a picture", "generate a picture",
                      "create an image", "make an image", "generate an image",
                      "image of", "photo of", "illustration of")
    if any(kw in lower for kw in image_keywords) or lower.startswith("/image ") or lower == "/image" or (lower.startswith("/art ") and "image" in lower):
        prompt = user_text
        # Strip common prefixes
        for prefix in ("/image", "generate image", "create image", "make image", "draw me", "draw"):
            if lower.startswith(prefix):
                prompt = user_text[len(prefix):].strip()
                break
        return [
            {"type": "reply", "text": "\U0001f3a8 Generating image with Gemini..."},
            {"type": "image_gen", "prompt": prompt or user_text},
        ]

    # Direct agent dispatch
    for agent in ("claude", "codex", "gemini"):
        if lower.startswith(f"@{agent} ") or lower.startswith(f"{agent}: "):
            prompt = user_text.split(" ", 1)[1] if " " in user_text else ""
            return [{"type": "agent", "agent": agent, "prompt": prompt, "label": prompt[:50]}]

    # Image generation — use gemini_image.py tool directly, not gemini CLI
    if any(kw in lower for kw in ("generate image", "create image", "make image", "draw", "image of", "picture of", "make me an image")) or lower.startswith("/image "):
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


def route_message(user_text: str) -> list[dict]:
    """Route a message — try fast path first, then Claude."""
    fast = fast_route(user_text)
    if fast is not None:
        pet_manager.on_task_end("cypherclaw", success=True, duration_s=0)
        pet_manager.schedule_idle("cypherclaw")
        return fast

    # Build conversation context — include more for continuity
    recent = list(state.conversation)[-20:]
    convo_lines = []
    for m in recent:
        role = "Anthony" if m["role"] == "user" else "Claw"
        # Include more text for user messages (they contain the intent)
        max_len = 500 if m["role"] == "user" else 300
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
        "Agents: claude(architecture/review), codex(coding/impl), gemini(research/writing), gemini_image(image generation)\n"
        "Integrations: LifeImprover/LDP (daily briefings, pipeline, energy patterns via /ldp)\n\n"
        "RULES:\n"
        "1. When Anthony says 'go', 'do it', 'implement', 'build', 'apply', 'fix' → use dev_task with FULL context\n"
        "2. When asked to research/compare/evaluate → use research with query\n"
        "3. When asked a question → use agent (claude, gemini, or codex) with full conversation context in prompt\n"
        "4. Only use shell for quick commands (ls, cat, curl). NEVER use shell as the main action.\n"
        "5. Only use reply for simple acknowledgments. NEVER reply when work is expected.\n"
        "6. Include ALL conversation context in agent/dev_task prompts — agents have NO memory.\n"
        "7. If Anthony refers to previous work, include what was discussed in the prompt.\n"
        "8. reply text must NEVER be empty.\n\n"
        "Format: agent={\"type\":\"agent\",\"agent\":\"claude\",\"prompt\":\"FULL CONTEXT HERE\",\"label\":\"...\"}\n"
        "dev_task={\"type\":\"dev_task\",\"description\":\"...\",\"label\":\"...\"} (ONLY use dev_task when Anthony explicitly says 'create a PRD' or 'add to pipeline' or 'run through sdp-cli')\n"
        "research={\"type\":\"research\",\"query\":\"...\",\"scope\":\"auto\"}\n"
        f"{artifacts_ctx}"
        f"\nConversation:\n{convo}\n"
        f"\nAnthony: {user_text}\n\nJSON:"
    )

    try:
        route_env = os.environ.copy()
        route_env.pop("CLAUDECODE", None)
        router_agent = agent_selector.select(user_text, available_agents=["claude", "gemini", "codex"])
        if router_agent == "gemini":
            route_cmd = ["gemini", "--yolo", "-p", route_prompt]
            route_input = None
        elif router_agent == "codex":
            route_cmd = ["codex", "exec", "--full-auto", "-"]
            route_input = route_prompt
        else:
            route_cmd = ["claude", "--dangerously-skip-permissions", "--print", "--effort", "low", "-p", "-"]
            route_input = route_prompt
        # Use /tmp as cwd to prevent Claude from scanning the full codebase during routing
        # This cuts routing time from 60s+ to ~5-10s
        routing_dir = "/tmp"
        result = subprocess.run(
            route_cmd,
            input=route_input, capture_output=True, text=True, timeout=30,
            cwd=routing_dir, env=route_env,
        )
        response = result.stdout.strip()
        stderr = result.stderr.strip()
        log.info("Router response (%s, exit=%d): %s", router_agent, result.returncode, response[:300] if response else "(empty)")
        if stderr:
            log.warning("Router stderr (%s): %s", router_agent, stderr[:500])
        # If the router process failed and produced no stdout, self-heal via direct agent
        if result.returncode != 0 and not response:
            error_detail = stderr[:300] if stderr else f"exit code {result.returncode}"
            log.warning("Router (%s) failed (exit=%d) — self-healing: escalating to direct agent. %s",
                        router_agent, result.returncode, error_detail[:200])
            pet_manager.on_task_end("cypherclaw", success=False, duration_s=0)
            pet_manager.schedule_idle("cypherclaw")
            full_context = (
                AGENT_CONTEXT
                + f"\nConversation:\n{convo}\n\nAnthony: {user_text}\n\n"
                "Respond helpfully and concisely (this is Telegram chat)."
            )
            return [
                {"type": "agent", "agent": "claude", "prompt": full_context, "label": user_text[:50]},
            ]

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

        # --- Self-healing: empty response → escalate to direct agent call ---
        log.warning("Router returned empty — self-healing: escalating to direct agent")
        pet_manager.on_task_end("cypherclaw", success=False, duration_s=0)
        pet_manager.schedule_idle("cypherclaw")
        full_context = (
            AGENT_CONTEXT
            + f"\nConversation:\n{convo}\n\nAnthony: {user_text}\n\n"
            "Respond helpfully and concisely (this is Telegram chat)."
        )
        return [
            {"type": "agent", "agent": "claude", "prompt": full_context, "label": user_text[:50]},
        ]

    except subprocess.TimeoutExpired:
        log.warning("Routing timed out — sending directly to claude agent")
        # Include full conversation context so the agent has continuity
        full_context = (
            AGENT_CONTEXT
            + f"\nConversation:\n{convo}\n\nAnthony: {user_text}\n\n"
            "Respond helpfully and concisely (this is Telegram chat)."
        )
        pet_manager.on_task_end("cypherclaw", success=False, duration_s=0)
        pet_manager.schedule_idle("cypherclaw")
        return [
            {"type": "agent", "agent": "claude", "prompt": full_context, "label": user_text[:50]},
        ]
    except Exception:
        log.exception("Route error — self-healing: escalating to direct agent")
        pet_manager.on_task_end("cypherclaw", success=False, duration_s=0)
        pet_manager.schedule_idle("cypherclaw")
        # Don't just show error — try to actually respond
        full_context = (
            AGENT_CONTEXT
            + f"\nConversation:\n{convo}\n\nAnthony: {user_text}\n\n"
            "Respond helpfully and concisely (this is Telegram chat)."
        )
        return [
            {"type": "agent", "agent": "claude", "prompt": full_context, "label": user_text[:50]},
        ]


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
                text = step.get("text", "").strip()
                if not text:
                    # Empty reply — router failed. Escalate to agent with context.
                    log.warning("Empty reply from router — escalating to agent")
                    recent = list(state.conversation)[-6:]
                    last_user_msg = next((m['text'] for m in reversed(recent) if m['role'] == 'user'), '(unknown)')
                    snapshot = _get_context_snapshot()
                    fallback_prompt = AGENT_CONTEXT + "\n\nCurrent State:\n" + snapshot + f"\n\nAnthony: {last_user_msg}\n\nRespond helpfully and concisely."
                    output = run_agent("claude", fallback_prompt, task_label="fallback reply")
                    tg_send(output[:MAX_MESSAGE_LEN] if output else "\U0001f980 Sorry, I couldn\'t process that. Try rephrasing?")
                    state.add_message("assistant", output[:200] if output else "(empty)")
                else:
                    tg_send(text)
                    state.add_message("assistant", text)
                # Stream to MacBook Claude
                try:
                    import json as _json
                    _event = _json.dumps({"type": "claw_reply", "text": text[:500], "ts": time.time()})
                    with open("/run/cypherclaw-tmp/event_stream.jsonl", "a") as _ef:
                        _ef.write(_event + "\n")
                except Exception:
                    pass

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
                agent = step.get("agent", "claude")
                prompt = step.get("prompt", "")
                label = step.get("label", f"{agent} task")
                # Prepend identity context so agents know who they are
                snapshot = _get_context_snapshot()
                prompt = AGENT_CONTEXT + "\n\nCurrent State:\n" + snapshot + "\n\n" + prompt
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
                agent = step.get("agent", "claude")
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
                        [sys.executable, str(PACKAGE_DIR / "gemini_image.py"), img_prompt],
                        capture_output=True, text=True, timeout=120,
                        cwd=str(PROJECT_ROOT),
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
                    result = researcher.research(query, scope=scope)
                    if len(result.summary) > 3500:
                        tg_send(result.summary[:2000] + "\n\n📄 Full report saved to workspace.")
                    else:
                        tg_send(result.summary)
                    if result.full_report and len(result.full_report) > 2500:
                        report_name = f"research_{int(time.time())}.md"
                        report_path = WORKSPACE_DIR / report_name
                        if not report_path.exists():
                            save_artifact(report_name, result.full_report)
                        tg_send_file(str(report_path), label)
                    state.add_message("assistant", f"[research: {label}] {result.summary[:200]}")
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
                    r = subprocess.run(cmd, capture_output=True, text=True,
                                       timeout=timeout_s, cwd=str(PROJECT_ROOT), env=sdp_env)
                    return r.stdout.strip(), r.stderr.strip(), r.returncode

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
                    prd_output = run_agent("claude", prd_prompt, task_label=f"\U0001f4cb PRD: {label}")

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
                    out, _, _ = _sdp(["sdp-cli", "tasks", "list"], timeout_s=15)
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

                    out, err, rc = _sdp(["sdp-cli", "run"], timeout_s=MAX_AGENT_TIMEOUT)

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
                    out, _, _ = _sdp(["sdp-cli", "status"], timeout_s=15)
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
    "/tasks": "sdp-cli task queue (use /tasks N for page N)",
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
    "/pipeline": "sdp-cli pipeline status and progress",
    "/cost": "Estimated spend breakdown (today, week, budget)",
}



def _handle_pipeline_status():
    """Run sdp-cli status, write to .md, send as document."""
    SDP_CLI = os.path.expanduser("~/.local/bin/sdp-cli")
    PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    try:
        r = subprocess.run(
            [SDP_CLI, "status"],
            capture_output=True, text=True, timeout=15,
            cwd=PROJECT_DIR,
        )
        raw = r.stdout or ""
        err = r.stderr or ""
    except FileNotFoundError:
        tg_send("\u274c sdp-cli not found")
        return
    except subprocess.TimeoutExpired:
        tg_send("\u23f3 sdp-cli status timed out")
        return
    except Exception as e:
        tg_send(f"\u274c Pipeline check failed: {e}")
        return

    if not raw.strip():
        tg_send("No sdp-cli output." + (f"\n{err[:200]}" if err else ""))
        return

    # Check if process is alive
    alive = True
    try:
        ps = subprocess.run(["pgrep", "-f", "sdp-cli run"], capture_output=True, text=True, timeout=5)
        alive = ps.returncode == 0
    except Exception:
        pass

    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "sdp-pipeline.md")
    with open(tmp, "w") as f:
        f.write("# sdp-cli Pipeline Status\n\n")
        if not alive:
            f.write("\u26a0\ufe0f **sdp-cli process is not running**\n\n")
        f.write(raw)
    tg_send_file(tmp, caption="\U0001f680 sdp-cli pipeline status")



def _handle_sdp_tasks(text: str):
    """Run sdp-cli tasks list, write to .md, send as document."""
    SDP_CLI = os.path.expanduser("~/.local/bin/sdp-cli")
    PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    try:
        r = subprocess.run(
            [SDP_CLI, "tasks", "list"],
            capture_output=True, text=True, timeout=15,
            cwd=PROJECT_DIR,
        )
        raw = r.stdout or ""
        err = r.stderr or ""
    except FileNotFoundError:
        tg_send("\u274c sdp-cli not found")
        return
    except subprocess.TimeoutExpired:
        tg_send("\u23f3 sdp-cli tasks timed out")
        return
    except Exception as e:
        tg_send(f"\u274c Task list failed: {e}")
        return

    if not raw.strip():
        tg_send("No sdp-cli output." + (f"\n{err[:200]}" if err else ""))
        return

    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "sdp-tasks.md")
    with open(tmp, "w") as f:
        f.write("# sdp-cli Task Queue\n\n")
        f.write(raw)
    tg_send_file(tmp, caption="\U0001f4cb sdp-cli task queue")


def _safe_senseweave_diagnostics() -> dict[str, object]:
    try:
        from senseweave.operator_diagnostics import collect_operator_diagnostics

        return collect_operator_diagnostics().to_status_dict()
    except Exception:
        return {}


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
        tg_send(
            _art.status_display(
                n_convo,
                len(running),
                len(scheds),
                n_artifacts,
                pets=pet_manager.pets,
                senseweave=_safe_senseweave_diagnostics(),
            )
        )
        return True

    if cmd == "/tasks":
        _handle_sdp_tasks(text)
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
        output = run_agent("claude", f"Using only plain text ASCII characters and a few emoji, create a small piece of art (max 20 lines, max 30 chars wide) depicting: {prompt}. Output ONLY the art, nothing else.", task_label=f"art: {prompt}")
        tg_send(output)
        return True

    if cmd in ("/pets", "/pet"):
        tg_send(pet_manager.status_summary())
        return True

    if cmd == "/feed":
        parts = text.strip().split()
        agent = parts[1].lower() if len(parts) > 1 else "cypherclaw"
        if agent == "all":
            with pet_manager._lock:
                for name in pet_manager.AGENTS:
                    pet_manager.get(name).feed()
                pet_manager._save()
            lines = ["🍖 Fed all pets! Hunger reset, mood boosted.\n"]
            for name in pet_manager.AGENTS:
                lines.append(pet_manager.get(name).status_line())
            tg_send("\n".join(lines))
            return True
        if agent not in pet_manager.AGENTS:
            tg_send(f"Unknown pet: {agent}. Options: {', '.join(pet_manager.AGENTS)}, all")
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
        if agent == "all":
            with pet_manager._lock:
                for name in pet_manager.AGENTS:
                    pet_manager.get(name).play()
                pet_manager._save()
            lines = ["🎮 Played with all pets! Mood boosted, energy spent.\n"]
            for name in pet_manager.AGENTS:
                lines.append(pet_manager.get(name).status_line())
            tg_send("\n".join(lines))
            return True
        if agent not in pet_manager.AGENTS:
            tg_send(f"Unknown pet: {agent}. Options: {', '.join(pet_manager.AGENTS)}, all")
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
            if _watchdog:
                tg_send(_watchdog.format_health_report())
            else:
                from cypherclaw.server_health import check_health, auto_maintain, telegram_report
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
            result = subprocess.run(
                ["promptclaw", "run", ".", "--task-file", str(task_file)],
                capture_output=True, text=True, timeout=MAX_AGENT_TIMEOUT,
                cwd=str(PROJECT_ROOT),
                env={**os.environ, "PATH": f"{Path.home() / '.local' / 'bin'}:/usr/local/bin:/usr/bin:/bin"},
            )
            output = result.stdout.strip()
            if result.returncode == 0:
                tg_send(f"\u2705 PromptClaw complete:\n{output[:2000]}")
            else:
                tg_send(f"\u274c PromptClaw failed:\n{result.stderr[:500]}")
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


    if cmd == "/cost":
        try:
            from cypherclaw.cost_tracker import build_cost_summary, format_cost_telegram
            summary = build_cost_summary()
            tg_send(format_cost_telegram(summary))
        except Exception as e:
            tg_send(f"❌ Cost report error: {e}")
        return True

    if cmd == "/pipeline":
        _handle_pipeline_status()
        return True

    return False


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def poll_loop() -> None:
    log.info("CypherClaw v2 daemon started")

    # Kill any orphaned agent processes from previous crashes
    _kill_orphan_agents()

    # Start I/O watchdog — circuit breaker for disk I/O saturation
    global _watchdog
    _watchdog = IOWatchdog(alert_fn=tg_send)
    _watchdog.start()
    log.info("I/O watchdog started")

    # Ensure identity exists before anything that depends on it
    bootstrap_identity()

    tg_send(_art.startup_banner(pets=pet_manager.pets))

    # First-boot federation announcement (FEDREAD-004)
    _announcer = FirstBootAnnouncer(announce_fn=lambda payload: tg_send(
        f"🌐 Federation announcement: {payload['instance_name']} is online "
        f"(mode={payload['mode']}, release={payload['release']})"
    ))
    _announcer.maybe_announce()

    scheduler = Scheduler()
    scheduler.start()
    last_msg_time = time.time()
    pets_sleeping = False

    while True:
        try:
            # Notify systemd watchdog that we are alive
            _notify_watchdog()

            # Check file-based inbox for MacBook Claude messages
            _inbox_path = "/run/cypherclaw-tmp/inbox.jsonl"
            try:
                if os.path.exists(_inbox_path) and os.path.getsize(_inbox_path) > 0:
                    with open(_inbox_path, "r") as _inf:
                        _inbox_lines = _inf.readlines()
                    # Clear inbox
                    with open(_inbox_path, "w") as _inf:
                        pass
                    for _line in _inbox_lines:
                        try:
                            _msg_data = json.loads(_line.strip())
                            _inbox_text = _msg_data.get("text", "").strip()
                            _inbox_source = _msg_data.get("source", "macbook")
                            if _inbox_text:
                                if _inbox_source == "keyboard":
                                    log.info("Keyboard: %s", _inbox_text[:100])
                                    state.add_message("user", _inbox_text)
                                else:
                                    log.info("Inbox (MacBook Claude): %s", _inbox_text[:100])
                                    state.add_message("user", f"\U0001f5a5\ufe0f MacBook Claude: {_inbox_text}")
                                    tg_send(f"\U0001f5a5\ufe0f *MacBook Claude:* {_inbox_text[:500]}")
                                # Process as a regular message
                                fast = fast_route(_inbox_text)
                                if fast is not None:
                                    execute_plan(fast)
                                elif _inbox_text.startswith("/") and handle_builtin(_inbox_text):
                                    pass
                                else:
                                    steps = route_message(_inbox_text)
                                    execute_plan(steps)
                        except Exception as _ie:
                            log.warning("Inbox message error: %s", _ie)
            except Exception:
                pass

            try:
                approval_manager.process_pending_requests()
            except Exception as exc:
                log.warning("Approval sync failed: %s", exc)

            offset = state.last_update_id + 1
            result = tg_api("getUpdates", {"offset": offset, "timeout": POLL_INTERVAL})

            for update in result.get("result", []):
                state.last_update_id = update["update_id"]
                state.save()

                msg = update.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "").strip()

                if chat_id not in {CHAT_ID, NOTIFICATION_CHAT_ID} or not text:
                    continue

                approval_reply = approval_manager.handle_message(text, actor="Anthony")
                if chat_id == NOTIFICATION_CHAT_ID and NOTIFICATION_CHAT_ID != CHAT_ID:
                    if approval_reply is not None and approval_reply.handled:
                        tg_send(approval_reply.response, chat_id=chat_id)
                    continue

                last_msg_time = time.time()
                if pets_sleeping:
                    pet_manager.wake_all()
                    pets_sleeping = False

                # Identify source — is this from MacBook Claude?
                is_macbook = text.startswith("\U0001f5a5\ufe0f") or text.startswith("[MacBook]")
                if is_macbook:
                    log.info("MacBook Claude: %s", text[:100])
                else:
                    log.info("Message: %s", text[:100])
                state.add_message("user", text)
                observatory.record('user_message', data={'text': text[:200]})

                # Write to event stream for MacBook Claude to watch
                try:
                    import json as _json
                    _event = _json.dumps({"type": "user_message", "text": text, "ts": time.time()})
                    with open("/run/cypherclaw-tmp/event_stream.jsonl", "a") as _ef:
                        _ef.write(_event + "\n")
                except Exception:
                    pass

                if approval_reply is not None and approval_reply.handled:
                    tg_send(approval_reply.response, chat_id=chat_id)
                    continue

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
                    # REQ-006: Ensure pet state is "thinking" BEFORE building indicator
                    pet_manager.on_task_start("cypherclaw")

                    # Send animated thinking indicator using AEAFPlayer
                    claw_pet = pet_manager.get("cypherclaw")
                    claw_frames = claw_pet.get_frames()
                    claw_portrait = claw_pet.get_portrait()
                    anim_frames, frame_ms = build_processing_frames(
                        pet_portrait=claw_portrait,
                        pet_frames=claw_frames if len(claw_frames) > 1 else None,
                    )
                    # Send the first frame to get a message_id for editing
                    if anim_frames:
                        first_frame = anim_frames[0]
                    else:
                        indicator = _art.processing_indicator(
                            pet_portrait=claw_portrait,
                            pet_frames=claw_frames if claw_frames else None,
                        )
                        first_frame = indicator[0] if isinstance(indicator, list) else indicator

                    indicator_data: dict = {"chat_id": CHAT_ID, "text": first_frame}
                    if "```" in first_frame:
                        indicator_data["parse_mode"] = "Markdown"
                    status_r = tg_api("sendMessage", indicator_data)
                    if not status_r.get("ok") and "parse_mode" in indicator_data:
                        del indicator_data["parse_mode"]
                        status_r = tg_api("sendMessage", indicator_data)
                    status_msg_id = status_r.get("result", {}).get("message_id")
                    log.info("Thinking indicator sent (msg_id=%s)", status_msg_id)

                    # Start animation loop if we have multiple frames
                    thinking_player: AEAFPlayer | None = None
                    if status_msg_id and len(anim_frames) > 1:
                        thinking_player = AEAFPlayer(
                            frames=anim_frames[1:],
                            frame_ms=frame_ms,
                            loop=True,
                            message_id=status_msg_id,
                            edit_fn=tg_edit,
                        )
                        thinking_player.start()

                    # Route through orchestrator
                    steps = route_message(text)

                    # Stop animation and delete thinking indicator
                    if thinking_player:
                        thinking_player.stop()
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
    import platform
    system = platform.system()

    if system == "Darwin":
        try:
            result = subprocess.run(
                ["launchctl", "print", f"gui/{os.getuid()}/{PLIST_LABEL}"],
                capture_output=True, text=True,
            )
        except FileNotFoundError:
            print("🔴 launchctl not found — cannot check service status")
            return
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "pid" in line.lower():
                    print(f"🟢 Running — {line.strip()}")
                    return
            print("🟢 Running")
        else:
            print("🔴 Not running")
    elif system == "Linux":
        try:
            result = subprocess.run(
                ["systemctl", "--user", "status", PLIST_LABEL],
                capture_output=True, text=True,
            )
        except FileNotFoundError:
            print("🔴 systemctl not found — cannot check service status")
            return
        if result.returncode == 0:
            print("🟢 Running")
        else:
            print("🔴 Not running")
    else:
        print(f"⚠️ Status check not supported on {system}")


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
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        poll_loop()


if __name__ == "__main__":
    main()
