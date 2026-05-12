#!/usr/bin/env python3
"""Maintenance mode flag management for CypherClaw."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from runtime_checkpoint import write_checkpoint

DEFAULT_STATE_DB = ".sdp/state.db"
MAINTENANCE_FLAG_NAME = "MAINTENANCE"
LEGACY_STATE_NAME = "maintenance-mode.json"
DEFAULT_DRAIN_TIMEOUT_SECONDS = 60
DEFAULT_KILL_GRACE_SECONDS = 15
DEFAULT_ACTOR = "operator"
RUNNER_PGREP_PATTERN = "sdp-cli run"


@dataclass(frozen=True)
class MaintenancePaths:
    """Filesystem locations used by maintenance mode."""

    project_root: Path
    state_db: Path
    sdp_cli: Path

    @classmethod
    def from_project_root(cls, project_root: str | Path) -> "MaintenancePaths":
        root = Path(project_root).resolve()
        return cls(
            project_root=root,
            state_db=root / DEFAULT_STATE_DB,
            sdp_cli=Path("/home/user/.local/bin/sdp-cli"),
        )

    @property
    def authority_sdp_dir(self) -> Path:
        resolved = self.state_db.resolve(strict=False)
        return resolved.parent if resolved.name else self.state_db.parent

    @property
    def recovery_dir(self) -> Path:
        return self.authority_sdp_dir / "recovery"

    @property
    def maintenance_flag(self) -> Path:
        return self.authority_sdp_dir / MAINTENANCE_FLAG_NAME

    @property
    def legacy_state(self) -> Path:
        return self.project_root / ".sdp" / LEGACY_STATE_NAME

    @property
    def circuit_file(self) -> Path:
        return self.authority_sdp_dir / "circuit_breaker.json"

    @property
    def run_lock(self) -> Path:
        return self.project_root / ".sdp" / "run.lock"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(now: datetime | None = None) -> str:
    current = now or _utcnow()
    return current.astimezone(timezone.utc).isoformat()


def _default_circuit_state() -> dict[str, Any]:
    return {
        "status": "closed",
        "consecutive_failures": 0,
        "last_outcomes": [],
        "opened_at": None,
        "last_updated": "",
        "suggested_actions": [],
    }


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(default))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(default))
    if not isinstance(data, dict):
        return json.loads(json.dumps(default))
    return data


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_circuit_state(paths: MaintenancePaths) -> dict[str, Any]:
    return _load_json(paths.circuit_file, _default_circuit_state())


def _open_circuit(paths: MaintenancePaths, *, now: datetime, reason: str) -> dict[str, Any]:
    state = _load_circuit_state(paths)
    state["status"] = "circuit_open"
    state["consecutive_failures"] = max(int(state.get("consecutive_failures", 0) or 0), 3)
    state["opened_at"] = state.get("opened_at") or _isoformat(now)
    state["last_updated"] = _isoformat(now)
    state["suggested_actions"] = [
        "Complete maintenance work before resuming the runner.",
        "Exit maintenance with: python3 my-claw/tools/maintenance_mode.py --project-root . exit",
        "Reset the circuit only after maintenance is complete.",
    ]
    state["maintenance_reason"] = reason
    _save_json(paths.circuit_file, state)
    return state


def _restore_circuit(paths: MaintenancePaths, previous_state: dict[str, Any], *, now: datetime) -> None:
    restored = json.loads(json.dumps(previous_state or _default_circuit_state()))
    restored["last_updated"] = _isoformat(now)
    restored.pop("maintenance_reason", None)
    _save_json(paths.circuit_file, restored)


def _runner_pids() -> list[int]:
    try:
        result = subprocess.run(
            ["pgrep", "-f", RUNNER_PGREP_PATTERN],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.isdigit():
            pids.append(int(stripped))
    return pids


def _project_runner_pids(paths: MaintenancePaths) -> list[int]:
    if not paths.run_lock.exists():
        return []

    try:
        lock_pid = int(paths.run_lock.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return []

    return [pid for pid in _runner_pids() if pid == lock_pid]


def _wait_for_runner_exit(paths: MaintenancePaths, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + max(timeout_seconds, 0)
    while time.monotonic() <= deadline:
        if not _project_runner_pids(paths):
            return True
        time.sleep(1)
    return not _project_runner_pids(paths)


def _signal_pids(pids: Sequence[int], sig: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            continue


def _terminate_runner(paths: MaintenancePaths, kill_grace_seconds: int) -> None:
    initial = _project_runner_pids(paths)
    if not initial:
        return
    _signal_pids(initial, signal.SIGTERM)
    deadline = time.monotonic() + max(kill_grace_seconds, 0)
    while time.monotonic() <= deadline:
        if not _project_runner_pids(paths):
            return
        time.sleep(1)
    _signal_pids(_project_runner_pids(paths), signal.SIGKILL)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _running_task_ids(state_db: Path) -> list[str]:
    if not state_db.exists():
        return []
    conn = sqlite3.connect(str(state_db))
    try:
        rows = conn.execute(
            "SELECT task_id FROM tasks WHERE status = 'running' ORDER BY task_id"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [str(row[0]) for row in rows]


def _reset_running_tasks_with_cli(
    paths: MaintenancePaths,
    *,
    reason: str,
    actor: str,
) -> bool:
    if not paths.sdp_cli.is_file():
        return False
    try:
        result = subprocess.run(
            [
                str(paths.sdp_cli),
                "tasks",
                "reset-running",
                "--to",
                "pending",
                "--reason",
                reason,
                "--actor",
                actor,
            ],
            cwd=str(paths.project_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except Exception:
        return False
    return result.returncode == 0


def _reset_running_tasks_in_sqlite(
    paths: MaintenancePaths,
    *,
    reason: str,
    actor: str,
    now: datetime,
) -> list[str]:
    conn = sqlite3.connect(str(paths.state_db))
    try:
        rows = conn.execute(
            "SELECT task_id FROM tasks WHERE status = 'running' ORDER BY task_id"
        ).fetchall()
        task_ids = [str(row[0]) for row in rows]
        if not task_ids:
            return []

        changed_at = _isoformat(now)
        conn.executemany(
            """
            UPDATE tasks
            SET status = 'pending',
                status_reason = ?,
                status_changed_at = ?,
                status_changed_by = ?,
                updated_at = ?
            WHERE task_id = ?
            """,
            [
                (reason, changed_at, actor, changed_at, task_id)
                for task_id in task_ids
            ],
        )

        if _table_exists(conn, "task_runs"):
            conn.executemany(
                """
                UPDATE task_runs
                SET completed_at = CASE
                    WHEN completed_at = '' THEN ?
                    ELSE completed_at
                END
                WHERE task_id = ? AND completed_at = ''
                """,
                [(changed_at, task_id) for task_id in task_ids],
            )

        if _table_exists(conn, "task_status_history"):
            conn.executemany(
                """
                INSERT INTO task_status_history (
                    task_id, old_status, new_status, reason, actor, mutation_source, changed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        task_id,
                        "running",
                        "pending",
                        reason,
                        actor,
                        "maintenance_mode",
                        changed_at,
                    )
                    for task_id in task_ids
                ],
            )

        if _table_exists(conn, "pipeline_runs"):
            conn.execute(
                """
                UPDATE pipeline_runs
                SET status = 'blocked',
                    completed_at = CASE
                        WHEN completed_at = '' THEN ?
                        ELSE completed_at
                    END
                WHERE status = 'running'
                """,
                (changed_at,),
            )

        conn.commit()
        return task_ids
    finally:
        conn.close()


