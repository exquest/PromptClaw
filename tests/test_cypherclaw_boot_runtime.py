"""Runtime checks for the CypherClaw boot script."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_boot_script_starts_presence_and_cadence_engines() -> None:
    script = (ROOT / "my-claw" / "scripts" / "cypherclaw_boot.sh").read_text()

    assert "presence_engine.py --interval 2.0" in script
    assert "cadence_engine.py --interval 5.0" in script
    assert "bash /home/user/cypherclaw/scripts/cypherclaw_av_boot.sh" in script
    assert "room_listener.py --no-jack" not in script
    assert "theramini_listener.py" in script
    assert "contact_listener.py" in script
    assert "input_monitor.py" in script
    assert "room_presence_daemon.py" in script
    assert "midi_keyboard_listener.py" in script
    assert "ensure_singleton_daemon" in script
    assert script.count("ensure_singleton_daemon") >= 5
    assert "observer_vision.py" in script
    assert "room_presence_daemon.py --observer-frame-only" in script
    assert "cypherclaw-observer-ollama.service" in script
    assert "OBSERVER_OLLAMA_URLS=http://127.0.0.1:11435/api/chat,http://127.0.0.1:11434/api/chat" in script
    assert "ARCHIVE_ROOT=$(archive_root)" in script
    assert '"/mnt/archive/cypherclaw"' in script or "/mnt/archive/cypherclaw" in script
    assert "PORCH_CAPTURE_DIR" in script
    assert "SIDE_CAPTURE_DIR" in script
    assert "/tmp/porch_eye_captures" not in script
    assert "/tmp/side_eye_captures" not in script
    assert "/home/user/cypherclaw/tools/senseweave/porch_eye.py" in script
    assert "side_eye_state.json" in script
    assert "from garden_watcher import update_garden_state,write_garden_state" in script


def test_start_displays_uses_dual_head_xorg_recovery_path() -> None:
    script = (ROOT / "my-claw" / "scripts" / "start_displays.sh").read_text()

    assert "xorg-dual.conf" in script
    assert "vt1" in script
    assert "sudo -n Xorg :0" in script


def test_xorg_dual_config_targets_live_dp_outputs() -> None:
    config = (ROOT / "my-claw" / "scripts" / "xorg-dual.conf").read_text()

    assert 'Option "Monitor-DP-2" "FaceMon"' in config
    assert 'Option "Monitor-DP-0" "GalleryMon"' in config


def test_observer_ollama_service_runs_on_dedicated_port_as_ollama() -> None:
    unit = (ROOT / "my-claw" / "systemd" / "cypherclaw-observer-ollama.service").read_text()

    assert "Description=CypherClaw Observer Ollama" in unit
    assert "User=ollama" in unit
    assert "Group=ollama" in unit
    assert 'Environment="OLLAMA_HOST=127.0.0.1:11435"' in unit
    assert 'Environment="OLLAMA_MODELS=/usr/share/ollama/.ollama/models"' in unit
    assert "ExecStart=/usr/local/bin/ollama serve" in unit


def test_sample_capture_service_runs_under_repo_venv_with_jack_dependency() -> None:
    unit = (ROOT / "my-claw" / "systemd" / "cypherclaw-sample-capture.service").read_text()

    assert "Description=CypherClaw Sample Capture" in unit
    assert "After=cypherclaw-jack.service" in unit
    assert "Requires=cypherclaw-jack.service" in unit
    assert "User=user" in unit
    assert "WorkingDirectory=/home/user/cypherclaw" in unit
    assert "ExecStart=/home/user/cypherclaw/.venv/bin/python3 /home/user/cypherclaw/tools/sample_capture_daemon.py" in unit
    assert "Restart=always" in unit
    assert "LimitMEMLOCK=infinity" in unit


def test_generation_worker_service_runs_queue_worker_with_budget_env() -> None:
    unit = (
        ROOT / "my-claw" / "systemd" / "cypherclaw-generation-worker.service"
    ).read_text()

    assert "Description=CypherClaw Generation Worker" in unit
    assert "After=cypherclaw-jack.service network-online.target" in unit
    assert "User=user" in unit
    assert "EnvironmentFile=/home/user/cypherclaw/.env" in unit
    assert (
        "ExecStart=/home/user/cypherclaw/.venv/bin/python3 "
        "/home/user/cypherclaw/tools/generation_worker.py"
    ) in unit
    assert "Restart=always" in unit
    assert "RestartSec=10" in unit
    assert "LimitMEMLOCK=infinity" in unit
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "ReadWritePaths=/home/user/cypherclaw-data" in unit


def test_boot_script_starts_sample_capture_service() -> None:
    script = (ROOT / "my-claw" / "scripts" / "cypherclaw_boot.sh").read_text()

    assert "ensure_sample_capture_service" in script
    assert "systemctl start cypherclaw-sample-capture.service" in script
