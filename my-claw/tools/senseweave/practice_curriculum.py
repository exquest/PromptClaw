"""Deliberate practice selection for away-mode CypherClaw songs."""
from __future__ import annotations

from dataclasses import dataclass

from .rollout_controls import SenseWeaveFeatureFlags, load_feature_flags


@dataclass(frozen=True)
class PracticeBlock:
    name: str
    objective: str
    biases: dict[str, float]
    course_codes: tuple[str, ...]


_BLOCKS = {
    "harmony_lab": PracticeBlock(
        name="Harmony Lab",
        objective="Explore substitutions and cadence weight.",
        biases={"reharm": 0.8, "density": 0.4, "risk": 0.55},
        course_codes=("EMSD-110", "EMSD-302"),
    ),
    "melody_lab": PracticeBlock(
        name="Melody Lab",
        objective="Develop contour and answering phrases.",
        biases={"hooks": 0.8, "leaps": 0.45, "density": 0.35},
        course_codes=("EMSD-110", "EMSD-303"),
    ),
    "arrangement_lab": PracticeBlock(
        name="Arrangement Lab",
        objective="Vary layering and groove contrast.",
        biases={"arrangement": 0.8, "groove": 0.7, "density": 0.5},
        course_codes=("EMSD-210", "EMSD-301"),
    ),
    "ear_lab": PracticeBlock(
        name="Ear Lab",
        objective="Listen for cadence clarity and interval balance.",
        biases={"ear": 0.85, "space": 0.55, "resolution": 0.65},
        course_codes=("EMSD-120", "EMSD-254"),
    ),
    "scene_lab": PracticeBlock(
        name="Scene Lab",
        objective="Practice scene pivots and formal contrast.",
        biases={"form": 0.85, "transition": 0.75, "density": 0.45},
        course_codes=("EMSD-253", "EMSD-258"),
    ),
    "performance_weave": PracticeBlock(
        name="Performance Weave",
        objective="Integrate the current voice into a stable performance arc.",
        biases={"continuity": 0.8, "clarity": 0.7, "risk": 0.25},
        course_codes=("EMSD-252", "EMSD-259"),
    ),
}


def select_practice_block(
    *,
    cadence_state: str,
    family: str,
    progression_profile: str,
    song_num: int,
    flags: SenseWeaveFeatureFlags | None = None,
) -> PracticeBlock:
    """Choose the current practice emphasis."""

    active_flags = flags or load_feature_flags()
    if not active_flags.curriculum_exercise:
        return _BLOCKS["performance_weave"]

    if cadence_state != "away_practice":
        return _BLOCKS["performance_weave"]

    cycle = (
        "harmony_lab"
        if family in {"forge", "pulse"}
        else "ear_lab"
        if progression_profile in {"stillness", "settling"}
        else "scene_lab"
        if progression_profile in {"procession", "lift"}
        else "melody_lab"
        if family in {"ember", "drift"}
        else "arrangement_lab"
    )
    ordered = ["harmony_lab", "melody_lab", "arrangement_lab", "ear_lab", "scene_lab"]
    if cycle in ordered:
        index = (ordered.index(cycle) + max(song_num - 1, 0)) % len(ordered)
        return _BLOCKS[ordered[index]]
    return _BLOCKS["arrangement_lab"]
