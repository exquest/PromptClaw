#!/bin/bash
# CypherClaw full boot script — starts X, displays, audio, all daemons
# Run from /etc/rc.local or a systemd service as user

set -e
VENV=/home/user/cypherclaw/.venv/bin/python3
LOG=/tmp/cypherclaw_boot.log
exec > $LOG 2>&1

echo "$(date) CypherClaw boot starting..."

# Wait for PipeWire
sleep 5

# Start X on vt1 if not already running
if [ ! -f /tmp/.X0-lock ]; then
    sudo Xorg :0 -keeptty vt1 &
    sleep 3
fi
export DISPLAY=:0

# Start window manager
openbox &
sleep 1

# Configure monitors
xrandr --output DP-2 --mode 1280x1024 --pos 0x0 --output DP-0 --mode 3840x2160 --pos 1280x0 --primary 2>/dev/null || true
sleep 1

# Start audio chain
bash /home/user/cypherclaw/scripts/start_audio.sh
sleep 5

# Start composer
bash /home/user/cypherclaw/scripts/restart_composer.sh
sleep 2

# Displays
FACE_DISPLAY=1 nohup $VENV /home/user/cypherclaw/tools/face_display.py &>/dev/null &
nohup $VENV /home/user/cypherclaw/tools/gallery_x11.py &>/dev/null &

# Cameras
nohup $VENV /home/user/cypherclaw/tools/senseweave/porch_eye.py \
    "rtsps://192.168.1.1:7441/cY6cUV7hxEIy8k1v?enableSrtp" \
    --capture-dir /tmp/porch_eye_captures --interval 30 &>/dev/null &
nohup $VENV -c "
import sys;sys.path.insert(0,'/home/user/cypherclaw/tools/senseweave')
import porch_eye;porch_eye.DEFAULT_STATE_FILE='/tmp/side_eye_state.json'
porch_eye.run_porch_eye('rtsps://192.168.1.1:7441/oEUVMaB2G3pwbY42?enableSrtp','/tmp/side_eye_captures',interval=30.0)
" &>/dev/null &
nohup $VENV /home/user/cypherclaw/tools/observer_vision.py &>/dev/null &

# Sensors
nohup $VENV /home/user/cypherclaw/tools/theramini_midi.py /dev/midi3 &>/dev/null &
nohup $VENV /home/user/cypherclaw/tools/midi_keyboard_listener.py &>/dev/null &
nohup $VENV /home/user/cypherclaw/tools/input_monitor.py &>/dev/null &
nohup $VENV -c "
import sys;sys.path.insert(0,'/home/user/cypherclaw/tools/senseweave')
from sensor_fusion import run_fusion_loop;run_fusion_loop(interval=2.0)
" &>/dev/null &
nohup $VENV -c "
import sys,json,time,os
sys.path.insert(0,'/home/user/cypherclaw/tools/senseweave')
from garden_watcher import update_garden_state,write_garden_state
while True:
    try:
        b=0.5
        for cam in ['/tmp/porch_eye_state.json','/tmp/side_eye_state.json']:
            try:
                d=json.loads(open(cam).read())
                if d.get('brightness',0)>0:b=d['brightness'];break
            except:pass
        write_garden_state(update_garden_state(b))
    except:pass
    time.sleep(30)
" &>/dev/null &
nohup $VENV -c "
import subprocess,json,os,time
from PIL import Image
while True:
    try:
        subprocess.run(['ffmpeg','-y','-f','v4l2','-i','/dev/video0','-frames:v','1','-update','1','/tmp/room_frame.jpg'],capture_output=True,timeout=10)
        if os.path.exists('/tmp/room_frame.jpg') and os.path.getsize('/tmp/room_frame.jpg')>1000:
            img=Image.open('/tmp/room_frame.jpg').convert('L');px=list(img.getdata());b=sum(px)/(len(px)*255.0)
            s={'brightness':b,'motion':False,'someone_here':b>0.15,'timestamp':time.time()}
            with open('/tmp/room_presence.json.tmp','w') as f:json.dump(s,f)
            os.replace('/tmp/room_presence.json.tmp','/tmp/room_presence.json')
    except:pass
    time.sleep(15)
" &>/dev/null &

# Sensor daemons (startle, journal, self-listener)
bash /home/user/cypherclaw/tools/start_sensors.sh &

# Other daemons
nohup $VENV /home/user/cypherclaw/tools/nightly_reflection.py &>/dev/null &
nohup $VENV /home/user/cypherclaw/tools/senseweave/pareidolia_art_engine.py &>/dev/null &

# Main daemon (chat system)
cd /home/user/cypherclaw && PYTHONPATH=src nohup $VENV -m cypherclaw.daemon &>/dev/null &

# Boost volume
sleep 5
$VENV -c "
from pythonosc.udp_client import SimpleUDPClient
c = SimpleUDPClient('127.0.0.1', 57110)
c.send_message('/n_set', [99999, 'amp', 5.0])
" 2>/dev/null
wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.5 2>/dev/null

echo "$(date) CypherClaw boot complete — all systems online"

# Focus the face display window for keyboard input
sleep 3
DISPLAY=:0 xdotool mousemove 640 512 click 1 2>/dev/null

# Inner life — the mind
nohup $VENV -u -m inner_life.main &>/dev/null &

# Archive daemon — records everything
nohup $VENV -u /home/user/cypherclaw/tools/archive_daemon.py &>/dev/null &

# Hide mouse cursor
DISPLAY=:0 unclutter -idle 0 -root &>/dev/null &
