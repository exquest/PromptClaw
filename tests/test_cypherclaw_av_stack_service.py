"""Regression checks for the persistent CypherClaw AV boot stack."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_av_boot_script_starts_runtime_stack_detached() -> None:
    script = _read("my-claw/scripts/cypherclaw_av_boot.sh")

    assert "DISPLAY=:0" in script
    assert "XDG_RUNTIME_DIR=/run/user/1000" in script
    assert "ensure_display_stack" in script
    assert "bash /home/user/cypherclaw/scripts/start_displays.sh" in script
    assert "openbox" in script
    assert "bash /home/user/cypherclaw/scripts/start_audio.sh" in script
    assert "bash /home/user/cypherclaw/scripts/restart_composer.sh" in script
    assert "wait_for_existing_core_stack" in script
    assert "wait_for_sc_port" in script
    assert "preferred_self_listener_backend" in script
    assert "printf 'jack" in script
    assert "SELF_LISTENER_CAPTURE_BACKEND=" in script
    assert "SELF_LISTENER_PORT=SuperCollider:out_1" in script
    assert "start_daemon_if_missing" in script
    assert "dedupe_daemon" in script
    assert "kill -KILL" in script
    assert "DISPLAY=:0.0" in script
    assert "DISPLAY=:0.1" in script
    assert "FACE_DISPLAY=1 SDL_AUDIODRIVER=dummy" in script
    assert "self_listener.py" in script
    assert "sample_playback_engine.py" in script
    assert "room_listener.py" in script
    assert "gallery_x11.py" in script
    assert "nohup setsid" in script
    assert script.count("/home/user/cypherclaw/tools/face_display.py") >= 2
    assert script.count("/home/user/cypherclaw/tools/gallery_x11.py") >= 2


def test_av_stack_service_targets_graphical_boot_as_user() -> None:
    unit = _read("my-claw/systemd/cypherclaw-av-stack.service")

    assert "Description=CypherClaw AV Stack" in unit
    assert "User=user" in unit
    assert "After=display-manager.service network-online.target sound.target" in unit
    assert "ExecStart=/home/user/cypherclaw/scripts/cypherclaw_av_boot.sh" in unit
    assert "Type=oneshot" in unit
    assert "RemainAfterExit=yes" in unit
    assert "WantedBy=graphical.target" in unit


def test_av_boot_normalizes_live_dual_head_modes() -> None:
    script = _read("my-claw/scripts/cypherclaw_av_boot.sh")

    assert "xrandr --screen 0 --output DP-2 --mode 1280x1024 --rate 60" in script
    assert "xrandr --screen 1 --output DP-0 --mode 3840x2160 --rate 60" in script
