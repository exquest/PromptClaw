"""Sensory journal daemon — logs significant sensor events over time."""
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "senseweave"))
from sensory_journal import log_event

FUSED = "/tmp/organism_state.json"
JOURNAL = "/home/user/cypherclaw-data/state/sensory_journal.jsonl"
last = {}

while True:
    try:
        state = json.loads(open(FUSED).read())
        mood = state.get("organism_mood", {})
        room = state.get("room", {})
        ther = state.get("theramini", {})
        if ther.get("playing") and not last.get("tp"):
            log_event("theramini_start", {"pitch": ther.get("pitch")}, journal_path=JOURNAL)
        if room.get("transient") and not last.get("tr"):
            log_event("room_transient", {"activity": room.get("activity")}, journal_path=JOURNAL)
        ne = mood.get("energy", 0.5)
        if abs(ne - last.get("e", 0.5)) > 0.15:
            log_event("mood_shift", {"energy": ne}, journal_path=JOURNAL)
        last = {"tp": ther.get("playing"), "tr": room.get("transient"), "e": ne}
    except Exception:
        pass
    time.sleep(5)
