"""Startle daemon — monitors room for sudden sounds, triggers face reaction."""
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "senseweave"))
from startle import update_startle, startle_to_face_reaction, StartleState

STATE = "/tmp/startle_state.json"
state = StartleState()

while True:
    try:
        room = json.loads(open("/tmp/room_activity.json").read())
        amp = max(room.get("window_mic_amp", 0), room.get("cypherclaw_mic_amp", 0))
        transient = room.get("recent_transient", False)
        state = update_startle(state, amp, transient)
        face = startle_to_face_reaction(state)
        out = {"startled": state.startled, "startle_count": state.startle_count,
               "cooldown_active": state.cooldown_active, "face_reaction": face,
               "timestamp": time.time()}
        tmp = STATE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(out, f)
        os.replace(tmp, STATE)
    except Exception:
        pass
    time.sleep(0.5)
