"""Reharmonization and functional section planning for CypherClaw."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

HARMONIC_FUNCTIONS: tuple[str, ...] = (
    "tonic",
    "subdominant",
    "dominant",
    "secondary_dominant",
    "modal_interchange",
    "tritone_sub",
    "chromatic_mediant",
    "pedal",
    "planing",
    "modulation",
)

PHASE_TENSION: dict[str, float] = {
    "Emergence": 0.2,
    "Theme": 0.35,
    "Development": 0.65,
    "Bridge": 0.8,
    "Recap": 0.5,
    "Release": 0.4,
    "Resolution": 0.25,
    "Afterglow": 0.1,
}

FUNCTION_TENSION: dict[str, float] = {
    "tonic": 0.1,
    "subdominant": 0.3,
    "dominant": 0.7,
    "secondary_dominant": 0.8,
    "modal_interchange": 0.5,
    "tritone_sub": 0.85,
    "chromatic_mediant": 0.6,
    "pedal": 0.2,
    "planing": 0.4,
    "modulation": 0.65,
    "predominant": 0.3,
    "deceptive": 0.55,
    "plagal": 0.15,
    "suspended": 0.25,
}

TRANSITION_INTENTS: tuple[str, ...] = (
    "establish",
    "maintain",
    "pivot",
    "common_tone",
    "direct",
    "chromatic",
    "return",
    "dissolve",
)


def label_harmonic_function(
    degree: int,
    *,
    mode: str = "ionian",
    chromatic_alteration: int = 0,
    is_secondary: bool = False,
    bass_is_pedal: bool = False,
    is_parallel_motion: bool = False,
    is_pivot: bool = False,
) -> str:
    """Label the harmonic function of a chord given its scale degree and context."""
    if is_pivot:
        return "modulation"
    if bass_is_pedal:
        return "pedal"
    if is_parallel_motion:
        return "planing"
    if is_secondary:
        return "secondary_dominant"
    if chromatic_alteration != 0:
        if degree == 2 and chromatic_alteration == -1:
            return "tritone_sub"
        if degree in (3, 6):
            return "chromatic_mediant"
        return "modal_interchange"
    if degree in (1,):
        return "tonic"
    if degree in (3, 6):
        return "tonic"
    if degree in (2, 4):
        return "subdominant"
    if degree in (5, 7):
        return "dominant"
    return "tonic"


def tension_for_function(function: str) -> float:
    """Return the inherent tension level (0.0–1.0) for a harmonic function."""
    return FUNCTION_TENSION.get(function, 0.5)


def tension_for_phase(scene_name: str) -> float:
    """Return the target tension level (0.0–1.0) for a scene phase."""
    return PHASE_TENSION.get(scene_name, 0.5)


@dataclass(frozen=True)
class SectionHarmony:
    scene_name: str
    function: str
    cadence: str
    progression: tuple[tuple[int, ...], ...]
    borrowed_color: str = ""
    transition_intent: str = "maintain"
    harmonic_function: str = "tonic"


@dataclass(frozen=True)
class ReharmPlan:
    strategy: str
    study_focus: str
    sections: Mapping[str, SectionHarmony]


_FUNCTION_BANKS: dict[str, tuple[tuple[int, ...], ...]] = {
    "tonic": ((1, 1, 4, 1), (1, 5, 1, 1), (1, 6, 4, 1)),
    "predominant": ((1, 4, 2, 5), (1, 2, 5, 1), (1, 4, 5, 1)),
    "subdominant": ((1, 4, 2, 5), (1, 2, 4, 1), (4, 2, 5, 1)),
    "dominant": ((2, 5, 1, 1), (4, 5, 1, 6), (2, 5, 6, 5)),
    "secondary_dominant": ((5, 5, 1, 1), (2, 5, 5, 1), (5, 1, 5, 1)),
    "modal_interchange": ((1, 7, 4, 1), (1, 3, 4, 1), (4, 7, 1, 1)),
    "tritone_sub": ((2, 1, 4, 1), (4, 2, 1, 1), (2, 5, 1, 1)),
    "chromatic_mediant": ((1, 6, 3, 1), (1, 3, 6, 1), (6, 1, 3, 1)),
    "pedal": ((1, 4, 5, 1), (1, 2, 5, 1), (1, 1, 4, 1)),
    "planing": ((1, 2, 3, 4), (4, 3, 2, 1), (5, 4, 3, 2)),
    "modulation": ((1, 5, 5, 1), (1, 4, 5, 1), (2, 5, 1, 5)),
    "deceptive": ((1, 5, 6, 4), (2, 5, 6, 1), (4, 5, 6, 5)),
    "plagal": ((1, 4, 1, 1), (1, 4, 5, 1), (1, 4, 1, 5)),
    "suspended": ((1, 5, 1, 4), (1, 1, 5, 1), (1, 4, 1, 5)),
}


_SCENE_TRANSITION_INTENTS: dict[str, str] = {
    "Emergence": "establish",
    "Theme": "maintain",
    "Development": "pivot",
    "Bridge": "chromatic",
    "Recap": "return",
    "Release": "maintain",
    "Resolution": "maintain",
    "Afterglow": "dissolve",
}

_FUNCTION_TO_HARMONIC_FUNCTION: dict[str, str] = {
    "tonic": "tonic",
    "predominant": "subdominant",
    "subdominant": "subdominant",
    "dominant": "dominant",
    "deceptive": "dominant",
    "plagal": "subdominant",
    "suspended": "pedal",
    "secondary_dominant": "secondary_dominant",
    "modal_interchange": "modal_interchange",
    "tritone_sub": "tritone_sub",
    "chromatic_mediant": "chromatic_mediant",
    "pedal": "pedal",
    "planing": "planing",
    "modulation": "modulation",
}


def _transition_intent_for_scene(
    scene_name: str,
    *,
    modulation_intent: str = "steady",
    strategy: str = "",
) -> str:
    if modulation_intent == "modulate" and scene_name in {"Development", "Bridge"}:
        return "pivot" if scene_name == "Development" else "common_tone"
    if strategy == "modal_interchange" and scene_name in {"Development", "Bridge"}:
        return "direct"
    return _SCENE_TRANSITION_INTENTS.get(scene_name, "maintain")


def _section_profile(
    progression_profile: str,
    *,
    cadence_state: str,
    family: str,
    mode: str,
) -> dict[str, tuple[str, str]]:
    if cadence_state in {"sleep", "wind_down"}:
        return {
            "Emergence": ("tonic", "half"),
            "Theme": ("tonic", "plagal"),
            "Development": ("predominant", "half"),
            "Bridge": ("dominant", "deceptive"),
            "Recap": ("tonic", "plagal"),
            "Release": ("tonic", "plagal"),
            "Resolution": ("plagal", "plagal"),
            "Afterglow": ("suspended", "plagal"),
        }
    if cadence_state == "away_practice":
        return {
            "Emergence": ("tonic", "half"),
            "Theme": ("predominant", "half"),
            "Development": ("dominant", "deceptive"),
            "Bridge": ("deceptive", "deceptive"),
            "Recap": ("tonic", "authentic"),
            "Release": ("tonic", "authentic"),
            "Resolution": ("tonic", "authentic"),
            "Afterglow": ("suspended", "plagal"),
        }

    if progression_profile in {"settling", "stillness"}:
        return {
            "Emergence": ("tonic", "half"),
            "Theme": ("tonic", "half"),
            "Development": ("predominant", "half"),
            "Bridge": ("dominant", "deceptive"),
            "Recap": ("tonic", "authentic"),
            "Release": ("tonic", "authentic"),
            "Resolution": ("plagal", "plagal"),
            "Afterglow": ("suspended", "plagal"),
        }
    if progression_profile in {"lift", "procession"}:
        return {
            "Emergence": ("predominant", "half"),
            "Theme": ("tonic", "half"),
            "Development": ("dominant", "deceptive"),
            "Bridge": ("dominant", "half"),
            "Recap": ("tonic", "authentic"),
            "Release": ("tonic", "authentic"),
            "Resolution": ("plagal", "authentic"),
            "Afterglow": ("suspended", "plagal"),
        }
    if mode in {"aeolian", "dorian", "phrygian", "harmonic_minor", "melodic_minor"} or family in {"drift", "forge"}:
        return {
            "Emergence": ("tonic", "half"),
            "Theme": ("predominant", "half"),
            "Development": ("dominant", "deceptive"),
            "Bridge": ("deceptive", "deceptive"),
            "Recap": ("tonic", "authentic"),
            "Release": ("tonic", "authentic"),
            "Resolution": ("plagal", "plagal"),
            "Afterglow": ("suspended", "plagal"),
        }
    return {
        "Emergence": ("tonic", "half"),
        "Theme": ("tonic", "half"),
        "Development": ("predominant", "deceptive"),
        "Bridge": ("dominant", "half"),
        "Recap": ("tonic", "authentic"),
        "Release": ("tonic", "authentic"),
        "Resolution": ("plagal", "authentic"),
        "Afterglow": ("suspended", "plagal"),
    }


def _strategy_for_context(
    progression_profile: str,
    *,
    cadence_state: str,
    family: str,
    song_num: int,
) -> tuple[str, str]:
    if cadence_state == "away_practice":
        sequence = (
            ("modal_interchange", "harmony_lab"),
            ("secondary_push", "scene_lab"),
            ("approach_chain", "ear_lab"),
            ("bass_reframe", "arrangement_lab"),
        )
        return sequence[(song_num - 1) % len(sequence)]
    if progression_profile in {"settling", "stillness"}:
        return ("plagal_release", "melody_lab")
    if family in {"forge", "pulse"}:
        return ("secondary_push", "harmony_lab")
    return ("borrowed_color", "performance_weave")


def reharm_plan_for_song(
    progression_profile: str,
    *,
    family: str,
    cadence_state: str,
    mode: str,
    song_num: int,
) -> ReharmPlan:
    """Return a functional harmony plan for one CypherClaw song."""

    strategy, study_focus = _strategy_for_context(
        progression_profile,
        cadence_state=cadence_state,
        family=family,
        song_num=song_num,
    )
    section_profile = _section_profile(
        progression_profile,
        cadence_state=cadence_state,
        family=family,
        mode=mode,
    )
    sections = {
        scene_name: SectionHarmony(
            scene_name=scene_name,
            function=function,
            cadence=cadence,
            progression=_FUNCTION_BANKS[function],
            borrowed_color=(
                "modal_interchange"
                if strategy == "modal_interchange" and function in {"predominant", "deceptive"}
                else "secondary_dominant"
                if strategy == "secondary_push" and function in {"dominant", "predominant"}
                else "pedal_tone"
                if strategy == "bass_reframe" and function == "tonic"
                else ""
            ),
            transition_intent=_transition_intent_for_scene(
                scene_name, strategy=strategy,
            ),
            harmonic_function=_FUNCTION_TO_HARMONIC_FUNCTION.get(function, "tonic"),
        )
        for scene_name, (function, cadence) in section_profile.items()
    }
    return ReharmPlan(strategy=strategy, study_focus=study_focus, sections=sections)


def progression_bank_for_section(scene_name: str, plan: ReharmPlan) -> tuple[tuple[int, ...], ...]:
    section = plan.sections.get(scene_name)
    if section is None:
        section = plan.sections.get("Theme")
    if section is None:
        return ()
    return section.progression