def _requeue_running_tasks(
    paths: MaintenancePaths,
    *,
    reason: str,
    actor: str,
    now: datetime,
) -> list[str]:
    before = _running_task_ids(paths.state_db)
    if not before:
        return []
    _reset_running_tasks_with_cli(paths, reason=reason, actor=actor)
    after = _running_task_ids(paths.state_db)
    if not after:
        return before
    return _reset_running_tasks_in_sqlite(paths, reason=reason, actor=actor, now=now)


def _status_payload(paths: MaintenancePaths) -> dict[str, Any]:
    if paths.maintenance_flag.exists():
        payload = _load_json(paths.maintenance_flag, {})
        payload["active"] = True
        payload["path"] = str(paths.maintenance_flag)
        return payload
    if paths.legacy_state.exists():
        payload = _load_json(paths.legacy_state, {"active": False})
        payload["path"] = str(paths.legacy_state)
        return payload
    return {"active": False, "path": str(paths.maintenance_flag)}


def read_maintenance_status(project_root: str | Path) -> dict[str, Any] | None:
    payload = _status_payload(MaintenancePaths.from_project_root(project_root))
    return payload if payload.get("active") else None


def enter_maintenance(
    project_root: str | Path,
    *,
    reason: str,
    actor: str,
    drain_timeout_seconds: int = DEFAULT_DRAIN_TIMEOUT_SECONDS,
    kill_grace_seconds: int = DEFAULT_KILL_GRACE_SECONDS,
    allow_runner_stop: bool = False,
    now: datetime | None = None,
) -> Path:
    paths = MaintenancePaths.from_project_root(project_root)
    current_time = now or _utcnow()
    running_reason = "Maintenance mode forced runner pause; task returned to pending."
    active_runner = _project_runner_pids(paths)
    active_tasks = _running_task_ids(paths.state_db)

    if (active_runner or active_tasks) and not allow_runner_stop:
        msg = (
            "refusing to enter maintenance while the managed runner is active; "
            "re-run with --allow-runner-stop or use safe_reboot.sh prepare"
        )
        raise RuntimeError(msg)

    checkpoint_path = write_checkpoint(
        paths.project_root,
        output_dir=paths.recovery_dir,
    )
    previous_circuit_state = _load_circuit_state(paths)
    maintenance_record = {
        "active": True,
        "reason": reason,
        "actor": actor,
        "entered_at": _isoformat(current_time),
        "checkpoint_path": str(checkpoint_path),
        "previous_circuit_state": previous_circuit_state,
        "drain_timeout_seconds": drain_timeout_seconds,
        "kill_grace_seconds": kill_grace_seconds,
        "runner_action": "idle",
        "running_tasks_requeued": [],
    }

    _save_json(paths.maintenance_flag, maintenance_record)
    paths.legacy_state.unlink(missing_ok=True)
    _open_circuit(
        paths,
        now=current_time,
        reason="Maintenance mode active; new runner starts are blocked.",
    )

    runner_action = "idle"
    running_tasks_requeued: list[str] = []
    if allow_runner_stop:
        if active_runner:
            if _wait_for_runner_exit(paths, drain_timeout_seconds):
                runner_action = "drained"
                running_tasks_requeued = _requeue_running_tasks(
                    paths,
                    reason=running_reason,
                    actor=actor,
                    now=current_time,
                )
                if running_tasks_requeued:
                    runner_action = "requeued"
            else:
                _terminate_runner(paths, kill_grace_seconds)
                running_tasks_requeued = _requeue_running_tasks(
                    paths,
                    reason=running_reason,
                    actor=actor,
                    now=current_time,
                )
                runner_action = "requeued" if running_tasks_requeued else "paused"
        elif active_tasks:
            running_tasks_requeued = _requeue_running_tasks(
                paths,
                reason=running_reason,
                actor=actor,
                now=current_time,
            )
            if running_tasks_requeued:
                runner_action = "requeued"

    paths.run_lock.unlink(missing_ok=True)
    maintenance_record["runner_action"] = runner_action
    maintenance_record["running_tasks_requeued"] = running_tasks_requeued
    _save_json(paths.maintenance_flag, maintenance_record)
    return paths.maintenance_flag


