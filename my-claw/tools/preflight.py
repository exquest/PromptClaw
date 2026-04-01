#!/usr/bin/env python3
"""Preflight validation for CypherClaw runner startup."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import runtime_checkpoint


DEFAULT_WORKDIR = Path("/run/cypherclaw-tmp/workdir/cypherclaw-work")


@dataclass(slots=True)
class PreflightReport:
    ok: bool
    summary: str
    checks: dict[str, dict[str, Any]]

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "summary": self.summary,
                "checks": self.checks,
            },
            indent=2,
            sort_keys=True,
        )

    def to_text(self) -> str:
        lines = [self.summary]
        for name, check in self.checks.items():
            status = "OK" if check["ok"] else "FAIL"
            message = check.get("message", "")
            lines.append(f"- {name}: {status}{f' — {message}' if message else ''}")
        return "\n".join(lines)


def pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _check_exists(path: Path, *, label: str) -> dict[str, Any]:
    if path.exists():
        return {"ok": True, "message": f"{label} present"}
    return {"ok": False, "message": f"{label} missing at {path}"}


def _check_db_integrity(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"ok": False, "message": f"database missing at {db_path}"}
    result = runtime_checkpoint._integrity_check(db_path)  # deliberate shared implementation
    if result == "ok":
        return {"ok": True, "message": "SQLite quick_check passed"}
    return {"ok": False, "message": f"SQLite quick_check returned {result!r}"}


def _check_run_lock(lock_path: Path) -> dict[str, Any]:
    if not lock_path.exists():
        return {"ok": True, "message": "No run.lock present"}
    raw = lock_path.read_text().strip()
    try:
        payload = json.loads(raw)
        pid = int(payload["pid"])
    except Exception:
        try:
            pid = int(raw.splitlines()[0].strip())
        except Exception:
            return {"ok": False, "message": f"Unreadable run.lock contents at {lock_path}"}
    if pid_exists(pid):
        return {"ok": True, "message": f"run.lock owned by live PID {pid}"}
    return {"ok": False, "message": f"Stale run.lock references dead PID {pid}"}


def _check_workdir_layout(workdir: Path) -> dict[str, Any]:
    required = [".git", "AGENTS.md", "pyproject.toml", "sdp.toml"]
    missing = [name for name in required if not (workdir / name).exists()]
    if not workdir.exists():
        return {"ok": False, "message": f"Workdir missing at {workdir}"}
    if missing:
        return {"ok": False, "message": f"Workdir missing {', '.join(missing)}"}
    return {"ok": True, "message": "Workdir layout looks valid"}


def _queue_counts(state_db: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(state_db))
    try:
        rows = conn.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall()
    finally:
        conn.close()
    return {str(status): int(count) for status, count in rows}


def _check_checkpoint_reconciliation(state_db: Path, checkpoint_path: Path | None) -> dict[str, Any]:
    if checkpoint_path is None:
        return {"ok": True, "message": "No checkpoint supplied"}
    payload = json.loads(checkpoint_path.read_text())
    expected = {str(key): int(value) for key, value in payload.get("queue_counts", {}).items()}
    actual = _queue_counts(state_db)
    normalized_statuses = set(expected) | set(actual)
    expected_full = {status: expected.get(status, 0) for status in sorted(normalized_statuses)}
    actual_full = {status: actual.get(status, 0) for status in sorted(normalized_statuses)}
    if expected_full == actual_full:
        return {"ok": True, "message": "Queue counts match checkpoint"}
    return {
        "ok": False,
        "message": f"Queue counts differ: expected {expected_full}, got {actual_full}",
        "expected": expected_full,
        "actual": actual_full,
    }


def run_preflight(
    project_root: str | Path,
    *,
    workdir: str | Path | None = None,
    checkpoint_path: str | Path | None = None,
) -> PreflightReport:
    root = Path(project_root).resolve()
    resolved_workdir = Path(workdir) if workdir is not None else DEFAULT_WORKDIR
    state_db = root / ".sdp" / "state.db"
    observatory_db = root / ".promptclaw" / "observatory.db"
    run_lock = root / ".sdp" / "run.lock"

    checks = {
        "state_db_exists": _check_exists(state_db, label="state.db"),
        "state_db_integrity": _check_db_integrity(state_db),
        "observatory_db_exists": _check_exists(observatory_db, label="observatory.db"),
        "run_lock": _check_run_lock(run_lock),
        "workdir_layout": _check_workdir_layout(resolved_workdir),
        "checkpoint_reconciliation": _check_checkpoint_reconciliation(
            state_db,
            Path(checkpoint_path) if checkpoint_path is not None else None,
        ),
    }
    ok = all(check["ok"] for check in checks.values())
    summary = "Preflight OK" if ok else "Preflight FAILED"
    return PreflightReport(ok=ok, summary=summary, checks=checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run CypherClaw startup preflight checks.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args(argv)
    report = run_preflight(
        args.project_root,
        workdir=args.workdir,
        checkpoint_path=args.checkpoint,
    )
    print(report.to_json() if args.json else report.to_text())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
