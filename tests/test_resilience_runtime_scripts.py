"""Tests for the first safe-runtime scripts and service wiring."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from importlib import import_module
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "my-claw" / "tools"
SYSTEMD_DIR = ROOT / "my-claw" / "systemd"

sys.path.insert(0, str(TOOLS_DIR))
runtime_checkpoint = import_module("runtime_checkpoint")


def _write_state_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE tasks (
            task_id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            tier TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE task_runs (
            task_run_id TEXT PRIMARY KEY,
            pipeline_run_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            lead_agent TEXT NOT NULL,
            verify_agent TEXT NOT NULL,
            work_result TEXT NOT NULL,
            verdict TEXT NOT NULL DEFAULT '',
            gate_passed INTEGER NOT NULL DEFAULT 0,
            duration_seconds REAL NOT NULL DEFAULT 0.0,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT ''
        );
        """
    )
    conn.execute(
        "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?)",
        (
            "T-001@20260401T000000Z",
            "Task one",
            "T1",
            "pending",
            "2026-04-01T00:00:00Z",
            "2026-04-01T00:00:00Z",
        ),
    )
    conn.commit()
    conn.close()


def _init_git_repo(project_root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(project_root)], check=True)
    subprocess.run(["git", "-C", str(project_root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(project_root),
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-qm",
            "init",
        ],
        check=True,
    )


def _healthy_project(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "AGENTS.md").write_text("home rules\n")
    (project_root / "pyproject.toml").write_text("[project]\nname='cypherclaw'\n")
    (project_root / "sdp.toml").write_text("state_db_path = '.sdp/state.db'\n")
    state_dir = project_root / ".sdp"
    state_dir.mkdir()
    promptclaw_dir = project_root / ".promptclaw"
    promptclaw_dir.mkdir()
    _write_state_db(state_dir / "state.db")
    promptclaw_db = sqlite3.connect(promptclaw_dir / "observatory.db")
    promptclaw_db.execute("CREATE TABLE observatory_events (id INTEGER PRIMARY KEY)")
    promptclaw_db.commit()
    promptclaw_db.close()
    _init_git_repo(project_root)
    tmp_root = tmp_path / "tmpfs"
    tmp_root.mkdir()
    return project_root, tmp_root


def _script_env(project_root: Path, tmp_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PROJECT_ROOT": str(project_root),
            "TMP_ROOT": str(tmp_root),
            "WORKDIR_NAME": "cypherclaw-work",
            "PYTHON_BIN": sys.executable,
            "SDP_CONFIG_SOURCE": str(project_root / "sdp.toml"),
        }
    )
    return env


def _write_fake_command(fake_bin: Path, name: str, body: str) -> None:
    path = fake_bin / name
    path.write_text(body)
    path.chmod(0o755)


def test_init_workdir_creates_tmpfs_clone_and_symlinks_authority_dbs(tmp_path: Path) -> None:
    project_root, tmp_root = _healthy_project(tmp_path)

    subprocess.run(
        ["bash", str(TOOLS_DIR / "init_workdir.sh")],
        check=True,
        env=_script_env(project_root, tmp_root),
    )

    workdir = tmp_root / "workdir" / "cypherclaw-work"
    assert (workdir / ".git").exists()
    assert (workdir / ".sdp" / "state.db").is_symlink()
    assert (workdir / ".sdp" / "state.db").resolve() == project_root / ".sdp" / "state.db"
    assert (workdir / ".promptclaw" / "observatory.db").is_symlink()
    assert (workdir / ".promptclaw" / "observatory.db").resolve() == project_root / ".promptclaw" / "observatory.db"
    assert (workdir / "sdp.toml").is_symlink()
    assert (workdir / "sdp.toml").resolve() == project_root / "sdp.toml"


