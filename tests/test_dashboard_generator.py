"""Compatibility tests for dashboard_generator.py."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "my-claw" / "tools"))

from dashboard_generator import (
    CLASS_EMOJI,
    _bar_html,
    _format_event,
    _format_timestamp,
    _service_pill_class,
    _stage_for_xp,
    collect_events,
    collect_pet_classes,
    collect_pets,
    collect_pipeline,
    generate_dashboard,
    generate_html,
)


class TestStageForXP:
    def test_zero_xp(self) -> None:
        assert _stage_for_xp(0) == 1

    def test_baby(self) -> None:
        assert _stage_for_xp(10) == 1

    def test_teen(self) -> None:
        assert _stage_for_xp(50) == 2

    def test_adult(self) -> None:
        assert _stage_for_xp(200) == 3

    def test_elite(self) -> None:
        assert _stage_for_xp(500) == 4

    def test_master(self) -> None:
        assert _stage_for_xp(1000) == 5

    def test_beyond_master(self) -> None:
        assert _stage_for_xp(9999) == 5


class TestBarHtml:
    def test_zero(self) -> None:
        html = _bar_html(0)
        assert "width:0%" in html

    def test_full(self) -> None:
        html = _bar_html(100)
        assert "width:100%" in html

    def test_half(self) -> None:
        html = _bar_html(50)
        assert "width:50%" in html

    def test_custom_color(self) -> None:
        html = _bar_html(50, color="#ff0000")
        assert "#ff0000" in html

    def test_over_max_clamped(self) -> None:
        html = _bar_html(200, max_val=100)
        assert "width:100%" in html

    def test_zero_max(self) -> None:
        html = _bar_html(50, max_val=0)
        assert "width:0%" in html


class TestServicePillClass:
    def test_active(self) -> None:
        assert _service_pill_class("active") == "status-active"

    def test_inactive(self) -> None:
        assert _service_pill_class("inactive") == "status-inactive"

    def test_idle(self) -> None:
        assert _service_pill_class("idle") == "status-inactive"

    def test_failed(self) -> None:
        assert _service_pill_class("failed") == "status-error"

    def test_unknown(self) -> None:
        assert _service_pill_class("something") == "status-inactive"


class TestFormatTimestamp:
    def test_iso(self) -> None:
        assert _format_timestamp("2026-03-30T07:30:01+00:00") == "07:30"

    def test_short(self) -> None:
        assert _format_timestamp("12:45") == "12:45"

    def test_empty(self) -> None:
        assert _format_timestamp("") == "??:??"


class TestFormatEvent:
    def test_heartbeat(self) -> None:
        ev = {"type": "heartbeat", "data": {"uptime": "5h", "io_pct": 2.1, "load_1m": 0.3}}
        result = _format_event(ev)
        assert "5h" in result
        assert "2.1%" in result

    def test_health_check(self) -> None:
        ev = {"type": "health_check", "data": {"healthy": True, "warnings": 0}}
        assert "Healthy" in _format_event(ev)

    def test_health_check_unhealthy(self) -> None:
        ev = {"type": "health_check", "data": {"healthy": False, "warnings": 3}}
        result = _format_event(ev)
        assert "UNHEALTHY" in result
        assert "3" in result

    def test_task_result(self) -> None:
        ev = {"type": "task_result", "data": {"agent": "claude", "success": True}}
        assert "claude" in _format_event(ev)
        assert "success" in _format_event(ev)

    def test_unknown_type(self) -> None:
        ev = {"type": "custom", "data": {"key": "value"}}
        result = _format_event(ev)
        assert "value" in result

    def test_xss_escaped(self) -> None:
        ev = {"type": "custom", "data": "<script>alert(1)</script>"}
        result = _format_event(ev)
        assert "<script>" not in result


class TestCollectPipeline:
    def test_with_tasks(self, tmp_path: Path) -> None:
        db = tmp_path / "state.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE tasks (id TEXT, status TEXT)")
        conn.executemany(
            "INSERT INTO tasks VALUES (?, ?)",
            [("t1", "complete"), ("t2", "complete"), ("t3", "pending"), ("t4", "running"), ("t5", "blocked"), ("t6", "skipped")],
        )
        conn.commit()
        conn.close()

        result = collect_pipeline(db)
        assert result["total"] == 6
        assert result["complete"] == 2
        assert result["pending"] == 1
        assert result["running"] == 1
        assert result["blocked"] == 1
        assert result["skipped"] == 1

    def test_missing_db(self, tmp_path: Path) -> None:
        result = collect_pipeline(tmp_path / "nope.db")
        assert result["total"] == 0

    def test_empty_db(self, tmp_path: Path) -> None:
        db = tmp_path / "state.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE tasks (id TEXT, status TEXT)")
        conn.commit()
        conn.close()

        result = collect_pipeline(db)
        assert result["total"] == 0


class TestCollectPets:
    def test_valid_pets(self, tmp_path: Path) -> None:
        pets_file = tmp_path / "pets.json"
        pets_file.write_text(
            json.dumps(
                {
                    "version": 2,
                    "pets": {
                        "claude": {
                            "xp": 966,
                            "stage": 4,
                            "mood": 100,
                            "energy": 100,
                            "hunger": 0,
                            "state": "idle",
                            "tasks_completed": 50,
                            "tasks_failed": 5,
                        },
                        "codex": {
                            "xp": 2,
                            "stage": 1,
                            "mood": 4,
                            "energy": 100,
                            "hunger": 0,
                            "state": "thinking",
                            "tasks_completed": 1,
                            "tasks_failed": 1,
                        },
                    },
                }
            )
        )
        result = collect_pets(pets_file, class_overrides={})
        assert len(result) == 2
        assert result[0]["agent"] == "claude"
        assert result[0]["stage_name"] == "Elite"
        assert result[0]["success_rate"] == 90
        assert result[1]["agent"] == "codex"
        assert result[1]["success_rate"] == 50

    def test_missing_file(self, tmp_path: Path) -> None:
        assert collect_pets(tmp_path / "nope.json", class_overrides={}) == []

    def test_no_tasks(self, tmp_path: Path) -> None:
        pets_file = tmp_path / "pets.json"
        pets_file.write_text(json.dumps({"pets": {"claude": {"xp": 0, "mood": 80, "energy": 100, "hunger": 50, "state": "idle"}}}))
        result = collect_pets(pets_file, class_overrides={})
        assert result[0]["success_rate"] is None

    def test_pets_with_class_overrides(self, tmp_path: Path) -> None:
        pets_file = tmp_path / "pets.json"
        pets_file.write_text(
            json.dumps(
                {
                    "pets": {
                        "claude": {
                            "xp": 500,
                            "mood": 80,
                            "energy": 90,
                            "hunger": 10,
                            "state": "idle",
                            "tasks_completed": 20,
                            "tasks_failed": 2,
                        },
                        "codex": {
                            "xp": 100,
                            "mood": 60,
                            "energy": 70,
                            "hunger": 30,
                            "state": "thinking",
                            "tasks_completed": 5,
                            "tasks_failed": 0,
                        },
                    },
                }
            )
        )
        overrides = {"claude": ("Scholar", 7), "codex": ("Engineer", 3)}
        result = collect_pets(pets_file, class_overrides=overrides)
        assert len(result) == 2
        assert result[0]["class_name"] == "Scholar"
        assert result[0]["class_level"] == 7
        assert result[1]["class_name"] == "Engineer"
        assert result[1]["class_level"] == 3

    def test_pets_without_class_data(self, tmp_path: Path) -> None:
        pets_file = tmp_path / "pets.json"
        pets_file.write_text(
            json.dumps(
                {
                    "pets": {
                        "gemini": {
                            "xp": 10,
                            "mood": 50,
                            "energy": 50,
                            "hunger": 50,
                            "state": "idle",
                            "tasks_completed": 0,
                            "tasks_failed": 0,
                        }
                    }
                }
            )
        )
        result = collect_pets(pets_file, class_overrides={})
        assert result[0]["class_name"] is None
        assert result[0]["class_level"] is None


class TestCollectPetClasses:
    def test_graceful_failure_without_db(self) -> None:
        result = collect_pet_classes()
        assert isinstance(result, dict)


class TestClassEmoji:
    def test_all_classes_have_emoji(self) -> None:
        for cls in ("Scholar", "Engineer", "Explorer", "Artist", "Guardian", "Diplomat"):
            assert cls in CLASS_EMOJI


class TestCollectEvents:
    def test_events(self, tmp_path: Path) -> None:
        db = tmp_path / "observatory.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE events (event_type TEXT, timestamp TEXT, data TEXT)")
        conn.execute(
            "INSERT INTO events VALUES (?, ?, ?)",
            ("heartbeat", "2026-03-30T07:30:01+00:00", '{"uptime": "5h"}'),
        )
        conn.commit()
        conn.close()

        result = collect_events(db, limit=5)
        assert len(result) == 1
        assert result[0]["type"] == "heartbeat"

    def test_missing_db(self, tmp_path: Path) -> None:
        assert collect_events(tmp_path / "nope.db") == []


class TestGenerateHtml:
    def test_contains_required_elements(self) -> None:
        html = generate_html(
            vitals={
                "uptime": "5h",
                "load": (0.1, 0.2, 0.3),
                "cores": 12,
                "mem_pct": 3.0,
                "mem_avail_mb": 60000,
                "mem_total_mb": 62000,
                "disk_pct": 4,
                "io_pct": 1.5,
                "temp_c": 39,
            },
            services=[{"name": "PostgreSQL", "status": "active"}, {"name": "Redis", "status": "active"}],
            pipeline={"total": 100, "complete": 25, "pending": 60, "running": 5, "blocked": 10, "skipped": 0},
            pets=[
                {
                    "agent": "claude",
                    "stage": 4,
                    "stage_name": "Elite",
                    "xp": 966,
                    "mood": 100,
                    "energy": 100,
                    "hunger": 0,
                    "state": "idle",
                    "success_rate": 90,
                    "tasks_completed": 50,
                    "tasks_failed": 5,
                    "class_name": "Scholar",
                    "class_level": 7,
                }
            ],
            events=[],
            quality={},
            now=datetime(2026, 3, 30, 8, 0, 0, tzinfo=timezone.utc),
        )

        assert 'http-equiv="refresh" content="60"' in html
        assert "<script" not in html
        assert "5h" in html
        assert "0.1" in html
        assert "3.0%" in html
        assert "39C" in html
        assert "PostgreSQL" in html
        assert "status-active" in html
        assert "25/100" in html
        assert "25.0%" in html
        assert "CLAUDE" in html
        assert "Elite" in html
        assert "966" in html
        assert "Scholar" in html
        assert "Lv.7" in html
        assert "2026-03-30 08:00:00 UTC" in html

    def test_pet_without_class(self) -> None:
        html = generate_html(
            vitals={"uptime": "1h", "load": (0, 0, 0), "cores": 1, "mem_pct": 0, "mem_avail_mb": 0, "mem_total_mb": 0, "disk_pct": 0, "io_pct": 0, "temp_c": None},
            services=[],
            pipeline={"total": 0, "complete": 0, "pending": 0, "running": 0, "blocked": 0, "skipped": 0},
            pets=[
                {
                    "agent": "gemini",
                    "stage": 1,
                    "stage_name": "Baby",
                    "xp": 5,
                    "mood": 50,
                    "energy": 50,
                    "hunger": 50,
                    "state": "idle",
                    "success_rate": None,
                    "tasks_completed": 0,
                    "tasks_failed": 0,
                    "class_name": None,
                    "class_level": None,
                }
            ],
            events=[],
            quality={},
        )
        assert "Unclassed" in html

    def test_no_javascript(self) -> None:
        html = generate_html(
            vitals={"uptime": "1h", "load": (0, 0, 0), "cores": 1, "mem_pct": 0, "mem_avail_mb": 0, "mem_total_mb": 0, "disk_pct": 0, "io_pct": 0, "temp_c": None},
            services=[],
            pipeline={"total": 0, "complete": 0, "pending": 0, "running": 0, "blocked": 0, "skipped": 0},
            pets=[],
            events=[],
            quality={},
        )
        assert "<script" not in html
        assert "javascript" not in html.lower()

    def test_valid_html_structure(self) -> None:
        html = generate_html(
            vitals={"uptime": "1h", "load": (0, 0, 0), "cores": 1, "mem_pct": 0, "mem_avail_mb": 0, "mem_total_mb": 0, "disk_pct": 0, "io_pct": 0, "temp_c": None},
            services=[],
            pipeline={"total": 0, "complete": 0, "pending": 0, "running": 0, "blocked": 0, "skipped": 0},
            pets=[],
            events=[],
            quality={},
        )
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert '<meta http-equiv="refresh" content="60">' in html

    def test_xss_protection(self) -> None:
        html = generate_html(
            vitals={"uptime": "<script>alert(1)</script>", "load": (0, 0, 0), "cores": 1, "mem_pct": 0, "mem_avail_mb": 0, "mem_total_mb": 0, "disk_pct": 0, "io_pct": 0, "temp_c": None},
            services=[{"name": "<b>evil</b>", "status": "active"}],
            pipeline={"total": 0, "complete": 0, "pending": 0, "running": 0, "blocked": 0, "skipped": 0},
            pets=[],
            events=[],
            quality={},
        )
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


class TestGenerateDashboard:
    def test_writes_file(self, tmp_path: Path) -> None:
        output = tmp_path / "index.html"
        pets_file = tmp_path / "pets.json"
        pets_file.write_text(json.dumps({"pets": {}}))

        sdp_db = tmp_path / "state.db"
        conn = sqlite3.connect(str(sdp_db))
        conn.execute("CREATE TABLE tasks (id TEXT, status TEXT)")
        conn.commit()
        conn.close()

        obs_db = tmp_path / "obs.db"
        conn = sqlite3.connect(str(obs_db))
        conn.execute("CREATE TABLE events (event_type TEXT, timestamp TEXT, data TEXT)")
        conn.commit()
        conn.close()

        generate_dashboard(output=output, sdp_db=sdp_db, obs_db=obs_db, pets_file=pets_file)

        assert output.exists()
        content = output.read_text()
        assert "CypherClaw Dashboard" in content
        assert '<meta http-equiv="refresh" content="60">' in content
        assert "<script" not in content