def exit_maintenance(
    project_root: str | Path,
    *,
    actor: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    paths = MaintenancePaths.from_project_root(project_root)
    current_time = now or _utcnow()
    if not paths.maintenance_flag.exists() and not paths.legacy_state.exists():
        return None

    payload = _status_payload(paths)
    previous_state = payload.get("previous_circuit_state", _default_circuit_state())
    _restore_circuit(paths, previous_state, now=current_time)
    paths.maintenance_flag.unlink(missing_ok=True)
    paths.legacy_state.unlink(missing_ok=True)
    payload["active"] = False
    payload["released_at"] = _isoformat(current_time)
    payload["released_by"] = actor
    return payload


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage CypherClaw maintenance mode.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    enter_parser = subparsers.add_parser("enter")
    enter_parser.add_argument("--reason", required=True)
    enter_parser.add_argument("--actor", default=DEFAULT_ACTOR)
    enter_parser.add_argument(
        "--drain-timeout-seconds",
        type=int,
        default=DEFAULT_DRAIN_TIMEOUT_SECONDS,
    )
    enter_parser.add_argument(
        "--kill-grace-seconds",
        type=int,
        default=DEFAULT_KILL_GRACE_SECONDS,
    )
    enter_parser.add_argument(
        "--allow-runner-stop",
        action="store_true",
        help="Allow maintenance mode to pause/requeue active runner work.",
    )

    exit_parser = subparsers.add_parser("exit")
    exit_parser.add_argument("--actor", default=DEFAULT_ACTOR)

    subparsers.add_parser("status")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.command == "enter":
        try:
            path = enter_maintenance(
                args.project_root,
                reason=args.reason,
                actor=args.actor,
                drain_timeout_seconds=args.drain_timeout_seconds,
                kill_grace_seconds=args.kill_grace_seconds,
                allow_runner_stop=args.allow_runner_stop,
            )
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.command == "exit":
        previous = exit_maintenance(args.project_root, actor=args.actor)
        print(json.dumps(previous or {}, indent=2, sort_keys=True))
        return 0

    print(json.dumps(_status_payload(MaintenancePaths.from_project_root(args.project_root)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
