"""MIDI keyboard listener — reads from Akai MAX25 + KORG microKEY-25.

Writes /tmp/midi_keyboard_state.json with current notes, velocity.
Notes are forwarded to the composer via the daemon inbox.
"""
import json, os, time, sys
from pathlib import Path

STATE_FILE = Path("/tmp/midi_keyboard_state.json")

def midi_to_freq(note):
    return 440.0 * (2 ** ((note - 69) / 12.0))

def midi_to_name(note):
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[note % 12]}{note // 12 - 1}"

def write_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(str(tmp), str(STATE_FILE))

def run(devices):
    print(f"MIDI keyboard listener on {devices}", flush=True)
    
    fds = {}
    for dev in devices:
        try:
            fds[dev] = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
            print(f"  Opened {dev}", flush=True)
        except OSError as e:
            print(f"  Cannot open {dev}: {e}", flush=True)
    
    if not fds:
        print("No MIDI devices available", flush=True)
        return
    
    active_notes = {}  # note -> {freq, name, velocity, time}
    last_activity = 0
    
    while True:
        for dev, fd in fds.items():
            try:
                data = os.read(fd, 256)
            except (BlockingIOError, OSError):
                continue
            
            i = 0
            while i < len(data):
                status = data[i]
                if status & 0x80 == 0:
                    i += 1
                    continue
                msg_type = status & 0xF0
                if msg_type == 0x90 and i + 2 < len(data):
                    note, vel = data[i+1], data[i+2]
                    i += 3
                    if vel > 0:
                        active_notes[note] = {
                            "freq": midi_to_freq(note),
                            "name": midi_to_name(note),
                            "velocity": vel,
                            "time": time.time(),
                        }
                        last_activity = time.time()
                    else:
                        active_notes.pop(note, None)
                elif msg_type == 0x80 and i + 2 < len(data):
                    note = data[i+1]
                    i += 3
                    active_notes.pop(note, None)
                elif msg_type in (0xB0, 0xE0) and i + 2 < len(data):
                    i += 3
                elif msg_type in (0xC0, 0xD0) and i + 1 < len(data):
                    i += 2
                else:
                    i += 1
        
        # Expire old notes (> 5s)
        now = time.time()
        active_notes = {k: v for k, v in active_notes.items() if now - v["time"] < 5.0}
        
        state = {
            "timestamp": now,
            "playing": len(active_notes) > 0,
            "notes": [v["name"] for v in active_notes.values()],
            "freqs": [v["freq"] for v in active_notes.values()],
            "velocities": [v["velocity"] for v in active_notes.values()],
            "last_activity": last_activity,
        }
        write_state(state)
        time.sleep(0.05)

if __name__ == "__main__":
    # Akai MAX25 and KORG microKEY-25
    devs = [d for d in ["/dev/midi5", "/dev/midi7", "/dev/midi8"] if os.path.exists(d)]
    if not devs:
        devs = ["/dev/midi"]
    run(devs)
