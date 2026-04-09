# Home Visit Playbook — CypherClaw Hardware Tasks

Mechanical scripts for tasks that need physical access to CypherClaw. Each section is designed to run **linearly** — read the command, run it, verify the expected output, move on. No thinking required.

**Before you start any section:**
- SSH into CypherClaw: `ssh cypherclaw`
- Navigate to the cypherclaw dir: `cd /home/user/cypherclaw`
- Check daemons are up: `pgrep -f cypherclaw_daemon | head -3`
- Have your phone ready for the Telegram bot confirmations

---

## Task 1 — APC-006: Debug NS8360 Thermal Printer

**Goal:** Get the thermal printer producing legible output.
**Time:** 15-30 minutes.
**Risk:** Low — printer output only, no system impact.

### Known Facts
- Device: NS8360 (or similar generic USB ESC/POS printer, VID 09c6:0248)
- Linux device nodes: `/dev/usb/lp0` and `/dev/usb/lp1` (two printers? or printer+phantom)
- Existing module: `/home/user/cypherclaw/src/cypherclaw/thermal_printer.py`
- It's been reported as "sending data but no output"

### Step 1.1 — Identify which device is the real printer

```bash
# Check both device nodes for lsusb info
ls -la /dev/usb/lp0 /dev/usb/lp1
lsusb | grep -i printer
udevadm info /dev/usb/lp0 | grep -E "ID_MODEL|ID_VENDOR|ID_SERIAL"
udevadm info /dev/usb/lp1 | grep -E "ID_MODEL|ID_VENDOR|ID_SERIAL" 2>/dev/null
```

**Expected:** One is the NS8360, the other might be a phantom from a previous install. Note which one is real.

### Step 1.2 — Check permissions

```bash
# Is the user in the lp group?
groups | tr ' ' '\n' | grep -w lp
# Check device ownership
ls -la /dev/usb/lp0
```

**If not in lp group:** `sudo usermod -aG lp $USER && newgrp lp` (or reboot)
**If device is root-only:** Add a udev rule:
```bash
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="09c6", MODE="0666"' | sudo tee /etc/udev/rules.d/99-thermal-printer.rules
sudo udevadm control --reload && sudo udevadm trigger
```

### Step 1.3 — Raw ESC/POS smoke test

Bypass all Python. Just write bytes:

```bash
# Test 1: Plain text with initialize + line feed
printf '\x1b@Hello printer\n\n\n\n' > /dev/usb/lp0

# Test 2: If nothing prints, try the other device
printf '\x1b@Hello printer\n\n\n\n' > /dev/usb/lp1

# Test 3: With explicit cut
printf '\x1b@Hello from CypherClaw\n\n\n\x1dV\x00' > /dev/usb/lp0
```

**Watch the printer.** If paper advances and text appears, the hardware is fine — the problem is in our Python code. If nothing happens:
- Power cycle the printer (plug/unplug USB)
- Check paper is loaded and not jammed
- Try a different USB port/cable
- Run `dmesg | tail -20` immediately after plugging in to see what the kernel detects

### Step 1.4 — Test the Python path

```bash
/home/user/cypherclaw/.venv/bin/python3 -c "
import sys
sys.path.insert(0, '/home/user/cypherclaw/src')
from cypherclaw.thermal_printer import ThermalPrinter
p = ThermalPrinter(device='/dev/usb/lp0')
p.print_text('Python path works')
"
```

**If raw bytes work but Python doesn't:**
- Compare what bytes the Python module actually writes
- Add `print(repr(...))` before the write calls to inspect
- Check for Unicode issues — thermal printers use CP437/Japanese codepage, not UTF-8

### Step 1.5 — Print a real sticker

```bash
# Find a recent dream sticker PNG
ls -lt /home/user/cypherclaw-data/gallery/stickers/*.png 2>/dev/null | head -3

# Print one via the full pipeline
/home/user/cypherclaw/.venv/bin/python3 -c "
import sys
sys.path.insert(0, '/home/user/cypherclaw/src')
sys.path.insert(0, '/home/user/cypherclaw/tools')
from cypherclaw.thermal_printer import ThermalPrinter
from PIL import Image
p = ThermalPrinter(device='/dev/usb/lp0')
img = Image.open('/PATH/TO/STICKER.png')
p.print_image(img)
"
```

