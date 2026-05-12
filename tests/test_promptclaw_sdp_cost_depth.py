"""Depth-2 tests for promptclaw.sdp_cost [frac-0042]."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from promptclaw import sdp_cost
from promptclaw.sdp_cost import (
    CostRunSummary,
    DailyCostRow,
    aggregate_rows,
    cost_by_model,
    summarize_cost_run,
    total_cost_usd,
)


SDP_COST_MODULE_PATH = Path("promptclaw/sdp_cost.py")


def _row(
    *,
    date: str,
    runs: int = 1,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    total_cost_usd: float = 0.0,
    models: list[str] | None = None,
) -> DailyCostRow:
    return DailyCostRow(
        date=date,
        runs=runs,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
        total_cost_usd=total_cost_usd,
        models=list(models or []),
    )


def _make_telemetry_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE telemetry (
                telemetry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                lead_profile_id TEXT NOT NULL DEFAULT '',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
                cache_read_tokens INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        rows = [
            ("T-A", "claude-opus-4-7-high", 10_000, 5_000, 0, 0, "2026-04-25T10:00:00+00:00"),
            ("T-B", "claude-sonnet-4-6-standard", 4_000, 2_000, 0, 0, "2026-04-25T11:00:00+00:00"),
            ("T-C", "claude-sonnet-4-6-standard", 2_000, 1_000, 0, 0, "2026-04-26T08:00:00+00:00"),
        ]
        conn.executemany(
            """
            INSERT INTO telemetry (
                task_id, lead_profile_id, input_tokens, output_tokens,
                cache_creation_tokens, cache_read_tokens, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def test_total_cost_usd_sums_rows() -> None:
    rows = [
        _row(date="2026-04-25", total_cost_usd=0.5670),
        _row(date="2026-04-26", total_cost_usd=0.0480),
        _row(date="2026-04-27", total_cost_usd=0.0210),
    ]

    assert total_cost_usd(rows) == pytest.approx(0.6360)
    assert total_cost_usd([]) == 0.0


def test_cost_by_model_partitions_rows_across_tiers() -> None:
    rows = [
        _row(
            date="2026-04-25",
            total_cost_usd=1.00,
            models=["claude-opus-4", "claude-sonnet-4"],
        ),
        _row(
            date="2026-04-26",
            total_cost_usd=0.40,
            models=["claude-sonnet-4"],
        ),
        _row(
            date="2026-04-27",
            total_cost_usd=0.20,
            models=[],
        ),
    ]

    breakdown = cost_by_model(rows)

    assert list(breakdown.keys()) == sorted(breakdown.keys())
    assert breakdown["claude-opus-4"] == pytest.approx(0.50)
    assert breakdown["claude-sonnet-4"] == pytest.approx(0.50 + 0.40)
    assert breakdown["fallback"] == pytest.approx(0.20)
    assert cost_by_model([]) == {}


def test_aggregate_rows_sums_runs_tokens_and_cost() -> None:
    rows = [
        _row(
            date="2026-04-26",
            runs=2,
            input_tokens=1_000,
            output_tokens=2_000,
            cache_creation_tokens=10,
            cache_read_tokens=20,
            total_cost_usd=0.10,
            models=["claude-sonnet-4"],
        ),
        _row(
            date="2026-04-25",
            runs=3,
            input_tokens=4_000,
            output_tokens=5_000,
            cache_creation_tokens=30,
            cache_read_tokens=40,
            total_cost_usd=0.50,
            models=["claude-opus-4", "claude-sonnet-4"],
        ),
    ]

    aggregate = aggregate_rows(rows)

    assert aggregate.date == "2026-04-25"
    assert aggregate.runs == 5
    assert aggregate.input_tokens == 5_000
    assert aggregate.output_tokens == 7_000
    assert aggregate.cache_creation_tokens == 40
    assert aggregate.cache_read_tokens == 60
    assert aggregate.total_cost_usd == pytest.approx(0.60)
    assert aggregate.models == ["claude-opus-4", "claude-sonnet-4"]

    empty = aggregate_rows([])
    assert empty.date == ""
    assert empty.runs == 0
    assert empty.input_tokens == 0
    assert empty.total_cost_usd == 0.0
    assert empty.models == []


def test_summarize_cost_run_writes_csv_and_cap(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    csv_path = tmp_path / "out" / "steady-state-cost.csv"
    summary_path = tmp_path / "out" / "steady-state-cap-summary.md"
    _make_telemetry_db(db_path)

    summary = summarize_cost_run(
        db_path=db_path,
        days=7,
        out_path=csv_path,
        summary_out=summary_path,
        daily_cap_usd=0.10,
        min_days=2,
    )

    assert isinstance(summary, CostRunSummary)
    assert summary.csv_path == csv_path
    assert csv_path.exists()
    assert summary_path.exists()

    assert [row.date for row in summary.rows] == ["2026-04-25", "2026-04-26"]
    assert summary.total_cost_usd == pytest.approx(sum(r.total_cost_usd for r in summary.rows))
    # Both opus and sonnet tiers are seen across the test telemetry.
    assert set(summary.cost_by_model.keys()) == {"claude-opus-4", "claude-sonnet-4"}

    cap = summary.cap
    assert cap is not None
    assert cap.cap_usd == pytest.approx(0.10)
    assert cap.days_checked == 2
    assert cap.result == "FAIL"  # apr 25 over $0.10 cap
    assert cap.breach_count >= 1
    text = summary_path.read_text(encoding="utf-8")
    assert "**Result:** FAIL" in text


def test_summarize_cost_run_without_cap_path(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    csv_path = tmp_path / "out.csv"
    _make_telemetry_db(db_path)

    summary = summarize_cost_run(
        db_path=db_path,
        days=7,
        out_path=csv_path,
        summary_out=None,
    )

    assert summary.cap is None
    assert csv_path.exists()
    assert summary.csv_path == csv_path
    assert len(summary.rows) == 2


def test_existing_public_surface_preserved() -> None:
    # Smoke: existing helpers still importable and unchanged in shape.
    assert callable(sdp_cost.match_pricing)
    assert callable(sdp_cost.call_cost_usd)
    assert callable(sdp_cost.extract_steady_state_cost)
    assert callable(sdp_cost.write_csv)
    assert callable(sdp_cost.read_csv)
    assert callable(sdp_cost.check_daily_caps)
    assert callable(sdp_cost.summarize_daily_cap)
    assert callable(sdp_cost.render_cap_summary)
    assert callable(sdp_cost.write_cap_summary)


def test_sdp_cost_module_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(SDP_COST_MODULE_PATH)

    assert result.depth >= 2, result.reason
