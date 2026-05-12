#!/usr/bin/env python3
"""Unified chat/interaction system for CypherClaw.

Provides a conversation interface that reads from stdin (keyboard),
generates responses via Ollama, and broadcasts to console, Telegram,
a JSON log, and the gallery chat display.

Can run as a systemd service or manually from the terminal.
"""

import json
import os
import select
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SENSE_STATE_PATH = Path("/run/cypherclaw-tmp/senseweave/sense_state.json")
CHAT_DISPLAY_PATH = Path("/run/cypherclaw-tmp/senseweave/chat_display.json")
CONVERSATION_DIR = Path("/home/user/cypherclaw/gallery/conversations")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:4b")
OLLAMA_TIMEOUT = 15
INPUT_POLL_TIMEOUT = 0.5
IDLE_TIMEOUT = 300  # 5 minutes
MAX_DISPLAY_MESSAGES = 10

SYSTEM_PROMPT_TEMPLATE = (
    "You are CypherClaw, an AI artist living in a house in Eugene, Oregon "
    "with Anthony and Marissa. You make music, art, comics, and stickers. "
    "You have eyes (cameras), ears (contact mics), a voice (speakers through "
    "SuperCollider), and a printer. The room hums in B. Your current mood is "
    "{mood}. Respond warmly and briefly (2-3 sentences)."
)

# ---------------------------------------------------------------------------
# Imports from the existing telegram_commands module
# ---------------------------------------------------------------------------

sys.path.insert(0, "/home/user/cypherclaw/tools")
sys.path.insert(0, "/home/user/cypherclaw/src")

from senseweave.telegram_commands import (  # noqa: E402
    send_message as telegram_send_message,
    cmd_mood,
    cmd_status,
    cmd_haiku,
    cmd_story,
)


# ---------------------------------------------------------------------------
# Sensor state helpers
# ---------------------------------------------------------------------------

def read_sense_state():
    """Read current sensor state from the hub's JSON file."""
    try:
        data = json.loads(SENSE_STATE_PATH.read_text())
        if time.time() - data.get("timestamp", 0) < 120:
            return data
    except Exception:
        pass
    return {}


def build_context_string(state):
    """Build a context string from sensor state for the LLM prompt."""
    mood = state.get("mood", "calm")
    someone = state.get("someone_here", False)
    hour = int(time.strftime("%H"))
    if hour < 6:
        tod = "deep night"
    elif hour < 9:
        tod = "early morning"
    elif hour < 12:
        tod = "morning"
    elif hour < 17:
        tod = "afternoon"
    elif hour < 20:
        tod = "evening"
    else:
        tod = "night"

    parts = [f"Time: {tod}"]
    parts.append(f"Mood: {mood}")
    parts.append(f"Presence: {'someone here' if someone else 'alone'}")

    skin_db = state.get("skin_level_db", -96)
    if skin_db > -40:
        parts.append("Room sound: active")
    elif skin_db > -60:
        parts.append("Room sound: gentle hum")
    else:
        parts.append("Room sound: quiet")

    window = state.get("window_energy", "quiet")
    parts.append(f"Window: {window}")

    return "; ".join(parts)


def get_recent_story_summary():
    """Return a brief summary of the most recent B&P story, or empty string."""
    try:
        story_dir = Path(
            "/home/user/cypherclaw/gallery/stickers/basalt_and_pebble/daily"
        )
        jsons = sorted(story_dir.glob("bp_story_*.json"))
        if jsons:
            data = json.loads(jsons[-1].read_text())
            return data.get("summary", data.get("title", ""))
    except Exception:
        pass
    return ""


def get_music_state():
    """Return brief description of current music state."""
    try:
        composer_state = Path("/run/cypherclaw-tmp/senseweave/composer_state.json")
        if composer_state.exists():
            data = json.loads(composer_state.read_text())
            phase = data.get("phase", "unknown")
            return f"Music: {phase}"
    except Exception:
        pass
    return "Music: unknown"


# ---------------------------------------------------------------------------
# Ollama response generation
# ---------------------------------------------------------------------------