### Step 1.6 — Mark APC-006 complete

Once you have a working print, tell CypherClaw:
- Telegram: `set APC-006 complete — NS8360 printing ESC/POS and PIL images`
- Or on the face keyboard: `/task APC-006 done`

---

## Task 2 — APC-012: Measure Room Impulse Response

**Goal:** Capture the room's acoustic fingerprint so we can build convolution reverb from it.
**Time:** 15 minutes (measurement) + 10 minutes (processing).
**Risk:** LOW volume — we're playing a sweep at conversation level, not loud.
**Requires:** Quiet room. **Marissa, dogs, Julia NOT home.** House HVAC off if possible.

### Prerequisites (verify before starting)

```bash
# Room must be empty and quiet
cat /tmp/organism_state.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('collective_mood',{}))"
# presence should be: someone_here: false

# PipeWire + scsynth must be up
pgrep -f scsynth && echo "scsynth running"
pw-jack jack_lsp | grep SuperCollider

# Current master amp (we'll want this BACK after)
python3 -c "
from pythonosc.udp_client import SimpleUDPClient
c = SimpleUDPClient('127.0.0.1', 57110)
# Save current state
" 2>&1 | head -5

# Contact mics must be connected to Scarlett inputs 1+2
# (They were disconnected from SC earlier — we'll use an ad-hoc recording)
arecord -l | grep -i scarlett
```

### Step 2.1 — Mute the composer

You don't want the composer playing while you're measuring the room.

```bash
# Pause the duet composer
pkill -STOP -f duet_composer.py
# Verify it's paused (status T)
ps -o state,comm -p $(pgrep -f duet_composer.py) | head -5
```

### Step 2.2 — Generate a swept sine file

We'll use ffmpeg to create a clean log sweep at -20 dBFS. Safe level.

```bash
mkdir -p /tmp/room_ir
cd /tmp/room_ir

# 10-second log sweep 20Hz → 20kHz, -20dBFS, 48kHz stereo
ffmpeg -y -f lavfi -i "sine=frequency=20:beep_factor=1:duration=10" sweep_dummy.wav 2>&1 | tail -5

# Actually use sox for a proper log sweep (install if needed)
which sox || sudo apt install -y sox
sox -n -r 48000 -c 2 sweep.wav synth 10 sine 20/20000 gain -20

# Verify
ls -la sweep.wav
sox sweep.wav -n stat 2>&1 | head -5
```

**Expected:** `sweep.wav` is ~960 KB, 10 seconds stereo at 48kHz.

### Step 2.3 — Simultaneous play + record

The trick: play the sweep through the Scarlett outputs, record through the contact mics on inputs 1+2, at the **same time**. We'll use two terminal sessions or a background job.

```bash
# Start recording contact mics (background)
arecord -D plughw:USB -f S24_LE -r 48000 -c 2 -d 12 /tmp/room_ir/response.wav &
RECORD_PID=$!
sleep 0.5  # let arecord settle

# Play the sweep
aplay -D plughw:USB /tmp/room_ir/sweep.wav

# Wait for recording to finish
wait $RECORD_PID

# Verify both files exist and have content
ls -la /tmp/room_ir/sweep.wav /tmp/room_ir/response.wav
sox /tmp/room_ir/response.wav -n stat 2>&1 | grep "Mean amplitude"
```

**What you should hear:** A 10-second sweep from a low rumble to a high whistle, at conversational volume. If it's loud, abort and lower the output level via `wpctl set-volume @DEFAULT_AUDIO_SINK@ 40%`.

### Step 2.4 — Extract the impulse response via deconvolution

