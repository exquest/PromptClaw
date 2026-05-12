"""Depth-2 Tamagotchi diagnostics - locked test surface for frac-0035."""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import tamagotchi  # noqa: E402


def test_pet_health_and_activity_bands_are_meaningful() -> None:
    thriving = tamagotchi.Pet("claude", {"mood": 90, "hunger": 10, "energy": 90})
    stable = tamagotchi.Pet("codex", {"mood": 60, "hunger": 45, "energy": 55})
    strained = tamagotchi.Pet("gemini", {"mood": 42, "hunger": 78, "energy": 30})
    critical = tamagotchi.Pet("cypherclaw", {"mood": 15, "hunger": 92, "energy": 8})

    assert tamagotchi.pet_health_band(thriving) == "thriving"
    assert tamagotchi.pet_health_band(stable) == "stable"
    assert tamagotchi.pet_health_band(strained) == "strained"
    assert tamagotchi.pet_health_band(critical) == "critical"

    assert tamagotchi.pet_activity_band(tamagotchi.Pet("claude")) == "new"
    assert (
        tamagotchi.pet_activity_band(
            tamagotchi.Pet("claude", {"tasks_completed": 9, "tasks_failed": 1})
        )
        == "reliable"
    )
    assert (
        tamagotchi.pet_activity_band(
            tamagotchi.Pet("codex", {"tasks_completed": 3, "tasks_failed": 2})
        )
        == "mixed"
    )
    assert (
        tamagotchi.pet_activity_band(
            tamagotchi.Pet("gemini", {"tasks_completed": 2, "tasks_failed": 3})
        )
        == "fragile"
    )


def test_pet_vital_snapshot_reports_stage_progress_and_summary() -> None:
    pet = tamagotchi.Pet(
        "codex",
        {
            "xp": 220,
            "state": "thinking",
            "tasks_completed": 9,
            "tasks_failed": 1,
            "mood": 82,
            "hunger": 20,
            "energy": 76,
            "class_name": "Engineer",
        },
    )

    snapshot = tamagotchi.build_pet_vital_snapshot(pet)

    assert isinstance(snapshot, tamagotchi.PetVitalSnapshot)
    assert dataclasses.is_dataclass(snapshot)
    assert getattr(snapshot, "__dataclass_params__").frozen
    assert snapshot.agent == "codex"
    assert snapshot.stage == 3
    assert snapshot.stage_name == "Adult"
    assert snapshot.xp == 220
    assert snapshot.xp_to_next_stage == 280
    assert snapshot.effective_state == "thinking"
    assert snapshot.class_label == "Engineer"
    assert snapshot.health_band == "thriving"
    assert snapshot.activity_band == "reliable"
    assert snapshot.success_rate == pytest.approx(0.9)
    assert snapshot.needs_attention is False
    assert "codex" in snapshot.summary_line
    assert "Adult" in snapshot.summary_line
    assert "Engineer" in snapshot.summary_line
    assert "thriving" in snapshot.summary_line
    assert "reliable" in snapshot.summary_line


def test_pet_fleet_report_summarizes_health_and_attention() -> None:
    pets = {
        "gemini": tamagotchi.Pet(
            "gemini",
            {
                "xp": 40,
                "state": "idle",
                "tasks_completed": 1,
                "tasks_failed": 4,
                "mood": 25,
                "hunger": 88,
                "energy": 20,
            },
        ),
        "claude": tamagotchi.Pet(
            "claude",
            {
                "xp": 510,
                "state": "idle",
                "tasks_completed": 10,
                "tasks_failed": 0,
                "mood": 90,
                "hunger": 15,
                "energy": 80,
                "class_name": "Scholar",
            },
        ),
        "cypherclaw": tamagotchi.Pet(
            "cypherclaw",
            {"xp": 10, "state": "sleeping", "mood": 75, "hunger": 35, "energy": 15},
        ),
        "codex": tamagotchi.Pet(
            "codex",
            {
                "xp": 60,
                "state": "communicating",
                "tasks_completed": 2,
                "tasks_failed": 0,
                "mood": 70,
                "hunger": 30,
                "energy": 65,
                "class_name": "Engineer",
            },
        ),
    }

    report = tamagotchi.build_pet_fleet_report(pets)
    summary = tamagotchi.summarize_pet_fleet_report(report)

    assert isinstance(report, tamagotchi.PetFleetReport)
    assert dataclasses.is_dataclass(report)
    assert getattr(report, "__dataclass_params__").frozen
    assert tuple(snapshot.agent for snapshot in report.snapshots) == (
        "claude",
        "codex",
        "gemini",
        "cypherclaw",
    )
    assert report.total_pets == 4
    assert report.total_xp == 620
    assert report.total_tasks == 17
    assert report.leader_agent == "claude"
    assert report.active_agents == ("codex",)
    assert report.sleeping_agents == ("cypherclaw",)
    assert report.attention_agents == ("gemini", "cypherclaw")
    assert report.health_counts == {
        "thriving": 1,
        "stable": 1,
        "strained": 2,
        "critical": 0,
    }
    assert summary["mean_mood"] == 65.0
    assert summary["mean_hunger"] == 42.0
    assert summary["mean_energy"] == 45.0
    assert summary["attention_agents"] == ["gemini", "cypherclaw"]
    assert summary["snapshots"][0]["agent"] == "claude"
    assert summary["snapshots"][0]["class_label"] == "Scholar"


def test_pet_manager_fleet_report_round_trips_through_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pets_file = tmp_path / "pets.json"
    monkeypatch.setattr(tamagotchi, "PETS_FILE", pets_file)

    manager = tamagotchi.PetManager()
    manager.on_task_start("codex")
    xp, evolved, pet = manager.on_task_end("codex", success=True, duration_s=180)
    report = manager.fleet_report()
    summary = tamagotchi.summarize_pet_fleet_report(report)

    assert xp == 13
    assert evolved is False
    assert pet.xp == 13
    assert report.leader_agent == "codex"
    assert summary["total_xp"] == 13
    assert summary["snapshots"][1]["agent"] == "codex"
    assert summary["snapshots"][1]["activity_band"] == "mixed"

    persisted = json.loads(pets_file.read_text())
    assert persisted["version"] == 2
    assert persisted["pets"]["codex"]["xp"] == 13

    reloaded = tamagotchi.PetManager()
    reloaded_report = reloaded.fleet_report()

    assert reloaded.get("codex").xp == 13
    assert reloaded_report.leader_agent == "codex"
    assert reloaded_report.total_xp == report.total_xp


def test_tamagotchi_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/tamagotchi.py")
    assert result.depth >= 2, result.reason
