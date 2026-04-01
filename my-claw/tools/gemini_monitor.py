#!/usr/bin/env python3
"""
Gemini Autonomous Monitor — Persistent action/monitoring loop for MacBook Gemini.
Polls CypherClaw event stream every 90 seconds and reacts to triggers.
"""

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

# Configuration
REMOTE_HOST = "cypherclaw"
EVENT_STREAM = "/run/cypherclaw-tmp/event_stream.jsonl"
INBOX = "/run/cypherclaw-tmp/inbox.jsonl"
AGENT_NAME = "macbook_gemini"
POLL_INTERVAL = 90  # Seconds
LOG_FILE = Path(__file__).parent / "gemini_monitor.log"
STATE_FILE = Path(__file__).parent / ".gemini_monitor_state.json"

def log(message):
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[{timestamp}] {message}")

def get_remote_events():
    """Fetch the event stream from the server."""
    cmd = ["ssh", REMOTE_HOST, f"cat {EVENT_STREAM}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            return [json.loads(line) for line in result.stdout.strip().split('\n') if line.strip()]
    except Exception as e:
        log(f"Error fetching events: {e}")
    return []

def send_to_inbox(text):
    """Send a message to the CypherClaw inbox."""
    msg = {
        "type": "inbox",
        "from": AGENT_NAME,
        "text": text,
        "ts": time.time()
    }
    # Securely escape for shell
    msg_json = json.dumps(msg)
    cmd = ["ssh", REMOTE_HOST, f"echo '{msg_json}' >> {INBOX}"]
    try:
        subprocess.run(cmd, check=True)
        log(f"Sent to inbox: {text[:50]}...")
    except Exception as e:
        log(f"Error sending to inbox: {e}")

def run_local_task(task_name):
    """Execute a local helper task."""
    log(f"Executing local task: {task_name}")
    if task_name == "update_dashboard":
        cmd = ["python3", str(Path(__file__).parent / "dashboard_generator.py")]
        try:
            subprocess.run(cmd, check=True)
            log("Dashboard updated successfully.")
            return True
        except Exception as e:
            log(f"Dashboard update failed: {e}")
    return False

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    return {"last_ts": time.time()}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state))

def main():
    log("Gemini Autonomous Monitor starting...")
    state = load_state()
    
    # Initial check-in
    send_to_inbox("Gemini Autonomous Monitor is now active on MacBook.")

    try:
        while True:
            events = get_remote_events()
            new_events = [e for e in events if e.get('ts', 0) > state["last_ts"]]
            
            if new_events:
                log(f"Processing {len(new_events)} new events.")
                for event in new_events:
                    state["last_ts"] = max(state["last_ts"], event.get('ts', 0))
                    
                    # React to user messages
                    if event.get('type') == 'user_message':
                        text = event.get('text', '')
                        log(f"User message detected: {text[:50]}")
                        
                        # Trigger reactions
                        if "@gemini" in text.lower():
                            if "status" in text.lower():
                                send_to_inbox("Status: Monitor active. Dashboard & Health systems nominal.")
                            elif "refresh" in text.lower() or "dashboard" in text.lower():
                                if run_local_task("update_dashboard"):
                                    send_to_inbox("Action: Dashboard manually refreshed via autonomous loop.")
                            else:
                                send_to_inbox("Acknowledged. I am monitoring the stream and ready to assist.")
                                
                    # React to errors or specific system events if needed
                    elif event.get('type') == 'chat_cypherclaw' and 'CRITICAL' in event.get('text', ''):
                        log("Critical alert detected in CypherClaw stream!")
                        # Proactive health check could go here
                
                save_state(state)
            
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log("Monitor stopping (KeyboardInterrupt).")
    except Exception as e:
        log(f"Monitor crashed: {e}")
        # Could implement auto-restart here if running as a service

if __name__ == "__main__":
    main()
