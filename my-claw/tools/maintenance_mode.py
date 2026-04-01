#!/usr/bin/env python3
"""Maintenance mode flag management for CypherClaw."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAINTENANCE_STATE = ".sdp/maintenance-mode.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / MAINTENANCE_STATE


def read_maintenance_status(project_root: str | Path) -> dict[str, Any] | None:
    path = _state_path(project_root)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def enter_maintenance(project_root: str | Path, *, reason: str, actor: str) -> Path:
    path = _state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active": True,
        "reason": reason,
        "actor": actor,
        "entered_at": _now(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def exit_maintenance(project_root: str | Path, *, actor: str) -> dict[str, Any] | None:
    previous = read_maintenance_status(project_root)
    if previous is None:
        return None
    payload = dict(previous)
    payload["active"] = False
    payload["released_at"] = _now()
    payload["released_by"] = actor
    _state_path(project_root).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return previous


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage CypherClaw maintenance mode.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    enter_parser = subparsers.add_parser("enter")
    enter_parser.add_argument("--reason", required=True)
    enter_parser.add_argument("--actor", default="operator")

    exit_parser = subparsers.add_parser("exit")
    exit_parser.add_argument("--actor", default="operator")

    subparsers.add_parser("status")

    args = parser.parse_args(argv)

    if args.command == "enter":
        path = enter_maintenance(args.project_root, reason=args.reason, actor=args.actor)
        print(path)
        return 0
    if args.command == "exit":
        previous = exit_maintenance(args.project_root, actor=args.actor)
        print(json.dumps(previous or {}, indent=2, sort_keys=True))
        return 0

    print(json.dumps(read_maintenance_status(args.project_root) or {}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