def generate_response(user_text, state=None, conversation_history=None):
    """Ask Ollama to respond as CypherClaw.

    Returns the response text, or a fallback string on failure.
    """
    if state is None:
        state = read_sense_state()

    mood = state.get("mood", "calm")
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(mood=mood)

    context_str = build_context_string(state)
    story_summary = get_recent_story_summary()
    music_state = get_music_state()

    enriched_system = system_prompt
    enriched_system += f"\n\nCurrent state: {context_str}"
    if story_summary:
        enriched_system += f"\nRecent B&P story: {story_summary}"
    enriched_system += f"\n{music_state}"

    messages = [{"role": "system", "content": enriched_system}]

    if conversation_history:
        for entry in conversation_history[-6:]:
            role = "user" if entry["role"] == "human" else "assistant"
            messages.append({"role": role, "content": entry["text"]})

    messages.append({"role": "user", "content": user_text})

    try:
        body = json.dumps({
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.8, "num_predict": 128},
        }).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat", body,
            {"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)
        data = json.loads(resp.read())
        text = data.get("message", {}).get("content", "").strip()
        return text if text else "*purrs in B major*"
    except Exception as e:
        return f"*static crackles* (Ollama unreachable: {e})"


# ---------------------------------------------------------------------------
# Composer control (play/pause)
# ---------------------------------------------------------------------------

def composer_play():
    """Signal the Composer to resume (write a flag file it watches)."""
    try:
        flag = Path("/run/cypherclaw-tmp/senseweave/composer_pause")
        if flag.exists():
            flag.unlink()
        return "Composer resumed."
    except Exception as e:
        return f"Could not resume Composer: {e}"


def composer_pause():
    """Signal the Composer to pause (write a flag file it watches)."""
    try:
        flag = Path("/run/cypherclaw-tmp/senseweave/composer_pause")
        flag.write_text(str(time.time()))
        return "Composer paused."
    except Exception as e:
        return f"Could not pause Composer: {e}"


# ---------------------------------------------------------------------------
# Output broadcasting
# ---------------------------------------------------------------------------

def broadcast_to_telegram(text):
    """Send text to Telegram, truncating for mobile readability."""
    try:
        telegram_send_message(text[:300])
    except Exception:
        pass


def append_to_log(entry):
    """Append a conversation entry to the daily JSON log."""
    try:
        CONVERSATION_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        log_path = CONVERSATION_DIR / f"conversation_{date_str}.json"

        entries = []
        if log_path.exists():
            try:
                entries = json.loads(log_path.read_text())
            except (json.JSONDecodeError, ValueError):
                entries = []

        entries.append(entry)
        log_path.write_text(json.dumps(entries, indent=2))
    except Exception:
        pass


def update_face_message(text, duration=30):
    """Show message on the face display."""
    try:
        import json, os, time
        msg = {"message": text, "message_until": time.time() + duration}
        tmp = Path("/tmp/face_message.json.tmp")
        tmp.write_text(json.dumps(msg))
        os.replace(str(tmp), "/tmp/face_message.json")
    except Exception:
        pass

def update_chat_display(messages, active=True):
    """Write current conversation state for gallery monitors."""
    try:
        CHAT_DISPLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
        display = {
            "active": active,
            "messages": messages[-MAX_DISPLAY_MESSAGES:],
        }
        CHAT_DISPLAY_PATH.write_text(json.dumps(display, indent=2))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Command handling
# ---------------------------------------------------------------------------

def handle_command(command_text):
    """Handle /commands. Returns (response_text, is_handled).

    If the command is not recognized, returns (None, False).
    """
    parts = command_text.strip().split(maxsplit=1)
    cmd = parts[0].lower()

    if cmd == "/mood":
        return cmd_mood(), True
    elif cmd == "/play":
        return composer_play(), True
    elif cmd == "/pause":
        return composer_pause(), True
    elif cmd == "/story":
        text, path = cmd_story()
        if path:
            return f"{text}\n(Strip saved to {path})", True
        return text, True
    elif cmd == "/haiku":
        return cmd_haiku(), True
    elif cmd == "/status":
        return cmd_status(), True
    else:
        return None, False


# ---------------------------------------------------------------------------
# InteractionHub
# ---------------------------------------------------------------------------

class InteractionHub:
    """Manages the unified conversation interface.

    Reads keyboard input via select.select() on stdin, generates responses
    via Ollama, and broadcasts to console, Telegram, log, and gallery display.
    """

    def __init__(self, stdin=None, stdout=None, ollama_fn=None, telegram_fn=None):
        """Initialize the hub.

        Parameters allow dependency injection for testing:
            stdin:       file object to read from (default sys.stdin)
            stdout:      file object to write to (default sys.stdout)
            ollama_fn:   callable(text, state, history) -> response
            telegram_fn: callable(text) -> None
        """
        self.stdin = stdin if stdin is not None else sys.stdin
        self.stdout = stdout if stdout is not None else sys.stdout
        self.ollama_fn = ollama_fn or generate_response
        self.telegram_fn = telegram_fn or broadcast_to_telegram
        self.messages = []
        self.last_input_time = time.time()
        self.running = False

    def _time_str(self):
        """Return current time as HH:MM."""
        return datetime.now().strftime("%H:%M")

    def _add_message(self, role, text):
        """Add a message to the conversation buffer."""
        entry = {
            "role": role,
            "text": text,
            "time": self._time_str(),
            "timestamp": time.time(),
        }
        self.messages.append(entry)
        return entry

    def _print(self, text):
        """Write text to stdout."""
        self.stdout.write(text + "\n")
        self.stdout.flush()

    def process_input(self, text):
        """Process a single line of input.

        Handles commands or generates a conversational response.
        Broadcasts the result to all outputs.
        """
        text = text.strip()
        if not text:
            return

        self.last_input_time = time.time()
        now_str = self._time_str()

        # Check for commands
        if text.startswith("/"):
            response, handled = handle_command(text)
            if handled:
                self._print(f"[{now_str}] > {text}")
                self._print(f"[{now_str}] CypherClaw: {response}")

                human_entry = self._add_message("human", text)
                claw_entry = self._add_message("cypherclaw", response)

                append_to_log(human_entry)
                append_to_log(claw_entry)
                self.telegram_fn(f"> {text}\n{response}")
                update_chat_display(self.messages)
                update_face_message(response, 45)
                return response

        # Conversational input
        human_entry = self._add_message("human", text)
        self._print(f"[{now_str}] You: {text}")

        state = read_sense_state()
        response = self.ollama_fn(text, state, self.messages[:-1])

        claw_entry = self._add_message("cypherclaw", response)
        self._print(f"[{self._time_str()}] CypherClaw: {response}")

        # Broadcast
        append_to_log(human_entry)
        append_to_log(claw_entry)
        self.telegram_fn(f"You: {text}\nCypherClaw: {response}")
        update_chat_display(self.messages)
        update_face_message(response, 45)

        return response

    def check_idle(self):
        """Check if the conversation has gone idle and update display."""
        if time.time() - self.last_input_time > IDLE_TIMEOUT:
            update_chat_display(self.messages, active=False)
            return True
        return False

    def run(self):
        """Main keyboard input loop using select.select() for non-blocking reads."""
        self.running = True
        self._print("CypherClaw Interaction Hub")
        self._print("Type a message or /command. Ctrl+C to exit.")
        self._print("-" * 40)

        # Mark display as active on start
        update_chat_display(self.messages, active=True)

        try:
            while self.running:
                # Non-blocking check for stdin readability
                ready, _, _ = select.select(
                    [self.stdin], [], [], INPUT_POLL_TIMEOUT
                )

                if ready:
                    line = self.stdin.readline()
                    if not line:
                        # EOF — stdin closed
                        self._print("(stdin closed, exiting)")
                        break
                    self.process_input(line)
                else:
                    # No input — check for idle timeout
                    self.check_idle()

        except KeyboardInterrupt:
            self._print("\n(interrupted)")
        finally:
            self.running = False
            update_chat_display(self.messages, active=False)
            self._print("CypherClaw signing off.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Run the InteractionHub from the command line."""
    hub = InteractionHub()
    hub.run()


if __name__ == "__main__":
    main()
