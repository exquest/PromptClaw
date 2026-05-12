"""Tests for practice_curriculum.py -- deliberate away-mode study selection."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.practice_curriculum import select_practice_block


def test_away_practice_selects_named_block() -> None:
    block = select_practice_block(
        cadence_state="away_practice",
        family="forge",
        progression_profile="experiment",
        song_num=5,
    )

    assert block.name in {"Harmony Lab", "Melody Lab", "Arrangement Lab", "Ear Lab", "Scene Lab"}
    assert block.objective
    assert block.biases
    assert block.course_codes


def test_non_practice_state_returns_gentle_block() -> None:
    block = select_practice_block(
        cadence_state="occupied_day",
        family="bloom",
        progression_profile="open_day",
        song_num=1,
    )

    assert block.name == "Performance Weave"
    assert block.course_codes == ("EMSD-252", "EMSD-259")
