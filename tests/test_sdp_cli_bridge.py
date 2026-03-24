"""Tests for the PromptClaw sdp-cli bridge."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(".promptclaw/scripts/sdp_cli_bridge.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("promptclaw_sdp_cli_bridge", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load sdp_cli_bridge module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bridge = _load_module()


class ResolveRepoPathTests(unittest.TestCase):
    def test_resolve_repo_path_prefers_state_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "sdp-cli"
            repo_path.mkdir()
            state_path = Path(tmpdir) / "STATE.json"
            state_path.write_text(
                json.dumps(
                    {
                        "integrations": {
                            "sdp_cli": {
                                "enabled": True,
                                "repo_path": str(repo_path),
                                "command": "auto",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            resolved = bridge.resolve_repo_path(None, state_path)
            self.assertEqual(resolved, repo_path.resolve())


class BuildBridgePayloadTests(unittest.TestCase):
    def test_build_bridge_payload_aggregates_counts_and_alerts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            command = ["sdp-cli"]

            responses = {
                ("tasks", "snapshot", "--json"): (
                    True,
                    {
                        "status_counts": {
                            "pending": 4,
                            "running": 1,
                            "blocked": 2,
                            "needs_review": 3,
                        },
                        "frozen_task_count": 1,
                    },
                    None,
                ),
                ("tasks", "approvals", "--json"): (
                    True,
                    [{"task_id": "T-1"}, {"task_id": "T-2"}],
                    None,
                ),
                ("tasks", "escalations", "--json"): (
                    True,
                    [{"task_id": "E-1"}],
                    None,
                ),
                ("agents", "usage", "--json"): (
                    True,
                    [
                        {
                            "provider": "openai",
                            "window_name": "hour",
                            "used_pct": 84.2,
                            "confidence": "authoritative",
                            "reset_at": "2026-03-13T01:00:00Z",
                        },
                        {
                            "provider": "anthropic",
                            "window_name": "day",
                            "used_pct": 12.5,
                            "confidence": "estimated",
                            "reset_at": "2026-03-14T00:00:00Z",
                        },
                    ],
                    None,
                ),
            }

            def fake_invoker(args):
                return responses[tuple(args)]

            payload = bridge.build_bridge_payload(repo_path, command, invoker=fake_invoker)

            self.assertTrue(payload["available"])
            self.assertEqual(payload["tasks"]["status_counts"]["pending"], 4)
            self.assertEqual(payload["tasks"]["frozen_task_count"], 1)
            self.assertEqual(payload["tasks"]["approvals_count"], 2)
            self.assertEqual(payload["tasks"]["escalations_count"], 1)
            self.assertEqual(len(payload["usage"]["alerts"]), 1)
            self.assertEqual(payload["usage"]["alerts"][0]["provider"], "openai")
            self.assertEqual(payload["usage"]["alerts"][0]["severity"], "high")

    def test_build_bridge_payload_falls_back_to_sqlite_for_task_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            sdp_dir = repo_path / ".sdp"
            sdp_dir.mkdir()
            db_path = sdp_dir / "state.db"

            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "CREATE TABLE tasks ("
                    " task_id TEXT PRIMARY KEY,"
                    " description TEXT NOT NULL,"
                    " tier TEXT NOT NULL,"
                    " status TEXT NOT NULL,"
                    " status_reason TEXT NOT NULL DEFAULT '',"
                    " frozen INTEGER NOT NULL DEFAULT 0,"
                    " created_at TEXT NOT NULL"
                    ")"
                )
                conn.execute(
                    "CREATE TABLE escalations ("
                    " escalation_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    " task_id TEXT NOT NULL,"
                    " reason TEXT NOT NULL,"
                    " details_path TEXT NOT NULL,"
                    " status TEXT NOT NULL,"
                    " created_at TEXT NOT NULL"
                    ")"
                )
                conn.execute(
                    "INSERT INTO tasks (task_id, description, tier, status, status_reason, frozen, created_at)"
                    " VALUES ('T-1', 'Needs review task', 'T2', 'needs_review', 'Protected file changed', 0, '2026-03-12T20:00:00Z')"
                )
                conn.execute(
                    "INSERT INTO tasks (task_id, description, tier, status, status_reason, frozen, created_at)"
                    " VALUES ('T-2', 'Blocked task', 'T1', 'blocked', '', 1, '2026-03-12T20:01:00Z')"
                )
                conn.execute(
                    "INSERT INTO escalations (task_id, reason, details_path, status, created_at)"
                    " VALUES ('T-2', 'Agent timeout', 'report.md', 'open', '2026-03-12T20:02:00Z')"
                )
                conn.commit()
            finally:
                conn.close()

            command = ["sdp-cli"]

            responses = {
                ("tasks", "snapshot", "--json"): (False, None, "readonly"),
                ("tasks", "approvals", "--json"): (False, None, "readonly"),
                ("tasks", "escalations", "--json"): (False, None, "readonly"),
                ("agents", "usage", "--json"): (True, [], None),
            }

            def fake_invoker(args):
                return responses[tuple(args)]

            payload = bridge.build_bridge_payload(repo_path, command, invoker=fake_invoker)

            self.assertEqual(payload["tasks"]["status_counts"]["needs_review"], 1)
            self.assertEqual(payload["tasks"]["frozen_task_count"], 1)
            self.assertEqual(payload["tasks"]["approvals_count"], 1)
            self.assertEqual(payload["tasks"]["escalations_count"], 1)
            self.assertEqual(payload["approvals"][0]["task_id"], "T-1")
            self.assertEqual(payload["escalations"][0]["task_id"], "T-2")
            self.assertEqual(payload["errors"], [])


if __name__ == "__main__":
    unittest.main()
