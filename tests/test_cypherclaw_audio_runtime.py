"""Regression checks for the CypherClaw audio runtime scripts."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_start_audio_autoloads_repo_synthdefs_and_avoids_disabled_loads() -> None:
    script = _read("my-claw/scripts/start_audio.sh")

    assert "JACK_NO_START_SERVER=1" in script
    assert ".local/share/SuperCollider" in script
    assert " -D 1 " in script
    assert " -D 0 " not in script
    assert "/d_recv" not in script


def test_start_audio_supports_real_jack_and_pipewire_jack_routing() -> None:
    script = _read("my-claw/scripts/start_audio.sh")

    assert 'system:playback_1' in script
    assert 'Scarlett 4i4 USB Analog Surround 4.0:playback_FL' in script
    assert 'jack_control start' in script
    assert 'jack_control dps device hw:USB' in script
    assert 'nohup jackdbus auto' in script
    assert 'pw-jack chrt -f 40 scsynth' in script
    assert 'Real JACK unavailable after scsynth start; retrying via pw-jack' in script
    assert 'real_jack_ready' in script


def test_restart_composer_uses_graceful_shutdown_and_verifies_new_process() -> None:
    script = _read("my-claw/scripts/restart_composer.sh")

    assert "pkill -TERM -f /home/user/cypherclaw/tools/duet_composer.py" in script
    assert "pkill -9 -f duet_composer" not in script
    assert "pgrep -f /home/user/cypherclaw/tools/duet_composer.py" in script
    assert "wait_for_composer" in script
    assert "nohup setsid /home/user/cypherclaw/.venv/bin/python3 -u /home/user/cypherclaw/tools/duet_composer.py" in script
    assert "reset_and_seed_master_chain" in script
    assert "seed_master_node_only" in script
    assert "sleep 1" in script
    assert "/d_recv" not in script


def test_boot_script_no_longer_blindly_n_sets_missing_master_node() -> None:
    script = _read("my-claw/scripts/cypherclaw_boot.sh")

    assert "c.send_message('/n_set', [99999, 'amp', 5.0])" not in script


def test_boot_script_delegates_core_av_ownership_to_av_boot_wrapper() -> None:
    script = _read("my-claw/scripts/cypherclaw_boot.sh")

    assert "bash /home/user/cypherclaw/scripts/cypherclaw_av_boot.sh" in script
    assert "bash /home/user/cypherclaw/scripts/start_audio.sh" not in script
    assert "bash /home/user/cypherclaw/scripts/restart_composer.sh" not in script
    assert "/home/user/cypherclaw/tools/face_display.py" not in script
    assert "/home/user/cypherclaw/tools/gallery_x11.py" not in script
    assert "/home/user/cypherclaw/tools/room_listener.py" not in script
    assert "/home/user/cypherclaw/tools/sample_playback_engine.py" not in script
