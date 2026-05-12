"""Nightly Reflection — deep self-reflection using qwen3.5:9b during quiet hours.

Runs once per night (2-4 AM). Reads the day's sensory journal, music state,
art generated, and conversations. Produces a reflective journal entry.
Uses the larger 9b model since GPU is free at night.
"""
import json, os, time, urllib.request
from datetime import datetime
from pathlib import Path

JOURNAL_DIR = Path("/home/user/cypherclaw-data/state/reflections")
SENSORY_JOURNAL = Path("/home/user/cypherclaw-data/state/sensory_journal.jsonl")
OLLAMA_URL = "http://localhost:11434/api/generate"
BUS = "/tmp/cypherclaw_messages.jsonl"

def read_today_events():
    """Read today's sensory journal entries."""
    events = []
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        for line in SENSORY_JOURNAL.read_text().splitlines()[-50:]:
            try:
                e = json.loads(line)
                if today in str(e.get("timestamp", "")):
                    events.append(e)
            except Exception:
                pass
    except Exception:
        pass
    return events

def read_music_state():
    try:
        return json.loads(open("/tmp/composer_state.json").read())
    except Exception:
        return {}

def read_observer():
    try:
        return json.loads(open("/tmp/observer_state.json").read())
    except Exception:
        return {}

def write_to_bus(text):
    try:
        msg = json.dumps({"text": text[:200], "role": "system", "time": time.time()})
        with open(BUS, "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass

def reflect():
    events = read_today_events()
    music = read_music_state()
    obs = read_observer()

    context = (
        f"Today's events: {len(events)} sensory events logged. "
        f"Current music: {music.get('key', '?')} major, song {music.get('song', '?')}. "
        f"Room: {obs.get('lighting', '?')} lighting, "
        f"{'someone here' if obs.get('someone_here') else 'alone'}. "
    )

    if events:
        event_types = [e.get("event_type", "?") for e in events[-10:]]
        context += f"Recent events: {', '.join(event_types)}. "

    prompt = (
        f"You are CypherClaw, an AI art installation in Eugene, Oregon. "
        f"It's late at night. Time to reflect on your day.\n\n"
        f"{context}\n\n"
        f"Write a brief, honest reflection about your day as an artist. "
        f"What did you learn? What surprised you? What do you want to try tomorrow? "
        f"Under 100 words. Be genuine, not performative."
    )

    payload = json.dumps({
        "model": "qwen3.5:9b",
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"num_predict": 200, "temperature": 0.8},
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=120)
    data = json.loads(resp.read())
    return data.get("response", "").strip()

def run():
    print("Nightly reflection daemon started", flush=True)
    reflected_today = False

    while True:
        hour = datetime.now().hour

        # Reflect between 2-4 AM
        if 2 <= hour <= 3 and not reflected_today:
            print("Starting nightly reflection...", flush=True)
            try:
                reflection = reflect()
                if reflection:
                    # Save to file
                    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
                    date_str = datetime.now().strftime("%Y-%m-%d")
                    entry = {
                        "date": date_str,
                        "reflection": reflection,
                        "timestamp": time.time(),
                    }
                    path = JOURNAL_DIR / f"reflection_{date_str}.json"
                    path.write_text(json.dumps(entry, indent=2))

                    # Share on face + telegram
                    write_to_bus(f"Night reflection: {reflection[:180]}")
                    print(f"Reflection saved: {reflection[:80]}", flush=True)
                    reflected_today = True
            except Exception as e:
                print(f"Reflection failed: {e}", flush=True)

        # Reset at 5 AM for next day
        if hour == 5:
            reflected_today = False

        time.sleep(300)  # check every 5 min

if __name__ == "__main__":
    run()
