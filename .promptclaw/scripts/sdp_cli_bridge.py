#!/usr/bin/env python3
"""Bridge PromptClaw to machine-readable sdp-cli operator state."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence

DEFAULT_STATE_PATH = Path(".promptclaw/STATE.json")
DEFAULT_SDP_CLI_REPO = Path("~/sdp-cli").expanduser()

UsageWindow = dict[str, Any]
Invoker = Callable[[Sequence[str]], tuple[bool, Any, str | None]]


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def resolve_integration_config(state_path: Path) -> dict[str, Any]:
    state = _read_json_file(state_path)
    integrations = state.get("integrations")
    if not isinstance(integrations, dict):
        return {}
    sdp_cli = integrations.get("sdp_cli")
    return sdp_cli if isinstance(sdp_cli, dict) else {}


def resolve_repo_path(explicit_repo: str | None, state_path: Path) -> Path:
    if explicit_repo:
        return Path(explicit_repo).expanduser().resolve()

    config = resolve_integration_config(state_path)
    repo_path = config.get("repo_path")
    if isinstance(repo_path, str) and repo_path.strip():
        return Path(repo_path).expanduser().resolve()

    return DEFAULT_SDP_CLI_REPO.resolve()


def resolve_command(
    repo_path: Path,
    *,
    explicit_command: str | None = None,
    state_path: Path = DEFAULT_STATE_PATH,
) -> list[str]:
    if explicit_command:
        return shlex.split(explicit_command)

    config = resolve_integration_config(state_path)
    config_command = config.get("command")
    if isinstance(config_command, str) and config_command.strip() and config_command != "auto":
        return shlex.split(config_command)

    repo_local_cli = repo_path / ".venv" / "bin" / "sdp-cli"
    if repo_local_cli.is_file():
        return [str(repo_local_cli)]

    path_cli = shutil.which("sdp-cli")
    if path_cli:
        return [path_cli]

    repo_local_python = repo_path / ".venv" / "bin" / "python"
    if repo_local_python.is_file():
        return [str(repo_local_python), "-m", "sdp.cli"]

    return []


def resolve_state_db_path(repo_path: Path) -> Path:
    config_path = repo_path / "sdp.toml"
    if config_path.is_file():
        try:
            import tomllib

            with config_path.open("rb") as handle:
                config = tomllib.load(handle)
        except (OSError, ValueError, TypeError):
            config = {}
        state_db_path = config.get("state_db_path")
        if isinstance(state_db_path, str) and state_db_path.strip():
            candidate = Path(state_db_path).expanduser()
            if not candidate.is_absolute():
                candidate = repo_path / candidate
            return candidate

    return repo_path / ".sdp" / "state.db"


def _prepare_snapshot_env(
    repo_path: Path,
) -> tuple[tempfile.TemporaryDirectory[str] | None, dict[str, str], str, Path]:
    env = dict(os.environ)
    state_db_path = resolve_state_db_path(repo_path)
    if not state_db_path.exists():
        return None, env, "direct", state_db_path

    temp_dir = tempfile.TemporaryDirectory(prefix="promptclaw-sdp-bridge-")
    temp_db_path = Path(temp_dir.name) / state_db_path.name

    for source_path in (
        state_db_path,
        state_db_path.with_name(f"{state_db_path.name}-wal"),
        state_db_path.with_name(f"{state_db_path.name}-shm"),
    ):
        if source_path.exists():
            shutil.copy2(source_path, Path(temp_dir.name) / source_path.name)

    env["SDP_STATE_DB_PATH"] = str(temp_db_path)
    return temp_dir, env, "snapshot", temp_db_path


def _run_json_command(
    base_command: Sequence[str],
    repo_path: Path,
    extra_args: Sequence[str],
    *,
    env: dict[str, str] | None = None,
) -> tuple[bool, Any, str | None]:
    try:
        result = subprocess.run(  # noqa: S603
            [*base_command, *extra_args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except OSError as exc:
        return False, None, str(exc)

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode != 0:
        detail = stderr or stdout or f"command failed with exit code {result.returncode}"
        return False, None, detail

    if not stdout:
        return True, None, None

    try:
        return True, json.loads(stdout), None
    except json.JSONDecodeError as exc:
        return False, None, f"invalid JSON from {' '.join(extra_args)}: {exc}"


def _usage_alerts(rows: Sequence[UsageWindow]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for row in rows:
        used_pct = row.get("used_pct")
        confidence = str(row.get("confidence") or "").strip().lower()
        if not isinstance(used_pct, int | float) or confidence == "unknown":
            continue

        severity = ""
        if used_pct >= 80:
            severity = "high"
        elif used_pct >= 50:
            severity = "warning"

        if not severity:
            continue

        alerts.append(
            {
                "provider": str(row.get("provider") or ""),
                "window_name": str(row.get("window_name") or ""),
                "used_pct": round(float(used_pct), 1),
                "confidence": confidence or "unspecified",
                "severity": severity,
                "reset_at": row.get("reset_at"),
            }
        )

    alerts.sort(key=lambda item: (-float(item["used_pct"]), str(item["provider"]), str(item["window_name"])))
    return alerts


def _query_status_snapshot(db_path: Path) -> tuple[dict[str, int] | None, str | None]:
    if not db_path.exists():
        return {}, None

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        return None, str(exc)

    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM tasks GROUP BY status"
        ).fetchall()
        status_counts = {
            str(row["status"] or "").strip().lower(): int(row["count"] or 0)
            for row in rows
            if str(row["status"] or "").strip()
        }
        return status_counts, None
    except sqlite3.Error as exc:
        return None, str(exc)
    finally:
        conn.close()


def _query_frozen_count(db_path: Path) -> tuple[int | None, str | None]:
    if not db_path.exists():
        return 0, None

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        return None, str(exc)

    try:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM tasks WHERE COALESCE(frozen, 0) = 1"
        ).fetchone()
        return int(row["count"] or 0) if row is not None else 0, None
    except sqlite3.Error as exc:
        return None, str(exc)
    finally:
        conn.close()


def _query_approvals(db_path: Path) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not db_path.exists():
        return [], None

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        return None, str(exc)

    try:
        rows = conn.execute(
            "SELECT task_id, description, tier, status_reason"
            " FROM tasks"
            " WHERE status = 'needs_review'"
            " ORDER BY created_at ASC"
        ).fetchall()
        return [
            {
                "task_id": str(row["task_id"]),
                "description": str(row["description"] or ""),
                "tier": str(row["tier"] or ""),
                "reason": str(row["status_reason"] or ""),
            }
            for row in rows
        ], None
    except sqlite3.Error as exc:
        return None, str(exc)
    finally:
        conn.close()


def _query_escalations(db_path: Path) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not db_path.exists():
        return [], None

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        return None, str(exc)

    try:
        rows = conn.execute(
            "SELECT e.task_id, t.description, e.reason, e.details_path, e.created_at"
            " FROM escalations e"
            " LEFT JOIN tasks t ON t.task_id = e.task_id"
            " WHERE e.status = 'open'"
            "   AND e.escalation_id IN ("
            "     SELECT MAX(e2.escalation_id)"
            "     FROM escalations e2"
            "     WHERE e2.status = 'open'"
            "     GROUP BY e2.task_id"
            "   )"
            " ORDER BY e.created_at DESC, e.task_id ASC"
        ).fetchall()
        return [
            {
                "task_id": str(row["task_id"]),
                "description": str(row["description"] or ""),
                "reason": str(row["reason"] or ""),
                "details_path": str(row["details_path"] or ""),
                "created_at": str(row["created_at"] or ""),
            }
            for row in rows
        ], None
    except sqlite3.Error as exc:
        return None, str(exc)
    finally:
        conn.close()


def build_bridge_payload(
    repo_path: Path,
    base_command: Sequence[str],
    *,
    invoker: Invoker | None = None,
) -> dict[str, Any]:
    checked_at = datetime.now(tz=UTC).isoformat()
    payload: dict[str, Any] = {
        "checked_at": checked_at,
        "repo_path": str(repo_path),
        "command": list(base_command),
        "available": False,
        "state_db_mode": "direct",
        "errors": [],
        "tasks": {
            "status_counts": {},
            "frozen_task_count": 0,
            "approvals_count": 0,
            "escalations_count": 0,
        },
        "approvals": [],
        "escalations": [],
        "usage": {
            "windows": [],
            "alerts": [],
        },
    }

    if not repo_path.is_dir():
        payload["errors"].append(f"repo path does not exist: {repo_path}")
        return payload

    if not base_command:
        payload["errors"].append("unable to resolve sdp-cli command")
        return payload

    payload["available"] = True
    temp_dir, env, state_db_mode, query_db_path = _prepare_snapshot_env(repo_path)
    payload["state_db_mode"] = state_db_mode
    try:
        invoke = invoker or (lambda args: _run_json_command(base_command, repo_path, args, env=env))

        snapshot_ok, snapshot_data, snapshot_error = invoke(["tasks", "snapshot", "--json"])
        approvals_ok, approvals_data, approvals_error = invoke(["tasks", "approvals", "--json"])
        escalations_ok, escalations_data, escalations_error = invoke(["tasks", "escalations", "--json"])
        usage_ok, usage_data, usage_error = invoke(["agents", "usage", "--json"])

        if not snapshot_ok:
            status_counts, status_error = _query_status_snapshot(query_db_path)
            frozen_count, frozen_error = _query_frozen_count(query_db_path)
            if status_counts is not None and frozen_count is not None:
                snapshot_ok = True
                snapshot_data = {
                    "status_counts": status_counts,
                    "frozen_task_count": frozen_count,
                }
                snapshot_error = None
            else:
                snapshot_error = status_error or frozen_error or snapshot_error

        if not approvals_ok:
            approvals_fallback, approvals_fallback_error = _query_approvals(query_db_path)
            if approvals_fallback is not None:
                approvals_ok = True
                approvals_data = approvals_fallback
                approvals_error = None
            else:
                approvals_error = approvals_fallback_error or approvals_error

        if not escalations_ok:
            escalations_fallback, escalations_fallback_error = _query_escalations(query_db_path)
            if escalations_fallback is not None:
                escalations_ok = True
                escalations_data = escalations_fallback
                escalations_error = None
            else:
                escalations_error = escalations_fallback_error or escalations_error

        if not snapshot_ok and snapshot_error:
            payload["errors"].append(snapshot_error)
        if not approvals_ok and approvals_error:
            payload["errors"].append(approvals_error)
        if not escalations_ok and escalations_error:
            payload["errors"].append(escalations_error)
        if not usage_ok and usage_error:
            payload["errors"].append(usage_error)

        status_counts: dict[str, int] = {}
        if isinstance(snapshot_data, dict):
            raw_counts = snapshot_data.get("status_counts")
            if isinstance(raw_counts, dict):
                for key, value in raw_counts.items():
                    if isinstance(key, str) and isinstance(value, int):
                        status_counts[key] = value

            frozen_count = snapshot_data.get("frozen_task_count")
            if isinstance(frozen_count, int):
                payload["tasks"]["frozen_task_count"] = frozen_count

        approvals: list[dict[str, Any]] = approvals_data if isinstance(approvals_data, list) else []
        escalations: list[dict[str, Any]] = escalations_data if isinstance(escalations_data, list) else []
        usage_rows: list[UsageWindow] = usage_data if isinstance(usage_data, list) else []

        payload["tasks"]["status_counts"] = status_counts
        payload["tasks"]["approvals_count"] = len(approvals)
        payload["tasks"]["escalations_count"] = len(escalations)
        payload["approvals"] = approvals
        payload["escalations"] = escalations
        payload["usage"]["windows"] = usage_rows
        payload["usage"]["alerts"] = _usage_alerts(usage_rows)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()
    return payload


def render_text_summary(payload: dict[str, Any]) -> str:
    tasks = payload.get("tasks", {})
    status_counts = tasks.get("status_counts", {}) if isinstance(tasks, dict) else {}
    alerts = payload.get("usage", {}).get("alerts", []) if isinstance(payload.get("usage"), dict) else []

    queue_parts = [
        f"pending {status_counts.get('pending', 0)}",
        f"running {status_counts.get('running', 0)}",
        f"blocked {status_counts.get('blocked', 0)}",
        f"review {status_counts.get('needs_review', 0)}",
        f"frozen {tasks.get('frozen_task_count', 0)}",
    ]

    lines = [
        "sdp-cli integration summary",
        f"- repo: {payload.get('repo_path', 'unknown')}",
        f"- queue: {', '.join(queue_parts)}",
        f"- approvals: {tasks.get('approvals_count', 0)}",
        f"- escalations: {tasks.get('escalations_count', 0)}",
    ]

    if alerts:
        first_alert = alerts[0]
        lines.append(
            "- top quota alert: "
            f"{first_alert.get('provider', 'unknown')}/{first_alert.get('window_name', 'unknown')} "
            f"{first_alert.get('used_pct', '--')}% ({first_alert.get('severity', 'warning')})"
        )
    else:
        lines.append("- top quota alert: none")

    errors = payload.get("errors", [])
    if isinstance(errors, list) and errors:
        lines.append(f"- errors: {len(errors)}")

    return "\n".join(lines)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="Path to the local sdp-cli repository.")
    parser.add_argument(
        "--command",
        help="Explicit command used to invoke sdp-cli. Default: repo-local .venv, then PATH.",
    )
    parser.add_argument(
        "--state",
        default=str(DEFAULT_STATE_PATH),
        help="PromptClaw state file used for integration config. Default: .promptclaw/STATE.json",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    state_path = Path(args.state).expanduser()
    repo_path = resolve_repo_path(args.repo, state_path)
    base_command = resolve_command(repo_path, explicit_command=args.command, state_path=state_path)
    payload = build_bridge_payload(repo_path, base_command)

    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(render_text_summary(payload))

    return 0 if payload.get("available") else 1


if __name__ == "__main__":
    raise SystemExit(main())
