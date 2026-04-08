"""Self-listener — records own audio output and analyzes it.

Uses pw-cat to capture from the monitor of the Scarlett output,
analyzes amplitude and pitch, writes state for continuous learner.
"""
import json, os, struct, subprocess, sys, time, wave
sys.path.insert(0, os.path.dirname(__file__))
from audio_analysis import detect_amplitude, detect_pitch_autocorrelation

STATE = "/tmp/self_listen.json"
CLIP = "/tmp/self_listen.wav"

while True:
    try:
        # Record SC output via pw-jack jack_rec
        subprocess.run(
            ["pw-jack", "jack_rec", "-f", CLIP, "-d", "3", "-b", "16",
             "SuperCollider:out_1"],
            timeout=5, capture_output=True,
        )

        if os.path.exists(CLIP) and os.path.getsize(CLIP) > 1000:
            try:
                w = wave.open(CLIP)
                sr, n = w.getframerate(), w.getnframes()
                nch = w.getnchannels()
                raw = w.readframes(n)
                w.close()
                fmt = f"<{n * nch}h"
                if len(raw) >= struct.calcsize(fmt):
                    samples = list(struct.unpack(fmt, raw[:struct.calcsize(fmt)]))
                    mono = [samples[i] for i in range(0, len(samples), nch)]
                    amp_result = detect_amplitude(mono)
                    amp = amp_result[0] if isinstance(amp_result, tuple) else amp_result
                    pitch = detect_pitch_autocorrelation(mono, sr) if amp > 0.01 else (0, 0)
                    state = {"timestamp": time.time(), "amplitude": amp,
                             "pitch_hz": pitch[0], "pitch_confidence": pitch[1],
                             "is_playing": amp > 0.005, "is_silent": amp < 0.001}
                else:
                    state = {"timestamp": time.time(), "is_silent": True, "amplitude": 0,
                             "error": "short_wav"}
            except Exception as e:
                state = {"timestamp": time.time(), "is_silent": True, "amplitude": 0,
                         "error": str(e)[:80]}
        else:
            state = {"timestamp": time.time(), "is_silent": True, "amplitude": 0,
                     "error": "no_capture"}

        tmp = STATE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, STATE)
    except Exception:
        pass
    time.sleep(10)
