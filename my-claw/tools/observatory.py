#!/usr/bin/env python3
"""Observatory — event store and query engine for PromptClaw introspection.

Records all PromptClaw events to a SQLite database and provides query/aggregation
interfaces for the Reviewer, Healer, and Skill Tracker modules.

Storage: append-only event log with rollup tables for daily/weekly aggregates.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


class Observatory:
    """Records and queries all PromptClaw events."""

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / ".promptclaw" / "observatory.db")
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self):
        c = self._conn
        c.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,
                timestamp   TEXT NOT NULL,
                data        TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(event_type, timestamp);

            CREATE TABLE IF NOT EXISTS task_results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent       TEXT NOT NULL,
                task_id     TEXT NOT NULL,
                success     INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                tokens      INTEGER NOT NULL,
                gate_pass   INTEGER NOT NULL,
                timestamp   TEXT NOT NULL,
                category    TEXT DEFAULT 'general'
            );
            CREATE INDEX IF NOT EXISTS idx_task_agent ON task_results(agent, timestamp);

            CREATE TABLE IF NOT EXISTS healing_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                failure_type    TEXT NOT NULL,
                severity        INTEGER NOT NULL,
                action_taken    TEXT NOT NULL,
                success         INTEGER NOT NULL,
                context         TEXT NOT NULL,
                timestamp       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_skills (
                agent       TEXT NOT NULL,
                category    TEXT NOT NULL,
                score       REAL NOT NULL DEFAULT 0.5,
                sample_count INTEGER NOT NULL DEFAULT 0,
                updated_at  TEXT NOT NULL,
                PRIMARY KEY (agent, category)
            );

            CREATE TABLE IF NOT EXISTS daily_rollups (
                date            TEXT NOT NULL,
                agent           TEXT NOT NULL,
                tasks_completed INTEGER DEFAULT 0,
                tasks_failed    INTEGER DEFAULT 0,
                total_tokens    INTEGER DEFAULT 0,
                total_duration_ms INTEGER DEFAULT 0,
                gate_passes     INTEGER DEFAULT 0,
                gate_total      INTEGER DEFAULT 0,
                PRIMARY KEY (date, agent)
            );
        """)
        c.commit()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, event_type: str, data: dict) -> None:
        """Record a generic event."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO events (event_type, timestamp, data) VALUES (?, ?, ?)",
            (event_type, now, json.dumps(data)),
        )
        self._conn.commit()

    def record_task_result(self, agent: str, task_id: str, success: bool,
                           duration_ms: int, tokens: int, gate_pass: bool,
                           category: str = "general") -> None:
        """Record a completed task result."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO task_results (agent, task_id, success, duration_ms, tokens, gate_pass, timestamp, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (agent, task_id, int(success), duration_ms, tokens, int(gate_pass), now, category),
        )
        self._conn.commit()
        self._update_skill(agent, category, success)

    def record_healing(self, failure_type: str, severity: int,
                       action_taken: str, success: bool, context: dict) -> None:
        """Record a healing event."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO healing_log (failure_type, severity, action_taken, success, context, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (failure_type, severity, action_taken, int(success), json.dumps(context), now),
        )
        self._conn.commit()

    def _update_skill(self, agent: str, category: str, success: bool):
        """Update rolling agent skill score (exponential moving average)."""
        now = datetime.now(timezone.utc).isoformat()
        row = self._conn.execute(
            "SELECT score, sample_count FROM agent_skills WHERE agent = ? AND category = ?",
            (agent, category),
        ).fetchone()
        if row is None:
            score = 1.0 if success else 0.0
            self._conn.execute(
                "INSERT INTO agent_skills (agent, category, score, sample_count, updated_at) "
                "VALUES (?, ?, ?, 1, ?)",
                (agent, category, score, now),
            )
        else:
            alpha = 0.3
            new_score = alpha * (1.0 if success else 0.0) + (1 - alpha) * row["score"]
            self._conn.execute(
                "UPDATE agent_skills SET score = ?, sample_count = sample_count + 1, updated_at = ? "
                "WHERE agent = ? AND category = ?",
                (new_score, now, agent, category),
            )
        self._conn.commit()

    def update_agent_skill(self, agent: str, category: str, success: bool) -> None:
        """Public compatibility wrapper for agent skill updates.

        AgentSelector and daemon code use this method directly; keep the public
        surface stable even though the EMA update is implemented internally.
        """
        self._update_skill(agent, category, success)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def query(self, event_type: str, since: datetime = None, limit: int = 100) -> list:
        """Query events by type."""
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=1)
        rows = self._conn.execute(
            "SELECT * FROM events WHERE event_type = ? AND timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
            (event_type, since.isoformat(), limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_task_results(self, since: datetime = None, agent: str = None) -> list:
        """Get task results, optionally filtered by agent and time."""
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=1)
        sql = "SELECT * FROM task_results WHERE timestamp >= ?"
        params = [since.isoformat()]
        if agent:
            sql += " AND agent = ?"
            params.append(agent)
        sql += " ORDER BY timestamp DESC"
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_agent_stats(self, agent: str = None, days: int = 1) -> dict:
        """Get aggregate stats for an agent (or all agents) over N days."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        if agent:
            rows = self._conn.execute(
                "SELECT agent, COUNT(*) as total, SUM(success) as successes, "
                "SUM(tokens) as total_tokens, AVG(duration_ms) as avg_duration, "
                "SUM(gate_pass) as gate_passes "
                "FROM task_results WHERE agent = ? AND timestamp >= ? GROUP BY agent",
                (agent, since),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT agent, COUNT(*) as total, SUM(success) as successes, "
                "SUM(tokens) as total_tokens, AVG(duration_ms) as avg_duration, "
                "SUM(gate_pass) as gate_passes "
                "FROM task_results WHERE timestamp >= ? GROUP BY agent",
                (since,),
            ).fetchall()
        return {r["agent"]: dict(r) for r in rows}

    def get_agent_skills(self, agent: str = None) -> list:
        """Get current skill scores for agent(s)."""
        if agent:
            rows = self._conn.execute(
                "SELECT * FROM agent_skills WHERE agent = ? ORDER BY score DESC",
                (agent,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM agent_skills ORDER BY agent, score DESC",
            ).fetchall()
        return [dict(r) for r in rows]

    def get_healing_log(self, days: int = 1) -> list:
        """Get healing events from the last N days."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self._conn.execute(
            "SELECT * FROM healing_log WHERE timestamp >= ? ORDER BY timestamp DESC",
            (since,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_routing_accuracy(self, days: int = 7) -> float:
        """Get the gate pass rate as a proxy for routing accuracy."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        row = self._conn.execute(
            "SELECT COUNT(*) as total, SUM(gate_pass) as passes "
            "FROM task_results WHERE timestamp >= ?",
            (since,),
        ).fetchone()
        if row and row["total"] > 0:
            return row["passes"] / row["total"]
        return 0.0

    def aggregate(self, metric: str = "tasks", period: str = "daily") -> dict:
        """Aggregate metrics over a period (daily, weekly, monthly)."""
        if period == "daily":
            days = 1
        elif period == "weekly":
            days = 7
        elif period == "monthly":
            days = 30
        else:
            days = 1
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        row = self._conn.execute(
            "SELECT COUNT(*) as total, SUM(success) as successes, "
            "SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures, "
            "SUM(tokens) as total_tokens, AVG(duration_ms) as avg_duration, "
            "SUM(gate_pass) as gate_passes "
            "FROM task_results WHERE timestamp >= ?",
            (since,),
        ).fetchone()
        return dict(row) if row else {}

    # ------------------------------------------------------------------
    # Rollups
    # ------------------------------------------------------------------

    def rollup_daily(self, date: str = None):
        """Compute daily rollup aggregates. date format: YYYY-MM-DD."""
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = self._conn.execute(
            "SELECT agent, COUNT(*) as total, SUM(success) as successes, "
            "SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures, "
            "SUM(tokens) as total_tokens, SUM(duration_ms) as total_duration, "
            "SUM(gate_pass) as gate_passes "
            "FROM task_results WHERE date(timestamp) = ? GROUP BY agent",
            (date,),
        ).fetchall()
        for r in rows:
            self._conn.execute(
                "INSERT OR REPLACE INTO daily_rollups "
                "(date, agent, tasks_completed, tasks_failed, total_tokens, total_duration_ms, gate_passes, gate_total) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (date, r["agent"], r["successes"], r["failures"],
                 r["total_tokens"], r["total_duration"],
                 r["gate_passes"], r["total"]),
            )
        self._conn.commit()

    def get_daily_rollup(self, date: str = None) -> list:
        """Get the daily rollup for a date."""
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = self._conn.execute(
            "SELECT * FROM daily_rollups WHERE date = ?", (date,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_weekly_rollups(self, weeks_back: int = 0) -> list:
        """Get daily rollups for a given week (0 = this week, 1 = last week)."""
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=today.weekday() + 7 * weeks_back)
        end = start + timedelta(days=7)
        rows = self._conn.execute(
            "SELECT * FROM daily_rollups WHERE date >= ? AND date < ? ORDER BY date, agent",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()
