"""Tests for the PromptClaw workspace snapshot integration."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(".promptclaw/scripts/workspace_snapshot.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("promptclaw_workspace_snapshot", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load workspace_snapshot module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snapshot = _load_module()


class AliasIndexTests(unittest.TestCase):
    def test_build_alias_index_includes_ids_display_names_and_aliases(self) -> None:
        registry = {
            "projects": [
                {
                    "id": "lgpromptlab",
                    "display_name": "LGPromptLab",
                    "aliases": ["Promptlab", "Prompt Lab"],
                    "path": "~/Documents/programming/LGPromptLab",
                }
            ]
        }

        alias_index = snapshot.build_alias_index(registry)

        self.assertEqual(alias_index["lgpromptlab"], "lgpromptlab")
        self.assertEqual(alias_index["promptlab"], "lgpromptlab")
        self.assertEqual(alias_index["prompt lab"], "lgpromptlab")


class ProgressParsingTests(unittest.TestCase):
    def test_parse_progress_summary_handles_generated_sdp_progress(self) -> None:
        text = """
# Progress

Generated from SQLite state (`tasks`, `task_runs`, `escalations`). Do not edit manually.

Progress: [████░░░░] 74%  207 / 280 tasks complete
  completed: 207, in-progress: 0, pending: 0, failed: 72, skipped: 1

- **T-054**: complete — Completed with verdict PASS.
"""

        parsed = snapshot.parse_progress_summary(text)

        self.assertEqual(parsed["progress_percent"], 74)
        self.assertEqual(parsed["completed"], 207)
        self.assertEqual(parsed["total"], 280)
        self.assertEqual(parsed["counts"]["failed"], 72)
        self.assertEqual(parsed["headline"], "74% 207/280 complete")
        self.assertEqual(parsed["first_task"]["task_id"], "T-054")

    def test_parse_progress_summary_handles_hand_written_progress(self) -> None:
        text = """
# Progress

## Current Task: Consolidate repo image assets for marketing use
## Classification: T2
## Phase: 0 — Explore (Completed)
"""

        parsed = snapshot.parse_progress_summary(text)

        self.assertEqual(parsed["current_task"], "Consolidate repo image assets for marketing use")
        self.assertEqual(parsed["classification"], "T2")
        self.assertEqual(parsed["phase"], "0 — Explore (Completed)")
        self.assertEqual(parsed["headline"], "Current task: Consolidate repo image assets for marketing use")


class WorkspaceSnapshotTests(unittest.TestCase):
    def test_build_workspace_snapshot_collects_status_and_latest_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_path = root / "LifeImprover"
            repo_path.mkdir()
            (repo_path / "progress.md").write_text(
                """
# Progress

Progress: [████░░░░] 74%  207 / 280 tasks complete
  completed: 207, in-progress: 0, pending: 0, failed: 72, skipped: 1
""",
                encoding="utf-8",
            )
            (repo_path / "SESSION_NOTES.md").write_text(
                """
# Session Notes

## 2026-03-11 — Chat widget integration tests
- Completed frontend contract coverage.
""",
                encoding="utf-8",
            )
            (repo_path / "PROJECT_PLAN.md").write_text("# Project Plan\n", encoding="utf-8")
            (repo_path / "sdp.toml").write_text("[project]\n", encoding="utf-8")

            registry_path = root / "workspace_registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "projects": [
                            {
                                "id": "lifeimprover",
                                "display_name": "LifeImprover",
                                "aliases": ["Life Improver"],
                                "path": str(repo_path),
                                "priority": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            payload = snapshot.build_workspace_snapshot(
                registry_path,
                branch_resolver=lambda _: "main",
                checked_at="2026-03-13T05:00:00Z",
            )

            self.assertEqual(payload["checked_at"], "2026-03-13T05:00:00Z")
            self.assertEqual(payload["projects"][0]["git_branch"], "main")
            self.assertTrue(payload["projects"][0]["files"]["progress"])
            self.assertTrue(payload["projects"][0]["files"]["session_notes"])
            self.assertEqual(payload["projects"][0]["status_source"], "sdp")
            self.assertEqual(payload["projects"][0]["progress"]["progress_percent"], 74)
            self.assertEqual(
                payload["projects"][0]["session_notes"]["latest_heading"],
                "2026-03-11 — Chat widget integration tests",
            )


if __name__ == "__main__":
    unittest.main()
