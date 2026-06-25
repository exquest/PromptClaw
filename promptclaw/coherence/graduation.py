"""Self-graduating enforcement mode promotion for the Coherence Engine."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .models import CoherenceConfig, EnforcementMode


@dataclass
class GraduationStats:
    """Tracks observation statistics used to evaluate mode promotions."""

    total_observations: int = 0
    true_positives: int = 0  # violation detected AND confirmed (retry fixed it)
    false_positives: int = 0  # violation detected BUT was wrong (user overrode)
    runs_in_current_mode: int = 0

    @property
    def confidence(self) -> float:
        if self.total_observations == 0:
            return 0.0
        return self.true_positives / self.total_observations

    @property
    def false_positive_rate(self) -> float:
        if self.total_observations == 0:
            return 1.0  # Unknown = assume bad
        return self.false_positives / self.total_observations


class GraduationManager:
    """Evaluates whether the enforcement mode should be promoted."""

    MIN_OBSERVATIONS_FOR_SOFT = 20
    MIN_RUNS_FOR_FULL = 10

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS graduation_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        mode TEXT NOT NULL,
        total_observations INTEGER NOT NULL DEFAULT 0,
        true_positives INTEGER NOT NULL DEFAULT 0,
        false_positives INTEGER NOT NULL DEFAULT 0,
        runs_in_current_mode INTEGER NOT NULL DEFAULT 0
    );
    """

    def __init__(self, config: CoherenceConfig, db_path: Path | None = None) -> None:
        self.config = config
        self.current_mode: EnforcementMode = config.mode
        self.stats = GraduationStats()
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        if db_path is not None:
            self._migrate()
            self._load()

    # --- Optional SQLite persistence (in-memory when db_path is None) ---

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), timeout=30)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=30000")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _migrate(self) -> None:
        assert self._db_path is not None
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.executescript(self._SCHEMA)
        conn.commit()

    def _load(self) -> None:
        row = self._get_conn().execute(
            "SELECT * FROM graduation_state WHERE id = 1"
        ).fetchone()
        if row is None:
            return
        try:
            self.current_mode = EnforcementMode(row["mode"])
        except ValueError:
            pass
        self.stats = GraduationStats(
            total_observations=row["total_observations"],
            true_positives=row["true_positives"],
            false_positives=row["false_positives"],
            runs_in_current_mode=row["runs_in_current_mode"],
        )

    def _persist(self) -> None:
        if self._db_path is None:
            return
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO graduation_state "
            "(id, mode, total_observations, true_positives, false_positives, runs_in_current_mode) "
            "VALUES (1, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET mode=excluded.mode, "
            "total_observations=excluded.total_observations, true_positives=excluded.true_positives, "
            "false_positives=excluded.false_positives, runs_in_current_mode=excluded.runs_in_current_mode",
            (self.current_mode.value, self.stats.total_observations, self.stats.true_positives,
             self.stats.false_positives, self.stats.runs_in_current_mode),
        )
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def record_observation(self, was_true_positive: bool) -> None:
        """Record whether a detected violation was a true or false positive."""
        self.stats.total_observations += 1
        if was_true_positive:
            self.stats.true_positives += 1
        else:
            self.stats.false_positives += 1
        self._persist()

    def increment_run(self) -> None:
        """Increment the run counter for the current enforcement mode."""
        self.stats.runs_in_current_mode += 1
        self._persist()

    def evaluate_promotion(self) -> EnforcementMode:
        """Evaluate and possibly promote the current enforcement mode.

        Promotion rules:
        - MONITOR -> SOFT: confidence > threshold AND total_observations >= MIN_OBSERVATIONS_FOR_SOFT
        - SOFT -> FULL: false_positive_rate < threshold AND runs_in_current_mode >= MIN_RUNS_FOR_FULL
        - FULL -> FULL: no auto-promotion beyond full
        - auto_graduate=False prevents all promotions

        Never auto-demotes. Returns the (possibly updated) mode.
        """
        if not self.config.auto_graduate:
            return self.current_mode

        if self.current_mode == EnforcementMode.MONITOR:
            if (
                self.stats.total_observations >= self.MIN_OBSERVATIONS_FOR_SOFT
                and self.stats.confidence > self.config.graduation_confidence_threshold
            ):
                self.current_mode = EnforcementMode.SOFT
                self.stats.runs_in_current_mode = 0

        elif self.current_mode == EnforcementMode.SOFT:
            if (
                self.stats.runs_in_current_mode >= self.MIN_RUNS_FOR_FULL
                and self.stats.false_positive_rate < self.config.graduation_false_positive_threshold
            ):
                self.current_mode = EnforcementMode.FULL
                self.stats.runs_in_current_mode = 0

        # FULL: no further promotion possible

        self._persist()
        return self.current_mode
