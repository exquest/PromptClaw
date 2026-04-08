"""Theramini MIDI listener — reads pitch from Moog Theremini MIDI output.

Writes /tmp/theramini_state.json with current pitch, note name, playing state.
Much cleaner than audio capture — direct MIDI note data.
"""
import json, os, struct, time, sys
from pathlib import Path

STATE_FILE = Path("/tmp/theramini_state.json")

def midi_to_freq(note):
    return 440.0 * (2 ** ((note - 69) / 12.0))

def midi_to_name(note):
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[note % 12]}{note // 12 - 1}"

def write_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(str(tmp), str(STATE_FILE))

def run(device="/dev/midi3"):
    print(f"Theramini MIDI listener on {device}", flush=True)
    
    current_note = None
    last_note_time = 0
    silence_start = time.time()
    
    try:
        fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as e:
        print(f"Cannot open {device}: {e}", flush=True)
        # Fallback: write silence state periodically
        while True:
            write_state({
                "timestamp": time.time(),
                "is_playing": False,
                "pitch_hz": None,
                "pitch_note": None,
                "pitch_confidence": 0.0,
                "state": "no_device",
                "consecutive_silence_ms": int((time.time() - silence_start) * 1000),
            })
            time.sleep(2)
    
    buf = b""
    while True:
        try:
            data = os.read(fd, 256)
            buf += data
        except BlockingIOError:
            pass
        except OSError:
            time.sleep(0.1)
            continue
        
        # Parse MIDI messages from buffer
        while len(buf) >= 3:
            status = buf[0]
            if status & 0x80 == 0:
                buf = buf[1:]  # skip non-status bytes
                continue
            
            msg_type = status & 0xF0
            if msg_type == 0x90:  # Note On
                note = buf[1]
                vel = buf[2]
                buf = buf[3:]
                if vel > 0:
                    current_note = note
                    last_note_time = time.time()
                    silence_start = 0
                else:
                    if current_note == note:
                        current_note = None
                        silence_start = time.time()
            elif msg_type == 0x80:  # Note Off
                note = buf[1]
                buf = buf[3:]
                if current_note == note:
                    current_note = None
                    silence_start = time.time() if silence_start == 0 else silence_start
            elif msg_type == 0xB0:  # CC
                buf = buf[3:]
            elif msg_type == 0xE0:  # Pitch bend
                buf = buf[3:]
            elif msg_type in (0xC0, 0xD0):  # Program/Aftertouch
                buf = buf[2:]
            else:
                buf = buf[1:]
        
        # Write state
        now = time.time()
        is_playing = current_note is not None and (now - last_note_time < 2.0)
        
        state = {
            "timestamp": now,
            "is_playing": is_playing,
            "pitch_hz": midi_to_freq(current_note) if current_note else None,
            "pitch_note": midi_to_name(current_note) if current_note else None,
            "pitch_confidence": 1.0 if is_playing else 0.0,
            "state": "playing" if is_playing else "silence",
            "consecutive_silence_ms": int((now - silence_start) * 1000) if silence_start > 0 else 0,
        }
        write_state(state)
        time.sleep(0.05)  # 20Hz update rate

if __name__ == "__main__":
    dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/midi3"
    run(dev)
