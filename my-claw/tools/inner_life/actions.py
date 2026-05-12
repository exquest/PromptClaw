"""Actions — dispatch system for inner life decisions.

Each action type writes to an existing communication channel.
No new protocols — just files, OSC, and the daemon inbox.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from .inner_state import InnerState


MESSAGE_BUS = "/tmp/cypherclaw_messages.jsonl"
DAEMON_INBOX = "/run/cypherclaw-tmp/inbox.jsonl"
MUSIC_INFLUENCE = "/tmp/inner_life_music.json"
PRINTER_DEVICE = "/dev/usb/lp0"


@dataclass
class Action:
    """Something the inner life wants to do."""
    action_type: str    # face_message, music_influence, print_receipt,
                        # daemon_inbox, journal_entry, request_art
    payload: dict
    cooldown_key: str   # which InnerState cooldown field to check
    min_cooldown_s: float = 60.0
    priority: int = 1   # 0=background, 1=normal, 2=urgent


def dispatch(action: Action, inner: InnerState) -> bool:
    """Execute an action. Returns True if successful."""
    if not inner.cooldown_ok(action.cooldown_key, action.min_cooldown_s):
        return False

    try:
        dispatchers = {
            "face_message": _dispatch_face,
            "music_influence": _dispatch_music,
            "print_receipt": _dispatch_print,
            "daemon_inbox": _dispatch_daemon,
            "journal_entry": _dispatch_journal,
            "request_art": _dispatch_art,
        }
        fn = dispatchers.get(action.action_type)
        if fn and fn(action.payload):
            inner.mark_cooldown(action.cooldown_key)
            return True
    except Exception:
        pass
    return False


def _dispatch_face(payload: dict) -> bool:
    """Write a message to the face display bus."""
    text = payload.get("text", "")
    role = payload.get("role", "system")
    if not text:
        return False
    msg = json.dumps({"text": text[:200], "role": role, "time": time.time()})
    with open(MESSAGE_BUS, "a") as f:
        f.write(msg + "\n")
    return True


def _dispatch_music(payload: dict) -> bool:
    """Write music suggestions for the composer to read."""
    data = {
        "timestamp": time.time(),
        "suggested_key": payload.get("key"),
        "suggested_energy": payload.get("energy"),
        "suggest_silence": payload.get("silence", False),
        "arc_phase": payload.get("arc_phase"),
        "source": "inner_life",
    }
    tmp = MUSIC_INFLUENCE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, MUSIC_INFLUENCE)
    return True


def _dispatch_print(payload: dict) -> bool:
    """Print to the thermal receipt printer."""
    text = payload.get("text", "")
    if not text:
        return False
    try:
        import usb.core
        import usb.util
        dev = usb.core.find(idVendor=0x09c6, idProduct=0x0248)
        if not dev:
            return False
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
        dev.set_configuration()
        cfg = dev.get_active_configuration()
        intf = cfg[(0, 0)]
        ep = usb.util.find_descriptor(
            intf, custom_match=lambda e: usb.util.endpoint_direction(
                e.bEndpointAddress) == usb.util.ENDPOINT_OUT)

        # ESC/POS: init + center + text + feed + cut
        ep.write(b"\x1b\x40")  # init
        ep.write(b"\x1b\x61\x01")  # center
        for line in text.split("\n"):
            ep.write((line + "\n").encode("ascii", errors="replace"))
        ep.write(b"\n\n\n")
        ep.write(b"\x1d\x56\x41\x00")  # partial cut

        dev.reset()
        dev.attach_kernel_driver(0)
        return True
    except Exception:
        return False


def _dispatch_daemon(payload: dict) -> bool:
    """Send a message through the daemon for cloud agent processing."""
    text = payload.get("text", "")
    if not text:
        return False
    msg = json.dumps({"text": text, "source": "inner_life", "time": time.time()})
    with open(DAEMON_INBOX, "a") as f:
        f.write(msg + "\n")
    return True


def _dispatch_journal(payload: dict) -> bool:
    """Append to the sensory journal."""
    event_type = payload.get("event_type", "inner:observation")
    detail = payload.get("detail", "")
    entry = json.dumps({
        "timestamp": time.time(),
        "event_type": event_type,
        "detail": detail,
        "source": "inner_life",
    })
    journal_path = "/home/user/cypherclaw-data/state/sensory_journal.jsonl"
    try:
        with open(journal_path, "a") as f:
            f.write(entry + "\n")
        return True
    except OSError:
        return False


def _dispatch_art(payload: dict) -> bool:
    """Request a new art piece by writing a trigger file."""
    trigger = {
        "requested_at": time.time(),
        "reason": payload.get("reason", "arc climax"),
        "mood": payload.get("mood"),
        "source": "inner_life",
    }
    path = "/tmp/art_request.json"
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(trigger, f)
    os.replace(tmp, path)
    return True
