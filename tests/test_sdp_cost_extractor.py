"""Tests for the SDP steady-state cost extractor (T-032@b)."""

from __future__ import annotations

import csv
import io
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from promptclaw import sdp_cost


def _make_telemetry_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE telemetry (
                telemetry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'T1',
                complexity_score INTEGER NOT NULL DEFAULT 0,
                lead_agent TEXT NOT NULL DEFAULT '',
                verify_agent TEXT NOT NULL DEFAULT '',
                lead_prompt_template_version TEXT NOT NULL DEFAULT '',
                verify_prompt_template_version TEXT NOT NULL DEFAULT '',
                lead_profile_id TEXT NOT NULL DEFAULT '',
                verify_profile_id TEXT NOT NULL DEFAULT '',
                lead_model_profile TEXT NOT NULL DEFAULT '{}',
                verify_model_profile TEXT NOT NULL DEFAULT '{}',
                duration_seconds REAL NOT NULL DEFAULT 0.0,
                outcome TEXT NOT NULL DEFAULT 'pass',
                retry_count INTEGER NOT NULL DEFAULT 0,
                gate_results TEXT NOT NULL DEFAULT '[]',
                prompt_length_bytes INTEGER NOT NULL DEFAULT 0,
                log_size_bytes INTEGER NOT NULL DEFAULT 0,
                task_category TEXT NOT NULL DEFAULT '',
                verification_outcome TEXT NOT NULL DEFAULT 'skip',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                thinking_tokens INTEGER NOT NULL DEFAULT 0,
                lint_pass INTEGER NOT NULL DEFAULT 0,
                test_pass INTEGER NOT NULL DEFAULT 0,
                regression_detected INTEGER NOT NULL DEFAULT 0,
                agent TEXT NOT NULL DEFAULT 'claude',
                created_at TEXT NOT NULL,
                cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
                cache_read_tokens INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        rows = [
            # Two days at the start that should be excluded by days=3 cutoff.
            ("T-A", "claude-opus-4-7-high", 1000, 2000, 0, 0, "2026-04-01T10:00:00+00:00"),
            ("T-B", "gpt-5.4-xhigh", 500, 1500, 0, 0, "2026-04-02T10:00:00+00:00"),
            # Three most-recent active days (selected by days=3).
            ("T-C", "claude-opus-4-7-high", 10_000, 5_000, 100, 200, "2026-04-25T10:00:00+00:00"),
            ("T-D", "claude-sonnet-4-6-standard", 4_000, 2_000, 0, 0, "2026-04-25T11:30:00+00:00"),
            ("T-E", "gpt-5.4-xhigh", 1_000, 3_000, 0, 0, "2026-04-26T09:00:00+00:00"),
            ("T-F", "claude-opus-4-7-high", 0, 0, 0, 0, "2026-04-26T10:00:00+00:00"),
            ("T-G", "claude-sonnet-4-6-standard", 2_000, 1_000, 50, 50, "2026-04-27T08:00:00+00:00"),
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


def test_token_pricing_table_matches_cost_model_doc() -> None:
    by_pattern = {pattern: (in_p, out_p) for pattern, in_p, out_p in sdp_cost.TOKEN_PRICING}
    assert by_pattern["claude-opus-4"] == (15.00, 75.00)
    assert by_pattern["claude-sonnet-4"] == (3.00, 15.00)
    assert by_pattern["claude-haiku"] == (0.80, 4.00)
    assert by_pattern["gpt-4o"] == (2.50, 10.00)
    assert by_pattern["o3"] == (10.00, 40.00)
    assert by_pattern["codex-mini"] == (1.50, 6.00)
    assert by_pattern["fallback"] == (3.00, 15.00)


def test_match_pricing_substring_and_fallback() -> None:
    assert sdp_cost.match_pricing("claude-opus-4-7-high")[0] == "claude-opus-4"
    assert sdp_cost.match_pricing("CLAUDE-OPUS-4-6-extended")[0] == "claude-opus-4"
    assert sdp_cost.match_pricing("claude-sonnet-4-6-standard")[0] == "claude-sonnet-4"
    assert sdp_cost.match_pricing("claude-haiku-4-5")[0] == "claude-haiku"
    assert sdp_cost.match_pricing("gpt-4o-mini")[0] == "gpt-4o"
    assert sdp_cost.match_pricing("o3-pro")[0] == "o3"
    assert sdp_cost.match_pricing("codex-mini-latest")[0] == "codex-mini"
    # Unknown profiles fall through to fallback.
    assert sdp_cost.match_pricing("gpt-5.4-xhigh")[0] == "fallback"
    assert sdp_cost.match_pricing("gemini-3.1-pro-preview-high")[0] == "fallback"
    assert sdp_cost.match_pricing("")[0] == "fallback"
    # Pricing values returned alongside tier name.
    tier, in_p, out_p = sdp_cost.match_pricing("claude-opus-4-7-high")
    assert (in_p, out_p) == (15.00, 75.00)


def test_call_cost_usd_matches_cost_model_formula() -> None:
    # Cost-model.md worked example: 10k input + 5k output on claude-sonnet-4 = $0.105.
    cost = sdp_cost.call_cost_usd(10_000, 5_000, "claude-sonnet-4-6-standard")
    assert cost == pytest.approx(0.105)
    # claude-opus-4: (10_000/1e6 * 15) + (5_000/1e6 * 75) = 0.15 + 0.375 = 0.525
    assert sdp_cost.call_cost_usd(10_000, 5_000, "claude-opus-4-7-high") == pytest.approx(0.525)
    # Fallback ($3/$15) for unknown profile.
    assert sdp_cost.call_cost_usd(10_000, 5_000, "gpt-5.4-xhigh") == pytest.approx(0.105)
    # Zero tokens => zero cost.
    assert sdp_cost.call_cost_usd(0, 0, "claude-opus-4-7-high") == 0.0


def test_extract_steady_state_cost_groups_and_prices_by_day(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    _make_telemetry_db(db_path)

    rows = sdp_cost.extract_steady_state_cost(db_path, days=3)

    assert [r.date for r in rows] == ["2026-04-25", "2026-04-26", "2026-04-27"]

    by_date = {r.date: r for r in rows}

    apr25 = by_date["2026-04-25"]
    assert apr25.runs == 2
    assert apr25.input_tokens == 14_000
    assert apr25.output_tokens == 7_000
    assert apr25.cache_creation_tokens == 100
    assert apr25.cache_read_tokens == 200
    # T-C: opus-4 10k/5k -> 0.525; T-D: sonnet-4 4k/2k -> 0.042.
    assert apr25.total_cost_usd == pytest.approx(0.525 + 0.042)
    assert apr25.models == ["claude-opus-4", "claude-sonnet-4"]

    apr26 = by_date["2026-04-26"]
    assert apr26.runs == 2
    # T-E fallback 1k/3k -> 0.048; T-F opus-4 0/0 -> 0.0.
    assert apr26.total_cost_usd == pytest.approx(0.048)
    assert apr26.models == ["claude-opus-4", "fallback"]

    apr27 = by_date["2026-04-27"]
    assert apr27.runs == 1
    # T-G sonnet-4 2k/1k -> 0.006 + 0.015 = 0.021.
    assert apr27.total_cost_usd == pytest.approx(0.021)
    assert apr27.models == ["claude-sonnet-4"]


def test_extract_steady_state_cost_returns_active_days_only(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    _make_telemetry_db(db_path)

    # Asking for more days than exist returns all distinct active days.
    rows = sdp_cost.extract_steady_state_cost(db_path, days=99)
    assert [r.date for r in rows] == [
        "2026-04-01",
        "2026-04-02",
        "2026-04-25",
        "2026-04-26",
        "2026-04-27",
    ]


def test_write_csv_emits_stable_schema(tmp_path: Path) -> None:
    rows = [
        sdp_cost.DailyCostRow(
            date="2026-04-25",
            runs=2,
            input_tokens=14_000,
            output_tokens=7_000,
            cache_creation_tokens=100,
            cache_read_tokens=200,
            total_cost_usd=0.567,
            models=["claude-opus-4", "claude-sonnet-4"],
        ),
        sdp_cost.DailyCostRow(
            date="2026-04-26",
            runs=1,
            input_tokens=1_000,
            output_tokens=3_000,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_cost_usd=0.048,
            models=["fallback"],
        ),
    ]
    out = tmp_path / "out.csv"
    sdp_cost.write_csv(rows, out)

    text = out.read_text(encoding="utf-8")
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == [
        "date",
        "runs",
        "input_tokens",
        "output_tokens",
        "cache_creation_tokens",
        "cache_read_tokens",
        "total_cost_usd",
        "models",
    ]
    assert parsed[1] == [
        "2026-04-25",
        "2",
        "14000",
        "7000",
        "100",
        "200",
        "0.5670",
        "claude-opus-4|claude-sonnet-4",
    ]
    assert parsed[2] == [
        "2026-04-26",
        "1",
        "1000",
        "3000",
        "0",
        "0",
        "0.0480",
        "fallback",
    ]


def test_cli_writes_csv_and_prints_path(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    _make_telemetry_db(db_path)
    out = tmp_path / "steady-state-cost.csv"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "promptclaw.sdp_cost",
            "--db",
            str(db_path),
            "--days",
            "3",
            "--out",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert str(out) in result.stdout
    assert out.exists()
    parsed = list(csv.reader(out.open(encoding="utf-8")))
    assert parsed[0][0] == "date"
    assert len(parsed) == 4  # header + 3 days


def test_check_daily_caps_flags_breaches_and_exact_cap_passes() -> None:
    rows = [
        sdp_cost.DailyCostRow(
            date="2026-04-25",
            runs=1,
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_cost_usd=4.9999,
            models=["fallback"],
        ),
        sdp_cost.DailyCostRow(
            date="2026-04-26",
            runs=1,
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_cost_usd=5.0,
            models=["fallback"],
        ),
        sdp_cost.DailyCostRow(
            date="2026-04-27",
            runs=1,
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_cost_usd=5.5,
            models=["fallback"],
        ),
    ]

    checks = sdp_cost.check_daily_caps(rows, daily_cap_usd=5.0)

    assert [(c.date, c.status, c.over_by_usd) for c in checks] == [
        ("2026-04-25", "OK", 0.0),
        ("2026-04-26", "OK", 0.0),
        ("2026-04-27", "BREACH", pytest.approx(0.5)),
    ]
    assert checks[0].breached is False
    assert checks[1].breached is False
    assert checks[2].breached is True


def test_render_cap_summary_links_cost_model_and_lists_breaches() -> None:
    rows = [
        sdp_cost.DailyCostRow(
            date="2026-04-26",
            runs=1,
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_cost_usd=4.0,
            models=["fallback"],
        ),
        sdp_cost.DailyCostRow(
            date="2026-04-27",
            runs=1,
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_cost_usd=5.5,
            models=["fallback"],
        ),
    ]

    summary = sdp_cost.summarize_daily_cap(rows, daily_cap_usd=5.0, min_days=2)
    text = sdp_cost.render_cap_summary(
        summary,
        summary_path=Path("sdp/telemetry/steady-state-cap-summary.md"),
    )

    assert summary.result == "FAIL"
    assert summary.breach_count == 1
    assert "[sdp/telemetry/cost-model.md](cost-model.md)" in text
    assert "**Result:** FAIL" in text
    assert "**Breaches:** 1" in text
    assert "| 2026-04-27 | $5.5000 | $5.00 | BREACH (+$0.5000) |" in text


def test_cap_summary_fails_when_minimum_days_missing() -> None:
    rows = [
        sdp_cost.DailyCostRow(
            date="2026-04-27",
            runs=1,
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_cost_usd=1.0,
            models=["fallback"],
        )
    ]

    summary = sdp_cost.summarize_daily_cap(rows, daily_cap_usd=5.0, min_days=7)
    text = sdp_cost.render_cap_summary(summary)

    assert summary.result == "FAIL"
    assert summary.missing_days == 6
    assert summary.breach_count == 0
    assert "**Days checked:** 1 / 7" in text
    assert "Minimum days missing: 6" in text


def test_cli_writes_cap_summary_and_returns_failure_on_breach(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    _make_telemetry_db(db_path)
    out = tmp_path / "steady-state-cost.csv"
    summary_out = tmp_path / "steady-state-cap-summary.md"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "promptclaw.sdp_cost",
            "--db",
            str(db_path),
            "--days",
            "3",
            "--out",
            str(out),
            "--summary-out",
            str(summary_out),
            "--daily-cap-usd",
            "0.05",
            "--min-days",
            "3",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )

    assert result.returncode == 1
    assert str(out) in result.stdout
    assert str(summary_out) in result.stdout
    text = summary_out.read_text(encoding="utf-8")
    assert "**Result:** FAIL" in text
    assert "| 2026-04-25 | $0.5670 | $0.05 | BREACH (+$0.5170) |" in text


def test_committed_cap_summary_reports_current_csv_days() -> None:
    summary_path = Path("sdp/telemetry/steady-state-cap-summary.md")
    assert summary_path.exists()

    text = summary_path.read_text(encoding="utf-8")

    assert "[sdp/telemetry/cost-model.md](cost-model.md)" in text
    assert "**Result:** FAIL" in text
    assert text.count("| 2026-") == 7
    assert text.count("BREACH") >= 7