```bash
/home/user/cypherclaw/.venv/bin/python3 << 'PYEOF'
import numpy as np
import scipy.io.wavfile as wav
import scipy.signal as sig

# Load sweep (clean) and response (room-coloured)
sweep_rate, sweep = wav.read('/tmp/room_ir/sweep.wav')
response_rate, response = wav.read('/tmp/room_ir/response.wav')

# Convert to mono float
if sweep.ndim > 1: sweep = sweep.mean(axis=1)
if response.ndim > 1: response = response.mean(axis=1)
sweep = sweep.astype(np.float32) / np.max(np.abs(sweep))
response = response.astype(np.float32) / np.max(np.abs(response))

# Inverse-filter deconvolution
# IR = ifft(fft(response) / fft(sweep))  but stabilized
from scipy.fftpack import fft, ifft
S = fft(sweep, n=len(response))
R = fft(response)
ir = np.real(ifft(R / (S + 1e-6)))

# Trim to the first ~1 second (typical room IR)
ir = ir[:48000]
# Normalize
ir = ir / np.max(np.abs(ir))

# Save as 48kHz mono WAV
wav.write('/home/user/cypherclaw-data/room_ir.wav', 48000, (ir * 32767).astype(np.int16))

print(f"IR extracted: {len(ir)} samples ({len(ir)/48000:.2f}s)")
print(f"Peak: {np.max(np.abs(ir)):.3f}")
print(f"RT60 estimate: {(np.sum(ir**2) / np.max(ir**2)) / 48000:.2f}s")
print("Saved to /home/user/cypherclaw-data/room_ir.wav")
PYEOF
```

**Expected:** `room_ir.wav` is ~96 KB, ~1 second mono, peaks near the start and tail of decay.

### Step 2.5 — Listen to it

```bash
aplay /home/user/cypherclaw-data/room_ir.wav
```

**What you should hear:** A quick "pop" or "crack" followed by ~1 second of room reverb tail. If it sounds like noise or silence, the deconvolution didn't work — check that sweep played through speakers and contact mics were recording the room (not the direct signal).

### Step 2.6 — Resume the composer

```bash
pkill -CONT -f duet_composer.py
# Verify it's running again (status S)
ps -o state,comm -p $(pgrep -f duet_composer.py) | head -5
```

### Step 2.7 — Mark APC-012 complete

- `/task APC-012 done — IR saved to /home/user/cypherclaw-data/room_ir.wav`
- The SynthDef work (APC-013) can happen later from the MacBook — it just needs the IR file.

---

## Task 3 — APC-009: Welcome Sticker

**Goal:** Print a personalized welcome sticker when a known visitor arrives.
**Prerequisites:** APC-006 (printer working), APC-001/002/003 (face recognition — NOT DONE).

**Status:** Skip this on today's visit. Face recognition isn't built yet — it's in the SDP pipeline queue but hasn't been processed. Come back to this after both the printer works AND the SDP has completed APC-001 through APC-005.

---

## General Troubleshooting

### If CypherClaw is in a weird state when you arrive
```bash
ssh cypherclaw
sudo systemctl status cypherclaw-sdp-runner
sudo systemctl status cypherclaw-daemon 2>/dev/null
pgrep -af face_display | head -3
pgrep -af duet_composer | head -3
pgrep -af scsynth | head -3
```

### If the printer beeps or spits garbage
```bash
# Power cycle it (unplug USB 5s, replug)
# Reinit
printf '\x1b@' > /dev/usb/lp0
# Feed paper
printf '\n\n\n\n\n' > /dev/usb/lp0
```

### If SuperCollider is stuck or popping
```bash
/home/user/cypherclaw/scripts/restart_composer.sh
```

### If you need to test without affecting the live composer
```bash
# Clone scsynth state to a test port
pw-jack chrt -f 40 scsynth -u 57120 -a 1024 -m 65536 -D 0 -R 0 -o 2 -i 2 -S 48000 &
# Work on port 57120 instead of 57110
# Kill when done: pkill -f "scsynth.*57120"
```

---

## After the Visit

Back at the MacBook:
1. Pull any changes: `cd ~/Programming/PromptClaw && git pull`
2. If you created `/home/user/cypherclaw-data/room_ir.wav`, scp it over:
   ```bash
   scp cypherclaw:/home/user/cypherclaw-data/room_ir.wav my-claw/data/
   ```
3. Mark the task(s) complete in SDP if the pipeline didn't auto-detect it
4. Write a brief "what I learned" note in `docs/home-visit-log.md` so the next visit builds on this one
