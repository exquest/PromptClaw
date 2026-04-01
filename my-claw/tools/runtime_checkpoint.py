#!/usr/bin/env python3
"""Checkpoint exporter for the live CypherClaw runtime state."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RECOVERY_DIRNAME = ".sdp/recovery"
DEFAULT_STATE_DB = ".sdp/state.db"
DEFAULT_OBSERVATORY_DB = ".promptclaw/observatory.db"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _db_file_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "size_bytes": 0, "modified_at": None}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def _integrity_check(db_path: Path) -> str:
    if not db_path.exists():
        return "missing"
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return "invalid"
    if not row:
        return "unknown"
    return str(row[0])


def _batch_id_for(task_id: str) -> str:
    if "@" not in task_id:
        return task_id
    return task_id.split("@", 1)[1]


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _select_columns(available: set[str], requested: list[str]) -> str:
    parts = []
    for name in requested:
        if name in available:
            parts.append(name)
        else:
            parts.append(f"NULL AS {name}")
    return ", ".join(parts)


def collect_checkpoint(
    project_root: str | Path,
    *,
    batch_titles: dict[str, str] | None = None,
    recent_runs_limit: int = 10,
) -> dict[str, Any]:
    """Collect a JSON-serializable checkpoint snapshot."""
    root = Path(project_root).resolve()
    state_db = root / DEFAULT_STATE_DB
    observatory_db = root / DEFAULT_OBSERVATORY_DB

    checkpoint: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(root),
        "db_files": {
            "state_db": _db_file_metadata(state_db),
            "observatory_db": _db_file_metadata(observatory_db),
        },
        "integrity": {
            "state_db": _integrity_check(state_db),
            "observatory_db": _integrity_check(observatory_db),
        },
        "queue_counts": {},
        "batch_totals": [],
        "active_task": None,
        "recent_task_runs": [],
    }

    if not state_db.exists():
        return checkpoint

    conn = sqlite3.connect(str(state_db))
    conn.row_factory = sqlite3.Row
    try:
        task_columns = _table_columns(conn, "tasks")
        task_select = _select_columns(
            task_columns,
            ["task_id", "description", "status", "lead_agent", "verify_agent", "updated_at"],
        )
        task_order = "created_at" if "created_at" in task_columns else "task_id"
        task_rows = conn.execute(
            f"SELECT {task_select} FROM tasks ORDER BY {task_order}"
        ).fetchall()
        counts = Counter(str(row["status"]) for row in task_rows)
        checkpoint["queue_counts"] = dict(sorted(counts.items()))

        batch_totals: dict[str, dict[str, Any]] = {}
        for row in task_rows:
            batch_id = _batch_id_for(str(row["task_id"]))
            bucket = batch_totals.setdefault(
                batch_id,
                {
                    "batch_id": batch_id,
                    "title": (batch_titles or {}).get(batch_id, batch_id),
                    "counts": defaultdict(int),
                    "total": 0,
                },
            )
            bucket["counts"][str(row["status"])] += 1
            bucket["total"] += 1
        checkpoint["batch_totals"] = [
            {
                "batch_id": batch_id,
                "title": data["title"],
                "counts": dict(sorted(data["counts"].items())),
                "total": data["total"],
            }
            for batch_id, data in sorted(batch_totals.items())
        ]

        active = conn.execute(
            f"SELECT {task_select} FROM tasks WHERE status = 'running' "
            f"ORDER BY {'updated_at DESC' if 'updated_at' in task_columns else 'task_id DESC'} LIMIT 1"
        ).fetchone()
        if active is not None:
            checkpoint["active_task"] = dict(active)

        run_columns = _table_columns(conn, "task_runs")
        if run_columns:
            run_select = _select_columns(
                run_columns,
                [
                    "task_run_id",
                    "pipeline_run_id",
                    "task_id",
                    "lead_agent",
                    "verify_agent",
                    "verdict",
                    "gate_passed",
                    "duration_seconds",
                    "started_at",
                    "completed_at",
                ],
            )
            run_order = "started_at DESC" if "started_at" in run_columns else "task_run_id DESC"
            recent_runs = conn.execute(
                f"SELECT {run_select} FROM task_runs ORDER BY {run_order} LIMIT ?",
                (recent_runs_limit,),
            ).fetchall()
            checkpoint["recent_task_runs"] = [dict(row) for row in recent_runs]
    finally:
        conn.close()

    return checkpoint


def write_checkpoint(
    project_root: str | Path,
    *,
    output_dir: str | Path | None = None,
    timestamp: str | None = None,
    batch_titles: dict[str, str] | None = None,
) -> Path:
    """Write a checkpoint manifest and return its path."""
    root = Path(project_root).resolve()
    recovery_dir = Path(output_dir) if output_dir else root / DEFAULT_RECOVERY_DIRNAME
    recovery_dir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or _utc_timestamp()
    payload = collect_checkpoint(root, batch_titles=batch_titles)
    checkpoint_path = recovery_dir / f"checkpoint-{stamp}.json"
    checkpoint_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return checkpoint_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a CypherClaw runtime checkpoint manifest.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    args = parser.parse_args(argv)
    checkpoint_path = write_checkpoint(
        args.project_root,
        output_dir=args.output_dir,
        timestamp=args.timestamp,
    )
    print(checkpoint_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
