"""Tests for runtime checkpoint export."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import runtime_checkpoint


TASKS_SCHEMA = """
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    tier TEXT NOT NULL,
    status TEXT NOT NULL,
    lead_agent TEXT,
    verify_agent TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    complexity_score INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'manual',
    criteria TEXT NOT NULL DEFAULT '',
    rollback_count INTEGER NOT NULL DEFAULT 0,
    parent_task_id TEXT,
    status_reason TEXT NOT NULL DEFAULT '',
    status_changed_at TEXT NOT NULL DEFAULT '',
    status_changed_by TEXT NOT NULL DEFAULT '',
    frozen INTEGER NOT NULL DEFAULT 0,
    frozen_reason TEXT NOT NULL DEFAULT '',
    frozen_at TEXT NOT NULL DEFAULT '',
    frozen_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

TASK_RUNS_SCHEMA = """
CREATE TABLE task_runs (
    task_run_id TEXT PRIMARY KEY,
    pipeline_run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    lead_agent TEXT NOT NULL,
    verify_agent TEXT NOT NULL,
    work_result TEXT NOT NULL,
    verdict TEXT NOT NULL DEFAULT '',
    commit_count INTEGER NOT NULL DEFAULT 0,
    gate_passed INTEGER NOT NULL DEFAULT 0,
    timeout_retry_count INTEGER NOT NULL DEFAULT 0,
    redundancy_score REAL NOT NULL DEFAULT 0.0,
    retry_context TEXT NOT NULL DEFAULT '',
    lead_prompt_template_version TEXT NOT NULL DEFAULT '',
    lead_prompt_template_hash TEXT NOT NULL DEFAULT '',
    verify_prompt_template_version TEXT NOT NULL DEFAULT '',
    verify_prompt_template_hash TEXT NOT NULL DEFAULT '',
    lead_profile_id TEXT NOT NULL DEFAULT '',
    verify_profile_id TEXT NOT NULL DEFAULT '',
    lead_model_profile TEXT NOT NULL DEFAULT '{}',
    verify_model_profile TEXT NOT NULL DEFAULT '{}',
    core_modifying INTEGER NOT NULL DEFAULT 0,
    duration_seconds REAL NOT NULL DEFAULT 0.0,
    started_at TEXT NOT NULL,
    last_activity_at TEXT NOT NULL DEFAULT '',
    completed_at TEXT NOT NULL DEFAULT ''
);
"""


def _init_state_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(TASKS_SCHEMA)
    conn.executescript(TASK_RUNS_SCHEMA)
    conn.executemany(
        """
        INSERT INTO tasks (
            task_id, description, tier, status, lead_agent, verify_agent, priority,
            complexity_score, source, criteria, rollback_count, parent_task_id,
            status_reason, status_changed_at, status_changed_by, frozen,
            frozen_reason, frozen_at, frozen_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 0, 0, 'prd', '', 0, NULL, '', ?, 'test', 0, '', '', '', ?, ?)
        """,
        [
            (
                "T-001@20260401T000000Z",
                "First task",
                "T1",
                "complete",
                "codex",
                "gemini",
                "2026-04-01T00:00:00Z",
                "2026-04-01T00:00:00Z",
                "2026-04-01T00:00:00Z",
            ),
            (
                "T-002@20260401T000000Z",
                "Second task",
                "T1",
                "running",
                "codex",
                "gemini",
                "2026-04-01T00:05:00Z",
                "2026-04-01T00:05:00Z",
                "2026-04-01T00:05:00Z",
            ),
            (
                "T-001@20260401T010000Z",
                "Third task",
                "T2",
                "blocked",
                "claude",
                "codex",
                "2026-04-01T01:00:00Z",
                "2026-04-01T01:00:00Z",
                "2026-04-01T01:00:00Z",
            ),
        ],
    )
    conn.executemany(
        """
        INSERT INTO task_runs (
            task_run_id, pipeline_run_id, task_id, lead_agent, verify_agent, work_result,
            verdict, gate_passed, duration_seconds, started_at, completed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "run-1",
                "pipeline-1",
                "T-001@20260401T000000Z",
                "codex",
                "gemini",
                "success",
                "PASS",
                1,
                10.5,
                "2026-04-01T00:00:01Z",
                "2026-04-01T00:00:12Z",
            ),
            (
                "run-2",
                "pipeline-1",
                "T-002@20260401T000000Z",
                "codex",
                "gemini",
                "working",
                "",
                0,
                3.0,
                "2026-04-01T00:05:00Z",
                "",
            ),
        ],
    )
    conn.commit()
    conn.close()


def test_collect_checkpoint_summarizes_queue_and_batches(tmp_path: Path) -> None:
    project_root = tmp_path
    state_dir = project_root / ".sdp"
    state_dir.mkdir()
    promptclaw_dir = project_root / ".promptclaw"
    promptclaw_dir.mkdir()
    state_db = state_dir / "state.db"
    _init_state_db(state_db)
    (promptclaw_dir / "observatory.db").write_bytes(b"sqlite placeholder")

    checkpoint = runtime_checkpoint.collect_checkpoint(
        project_root,
        batch_titles={"20260401T000000Z": "Home Resilience"},
    )

    assert checkpoint["queue_counts"] == {"blocked": 1, "complete": 1, "running": 1}
    assert checkpoint["active_task"]["task_id"] == "T-002@20260401T000000Z"
    assert checkpoint["batch_totals"][0]["batch_id"] == "20260401T000000Z"
    assert checkpoint["batch_totals"][0]["title"] == "Home Resilience"
    assert checkpoint["batch_totals"][0]["counts"]["complete"] == 1
    assert checkpoint["batch_totals"][0]["counts"]["running"] == 1
    assert checkpoint["integrity"]["state_db"] == "ok"
    assert checkpoint["db_files"]["state_db"]["size_bytes"] > 0
    assert checkpoint["recent_task_runs"][0]["task_run_id"] == "run-2"


def test_write_checkpoint_persists_json_manifest(tmp_path: Path) -> None:
    project_root = tmp_path
    state_dir = project_root / ".sdp"
    state_dir.mkdir()
    (project_root / ".promptclaw").mkdir()
    _init_state_db(state_dir / "state.db")

    checkpoint_path = runtime_checkpoint.write_checkpoint(project_root, timestamp="20260401T120000Z")

    assert checkpoint_path.name == "checkpoint-20260401T120000Z.json"
    payload = json.loads(checkpoint_path.read_text())
    assert payload["project_root"] == str(project_root)
    assert payload["queue_counts"]["running"] == 1


def test_collect_checkpoint_tolerates_missing_optional_files(tmp_path: Path) -> None:
    project_root = tmp_path
    state_dir = project_root / ".sdp"
    state_dir.mkdir()
    _init_state_db(state_dir / "state.db")

    checkpoint = runtime_checkpoint.collect_checkpoint(project_root)

    assert checkpoint["db_files"]["observatory_db"]["exists"] is False
    assert checkpoint["active_task"]["task_id"] == "T-002@20260401T000000Z"
