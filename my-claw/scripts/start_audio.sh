#!/bin/bash
# Start PipeWire + SuperCollider audio chain
# Updated 2026-04-07: PipeWire replaces JACK (xruns produce silence, not clicks)
sleep 5

# Ensure PipeWire is running
systemctl --user start pipewire wireplumber 2>/dev/null || true
sleep 3

# Launch scsynth through PipeWire's JACK shim
export PIPEWIRE_LATENCY=4096/48000
pw-jack chrt -f 40 scsynth -u 57110 -a 1024 -m 65536 -D 0 -R 0 -o 6 -i 8 -S 48000 &
sleep 4

# Connect SC to Scarlett (PipeWire port names)
pw-jack jack_connect "SuperCollider:out_1" "Scarlett 4i4 USB Analog Surround 4.0:playback_FL"
pw-jack jack_connect "SuperCollider:out_2" "Scarlett 4i4 USB Analog Surround 4.0:playback_FR"

# Connect Scarlett inputs to SC
# pw-jack jack_connect "Scarlett 4i4 USB Analog Surround 2.1:capture_FL" "SuperCollider:in_1"
# pw-jack jack_connect "Scarlett 4i4 USB Analog Surround 2.1:capture_FR" "SuperCollider:in_2"

# Load SynthDefs
DEFDIR=/home/user/cypherclaw/tools/senseweave/synthesis/synthdefs
/home/user/cypherclaw/.venv/bin/python3 -c "
from pythonosc import udp_client
import os, time
c = udp_client.SimpleUDPClient('127.0.0.1', 57110)
for f in sorted(os.listdir('${DEFDIR}')):
    if f.endswith('.scsyndef'):
        data = open(os.path.join('${DEFDIR}', f), 'rb').read()
        c.send_message('/d_recv', [data])
        time.sleep(0.1)
# Master chain with internal LFO EQ drift
c.send_message('/s_new', ['sw_master_smooth', 99999, 1, 0,
    'drive', 0.15, 'warmth', 0.35, 'reverb', 0.05, 'room', 0.5, 'amp', 5.0])
"

# Zero Scarlett analog inputs (prevent Theramini pass-through)
for mix in A B C D E F; do
    for inp in 01 02 03 04; do
        amixer -D hw:USB sset "Mix $mix Input $inp" 0 2>/dev/null
    done
done
amixer -D hw:USB sset 'Analogue Output 01' 'PCM 1' 2>/dev/null
amixer -D hw:USB sset 'Analogue Output 02' 'PCM 2' 2>/dev/null
amixer -D hw:USB sset 'Standalone' off 2>/dev/null

echo "$(date) PipeWire audio chain started" >> /tmp/audio_boot.log
