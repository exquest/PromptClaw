#!/bin/bash
# Pop-free composer restart: mute → kill → start → unmute

# Mute speakers
amixer -D hw:USB sset 'Line 01 Mute' on 2>/dev/null
amixer -D hw:USB sset 'Line 02 Mute' on 2>/dev/null

# Kill old composer and clear synths
pkill -9 -f duet_composer 2>/dev/null
sleep 0.5

# Reload SynthDefs from disk
DEFDIR=/home/user/cypherclaw/tools/senseweave/synthesis/synthdefs
/home/user/cypherclaw/.venv/bin/python3 -c "
from pythonosc import udp_client
import os, time
c = udp_client.SimpleUDPClient('127.0.0.1', 57110)
for f in sorted(os.listdir('${DEFDIR}')):
    if f.endswith('.scsyndef'):
        data = open(os.path.join('${DEFDIR}', f), 'rb').read()
        c.send_message('/d_recv', [data])
        time.sleep(0.05)
"
sleep 0.3

/home/user/cypherclaw/.venv/bin/python3 -c "
from pythonosc import udp_client
c = udp_client.SimpleUDPClient('127.0.0.1', 57110)
c.send_message('/g_freeAll', [0])
import time; time.sleep(0.3)
c.send_message('/s_new', ['sw_master_smooth', 99999, 1, 0,
    'drive', 0.15, 'warmth', 0.35, 'reverb', 0.05, 'room', 0.5, 'amp', 5.0])
"
sleep 0.5

# Start new composer
export PYTHONPATH=/home/user/cypherclaw/src:/home/user/cypherclaw/tools
nohup /home/user/cypherclaw/.venv/bin/python3 -u /home/user/cypherclaw/tools/duet_composer.py > /tmp/duet_composer.log 2>&1 &
echo "Composer PID: $!"

# Wait for first notes to start
sleep 4

# Unmute
amixer -D hw:USB sset 'Line 01 Mute' off 2>/dev/null
amixer -D hw:USB sset 'Line 02 Mute' off 2>/dev/null
echo "Unmuted — pop-free restart complete"
