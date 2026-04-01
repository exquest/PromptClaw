"""Tests for the CypherClaw Tamagotchi runtime."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import tamagotchi


def test_pet_record_task_and_uptime_update_stats() -> None:
    pet = tamagotchi.Pet(
        "codex",
        {
            "xp": 49,
            "mood": 40,
            "hunger": 70,
            "energy": 100,
        },
    )

    xp, evolved = pet.record_task(success=True)
    uptime_xp, uptime_evolved = pet.record_uptime(180)

    assert xp == 10
    assert evolved is True
    assert uptime_xp == 3
    assert uptime_evolved is False
    assert pet.stage == 2
    assert pet.tasks_completed == 1
    assert pet.hunger == 0
    assert pet.mood == 55
    assert pet.energy == 97


def test_pet_manager_persists_task_transitions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pets_file = tmp_path / "pets.json"
    monkeypatch.setattr(tamagotchi, "PETS_FILE", pets_file)

    manager = tamagotchi.PetManager()
    manager.on_task_start("claude")

    persisted = json.loads(pets_file.read_text())
    assert persisted["pets"]["claude"]["state"] == "thinking"

    xp, evolved, pet = manager.on_task_end("claude", success=False, duration_s=120)

    assert xp == 4
    assert evolved is False
    assert pet.state == "error"
    assert pet.tasks_failed == 1
    assert pet.energy == 98

    manager.on_idle("claude", only_if={"error"})

    reloaded = tamagotchi.PetManager()
    assert reloaded.get("claude").state == "idle"


def test_decay_all_only_affects_idle_pets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pets_file = tmp_path / "pets.json"
    monkeypatch.setattr(tamagotchi, "PETS_FILE", pets_file)

    manager = tamagotchi.PetManager()
    now = datetime.now(timezone.utc)
    stale = (now - timedelta(hours=2)).isoformat()

    idle_pet = manager.get("codex")
    idle_pet.state = "idle"
    idle_pet.mood = 80
    idle_pet.hunger = 20
    idle_pet.energy = 30
    idle_pet.last_decay = stale

    active_pet = manager.get("gemini")
    active_pet.state = "thinking"
    active_pet.mood = 80
    active_pet.hunger = 20
    active_pet.energy = 30
    active_pet.last_decay = stale

    changed = manager.decay_all()

    assert changed is True
    assert idle_pet.mood < 80
    assert idle_pet.hunger > 20
    assert idle_pet.energy > 30
    assert active_pet.mood == 80
    assert active_pet.hunger == 20
    assert active_pet.energy == 30


def test_effective_state_prefers_sleeping_and_hungry_thresholds() -> None:
    pet = tamagotchi.Pet("gemini", {"state": "idle", "energy": 10, "hunger": 85, "mood": 80})
    assert pet.effective_state() == "sleeping"

    pet = tamagotchi.Pet("gemini", {"state": "idle", "energy": 90, "hunger": 85, "mood": 80})
    assert pet.effective_state() == "hungry"


def test_pet_exposes_rebirth_tracking_fields() -> None:
    pet = tamagotchi.Pet("claude")

    assert pet.incarnation == 1
    assert pet.critical_since is None
