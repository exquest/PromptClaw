#!/bin/bash
# Start X11 with dual displays: Gallery (3840x2160) + Face (1280x1024)
set -e

export HOME=/home/user

# Kill existing X if running
pkill -9 Xorg 2>/dev/null || true
sleep 1

# Unbind fbcon so X owns the GPU
echo 0 > /sys/class/vtconsole/vtcon1/bind 2>/dev/null || true

# Start X with our dual-head config. Rootless Xorg cannot claim the VT on this box,
# so prefer the original sudo/vt1 recovery path and only fall back to plain Xorg.
if sudo -n true 2>/dev/null; then
    sudo -n Xorg :0 -config /home/user/cypherclaw/scripts/xorg-dual.conf -novtswitch -keeptty vt1 &
else
    Xorg :0 -config /home/user/cypherclaw/scripts/xorg-dual.conf -novtswitch -keeptty vt1 &
fi
XPID=$!
sleep 3

export DISPLAY=:0

# Verify displays
xrandr --screen 0 2>&1 | head -5
xrandr --screen 1 2>&1 | head -5

# Disable screen blanking
xset -display :0 s off -dpms 2>/dev/null || true

echo "X started with PID $XPID"
echo "$XPID" > /tmp/cypherclaw-x.pid