def test_runner_launcher_refuses_to_start_during_maintenance(tmp_path: Path) -> None:
    project_root, tmp_root = _healthy_project(tmp_path)
    subprocess.run(
        ["bash", str(TOOLS_DIR / "init_workdir.sh")],
        check=True,
        env=_script_env(project_root, tmp_root),
    )
    (project_root / ".sdp" / "maintenance-mode.json").write_text(
        json.dumps({"active": True, "reason": "test", "actor": "pytest"})
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    called = tmp_path / "sdp-called.txt"
    _write_fake_command(
        fake_bin,
        "sdp-cli",
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" > {called}\n",
    )
    env = _script_env(project_root, tmp_root)
    env["SDP_BIN"] = str(fake_bin / "sdp-cli")

    result = subprocess.run(
        ["bash", str(TOOLS_DIR / "sdp_runner_launcher.sh")],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert not called.exists()
    assert "maintenance" in result.stderr.lower()


def test_runner_launcher_executes_sdp_cli_after_passing_preflight(tmp_path: Path) -> None:
    project_root, tmp_root = _healthy_project(tmp_path)
    subprocess.run(
        ["bash", str(TOOLS_DIR / "init_workdir.sh")],
        check=True,
        env=_script_env(project_root, tmp_root),
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    called = tmp_path / "sdp-called.txt"
    _write_fake_command(
        fake_bin,
        "sdp-cli",
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" > {called}\n",
    )
    env = _script_env(project_root, tmp_root)
    env["SDP_BIN"] = str(fake_bin / "sdp-cli")

    subprocess.run(
        ["bash", str(TOOLS_DIR / "sdp_runner_launcher.sh"), "--lead", "codex", "-v"],
        check=True,
        env=env,
    )

    assert called.read_text().strip() == "run --lead codex -v"


def test_safe_reboot_prepare_dry_run_creates_checkpoint_and_stops_services(tmp_path: Path) -> None:
    project_root, tmp_root = _healthy_project(tmp_path)
    subprocess.run(
        ["bash", str(TOOLS_DIR / "init_workdir.sh")],
        check=True,
        env=_script_env(project_root, tmp_root),
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    log_path = tmp_path / "systemctl.log"
    _write_fake_command(
        fake_bin,
        "systemctl",
        f"#!/usr/bin/env bash\nprintf 'systemctl %s\\n' \"$*\" >> {log_path}\n",
    )
    _write_fake_command(
        fake_bin,
        "reboot",
        f"#!/usr/bin/env bash\nprintf 'reboot %s\\n' \"$*\" >> {log_path}\n",
    )

    env = _script_env(project_root, tmp_root)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    subprocess.run(
        ["bash", str(TOOLS_DIR / "safe_reboot.sh"), "prepare", "--dry-run", "--actor", "pytest"],
        check=True,
        env=env,
    )

    recovery_dir = project_root / ".sdp" / "recovery"
    checkpoints = list(recovery_dir.glob("checkpoint-*.json"))
    assert checkpoints
    status = json.loads((project_root / ".sdp" / "maintenance-mode.json").read_text())
    assert status["active"] is True
    logged = log_path.read_text()
    assert "systemctl stop cypherclaw-sdp-runner.service" in logged
    assert "systemctl stop cypherclaw.service" in logged
    assert "reboot" not in logged


def test_safe_reboot_resume_validates_checkpoint_and_clears_maintenance(tmp_path: Path) -> None:
    project_root, tmp_root = _healthy_project(tmp_path)
    subprocess.run(
        ["bash", str(TOOLS_DIR / "init_workdir.sh")],
        check=True,
        env=_script_env(project_root, tmp_root),
    )
    checkpoint = runtime_checkpoint.write_checkpoint(project_root, timestamp="20260401T120000Z")
    (project_root / ".sdp" / "maintenance-mode.json").write_text(
        json.dumps({"active": True, "reason": "test", "actor": "pytest"})
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    log_path = tmp_path / "systemctl.log"
    _write_fake_command(
        fake_bin,
        "systemctl",
        f"#!/usr/bin/env bash\nprintf 'systemctl %s\\n' \"$*\" >> {log_path}\n",
    )
    env = _script_env(project_root, tmp_root)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    subprocess.run(
        [
            "bash",
            str(TOOLS_DIR / "safe_reboot.sh"),
            "resume",
            "--dry-run",
            "--actor",
            "pytest",
            "--checkpoint",
            str(checkpoint),
        ],
        check=True,
        env=env,
    )

    status = json.loads((project_root / ".sdp" / "maintenance-mode.json").read_text())
    assert status["active"] is False
    logged = log_path.read_text()
    assert "systemctl start cypherclaw.service" in logged
    assert "systemctl start cypherclaw-sdp-runner.service" in logged


def test_systemd_units_wire_bootstrap_and_runner_services() -> None:
    bootstrap_unit = (SYSTEMD_DIR / "cypherclaw-bootstrap.service").read_text()
    runner_unit = (SYSTEMD_DIR / "cypherclaw-sdp-runner.service").read_text()

    assert "ExecStart=/home/user/cypherclaw/tools/init_workdir.sh" in bootstrap_unit
    assert "Before=cypherclaw.service cypherclaw-sdp-runner.service" in bootstrap_unit
    assert "ExecStart=/home/user/cypherclaw/tools/sdp_runner_launcher.sh" in runner_unit
    assert "After=cypherclaw-bootstrap.service cypherclaw.service" in runner_unit
    assert "Restart=on-failure" in runner_unit


def test_boot_hardening_no_longer_restores_state_or_starts_runner_directly() -> None:
    boot_hardening = (TOOLS_DIR / "boot_hardening.sh").read_text()

    assert "state.db.backup" not in boot_hardening
    assert "Scheduled sdp-cli pipeline start" not in boot_hardening
    assert "ionice -c3 nice -n19" not in boot_hardening
    assert "cypherclaw-bootstrap.service" in boot_hardening
    assert "cypherclaw-sdp-runner.service" in boot_hardening
