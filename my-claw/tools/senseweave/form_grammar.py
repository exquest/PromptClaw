"""Section-function grammar and form planning for score-tree composition."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from .piece_brief import PieceBrief
from .piece_commission import PieceCommission

SectionFunction = Literal[
    "invocation",
    "verse",
    "statement",
    "lift",
    "pre_chorus",
    "chorus",
    "arrival",
    "refrain",
    "build",
    "drop",
    "ambient",
    "episode",
    "return",
    "turn",
    "bridge",
    "through_line",
    "development",
    "breakdown",
    "instrumental_response",
    "recap",
    "coda",
    "residue",
    "afterglow",
]


@dataclass(frozen=True)
class PlannedSection:
    scene_name: str
    function: SectionFunction
    target_duration_s: float
    return_from: str | None = None
    transform_strength: str = "none"
    harmonic_role: str = "tonic"


@dataclass(frozen=True)
class FormPlan:
    form_family: str
    form_class: str
    composition_mode: str
    sections: tuple[PlannedSection, ...]
    ending_family: str

    @property
    def section_functions(self) -> tuple[str, ...]:
        return tuple(section.function for section in self.sections)


PhraseFamily = Literal[
    "seed",
    "variant",
    "development",
    "response",
    "liquidation",
]


@dataclass(frozen=True)
class PhraseFamilySlot:
    """Blueprint for one phrase within a section's fractal expansion."""

    family: PhraseFamily
    transform_ops: tuple[str, ...]
    is_seed: bool = False


# Maps (section_function) → ordered phrase-family slots.
# The first slot is always the seed; subsequent slots derive from it.
_PHRASE_FAMILY_TEMPLATES: dict[SectionFunction, tuple[PhraseFamilySlot, ...]] = {
    "invocation": (
        PhraseFamilySlot("seed", (), is_seed=True),
        PhraseFamilySlot("variant", ("thin",)),
    ),
    "verse": (
        PhraseFamilySlot("seed", (), is_seed=True),
        PhraseFamilySlot("variant", ("reharmonize",)),
    ),
    "statement": (
        PhraseFamilySlot("seed", (), is_seed=True),
        PhraseFamilySlot("variant", ("reharmonize",)),
    ),
    "lift": (
        PhraseFamilySlot("seed", (), is_seed=True),
        PhraseFamilySlot("variant", ("expand",)),
    ),
    "pre_chorus": (
        PhraseFamilySlot("seed", (), is_seed=True),
        PhraseFamilySlot("variant", ("expand", "rotate")),
    ),
    "chorus": (
        PhraseFamilySlot("seed", ("answer",), is_seed=True),
        PhraseFamilySlot("response", ("answer", "expand")),
    ),
    "arrival": (
        PhraseFamilySlot("seed", (), is_seed=True),
        PhraseFamilySlot("response", ("answer",)),
    ),
    "refrain": (
        PhraseFamilySlot("seed", (), is_seed=True),
        PhraseFamilySlot("variant", ("reharmonize",)),
    ),
    "build": (
        PhraseFamilySlot("seed", ("expand",), is_seed=True),
        PhraseFamilySlot("development", ("expand", "rotate")),
    ),
    "drop": (
        PhraseFamilySlot("seed", ("answer",), is_seed=True),
        PhraseFamilySlot("response", ("answer", "thin")),
    ),
    "ambient": (
        PhraseFamilySlot("seed", ("thin",), is_seed=True),
        PhraseFamilySlot("variant", ("thin", "rotate")),
    ),
    "episode": (
        PhraseFamilySlot("seed", ("expand",), is_seed=True),
        PhraseFamilySlot("development", ("expand", "invert")),
    ),
    "return": (
        PhraseFamilySlot("seed", ("answer",), is_seed=True),
        PhraseFamilySlot("variant", ("reharmonize", "answer")),
    ),
    "turn": (
        PhraseFamilySlot("seed", ("expand",), is_seed=True),
        PhraseFamilySlot("development", ("expand", "invert")),
        PhraseFamilySlot("response", ("answer", "rotate")),
    ),
    "bridge": (
        PhraseFamilySlot("seed", ("expand",), is_seed=True),
        PhraseFamilySlot("development", ("expand", "invert")),
        PhraseFamilySlot("response", ("answer", "rotate")),
    ),
    "through_line": (
        PhraseFamilySlot("seed", ("expand",), is_seed=True),
        PhraseFamilySlot("development", ("expand", "rotate")),
        PhraseFamilySlot("liquidation", ("thin", "answer")),
    ),
    "development": (
        PhraseFamilySlot("seed", ("expand",), is_seed=True),
        PhraseFamilySlot("development", ("expand", "rotate")),
        PhraseFamilySlot("liquidation", ("thin", "answer")),
    ),
    "breakdown": (
        PhraseFamilySlot("seed", (), is_seed=True),
        PhraseFamilySlot("liquidation", ("thin",)),
    ),
    "instrumental_response": (
        PhraseFamilySlot("seed", (), is_seed=True),
        PhraseFamilySlot("response", ("answer", "expand")),
    ),
    "recap": (
        PhraseFamilySlot("seed", ("answer",), is_seed=True),
        PhraseFamilySlot("variant", ("reharmonize", "answer", "rotate")),
    ),
    "coda": (
        PhraseFamilySlot("seed", ("answer",), is_seed=True),
        PhraseFamilySlot("liquidation", ("thin", "answer")),
    ),
    "residue": (
        PhraseFamilySlot("seed", ("answer",), is_seed=True),
        PhraseFamilySlot("liquidation", ("thin",)),
    ),
    "afterglow": (
        PhraseFamilySlot("seed", ("answer",), is_seed=True),
        PhraseFamilySlot("liquidation", ("thin", "answer")),
    ),
}


def phrase_family_slots(
    function: SectionFunction,
    phrase_count: int,
) -> tuple[PhraseFamilySlot, ...]:
    """Return *phrase_count* family slots for the given section function.

    The template is truncated or padded (with alternating variant/development)
    so the caller always gets exactly *phrase_count* entries.
    """
    template = _PHRASE_FAMILY_TEMPLATES.get(function, (PhraseFamilySlot("seed", (), is_seed=True),))
    if phrase_count <= 0:
        return ()
    if phrase_count <= len(template):
        return template[:phrase_count]
    # Pad with alternating variant / development derived from the seed.
    padded = list(template)
    alternates = (
        PhraseFamilySlot("variant", ("reharmonize", "rotate")),
        PhraseFamilySlot("development", ("expand", "invert")),
    )
    while len(padded) < phrase_count:
        padded.append(alternates[len(padded) % len(alternates)])
    return tuple(padded)


_MIN_FUNCTION_COUNTS = {
    "micro": 2,
    "song": 3,
    "extended": 4,
    "suite": 5,
}


def minimum_function_count(form_class: str) -> int:
    return _MIN_FUNCTION_COUNTS.get(form_class, 3)


def _weights_for_sections(count: int, *, mode: str, form_class: str) -> list[float]:
    if form_class == "micro":
        return [1.0] * count
    if mode == "hook_led":
        base = [0.8, 1.0, 0.8, 1.15, 0.9, 1.1, 0.75]
    elif mode == "hybrid":
        base = [0.85, 0.95, 1.05, 1.1, 1.0, 0.95, 0.8, 0.7]
    else:
        base = [0.8, 0.95, 1.0, 1.1, 0.95, 1.05, 0.9, 0.8, 0.75]
    weights = list(base[:count])
    while len(weights) < count:
        weights.append(base[(len(weights) - len(base)) % len(base)] * 0.9)
    return weights


SectionSpec = tuple[str, SectionFunction, str | None, str, str]


_FORM_LIBRARY: dict[str, tuple[SectionSpec, ...]] = {
    "mini_refrain": (
        ("Emergence", "invocation", None, "light", "tonic"),
        ("Arrival", "arrival", None, "none", "dominant"),
        ("Afterglow", "afterglow", "Arrival", "moderate", "plagal"),
    ),
    "verse_chorus": (
        ("Emergence", "invocation", None, "light", "tonic"),
        ("Theme", "statement", None, "none", "tonic"),
        ("Verse", "verse", "Theme", "light", "tonic"),
        ("Arrival", "arrival", "Theme", "moderate", "dominant"),
        ("Development", "development", "Arrival", "light", "predominant"),
        ("Bridge", "turn", None, "strong", "borrowed"),
        ("Chorus", "chorus", "Arrival", "moderate", "authentic"),
        ("Recap", "recap", "Arrival", "moderate", "authentic"),
        ("Afterglow", "afterglow", "Theme", "light", "plagal"),
    ),
    "aaba": (
        ("Emergence", "invocation", None, "light", "tonic"),
        ("Theme", "statement", None, "none", "tonic"),
        ("First Return", "return", "Theme", "light", "authentic"),
        ("Arrival", "arrival", "Theme", "moderate", "dominant"),
        ("Development", "development", "Theme", "moderate", "predominant"),
        ("Bridge", "turn", None, "strong", "borrowed"),
        ("Recap", "recap", "Theme", "moderate", "authentic"),
        ("Afterglow", "afterglow", "Theme", "light", "plagal"),
    ),
    "build_drop": (
        ("Ignition", "invocation", None, "light", "tonic"),
        ("Theme", "statement", None, "none", "tonic"),
        ("Build I", "build", None, "light", "predominant"),
        ("Drop I", "drop", "Build I", "moderate", "dominant"),
        ("Development", "development", "Drop I", "moderate", "predominant"),
        ("Bridge", "turn", None, "strong", "borrowed"),
        ("Recap", "recap", "Drop I", "strong", "authentic"),
        ("Afterglow", "afterglow", "Recap", "light", "plagal"),
    ),
    "ambient_arc": (
        ("Emergence", "invocation", None, "light", "tonic"),
        ("Theme", "statement", None, "none", "tonic"),
        ("Drift Field", "ambient", "Theme", "light", "tonic"),
        ("Development", "development", "Drift Field", "moderate", "predominant"),
        ("Arrival", "arrival", "Drift Field", "moderate", "dominant"),
        ("Recap", "recap", "Theme", "moderate", "authentic"),
        ("Afterglow", "afterglow", "Arrival", "light", "plagal"),
    ),
    "rondo_return": (
        ("Theme", "statement", None, "none", "tonic"),
        ("First Return", "return", "Theme", "light", "authentic"),
        ("Episode", "episode", None, "moderate", "borrowed"),
        ("Development", "development", "Episode", "moderate", "predominant"),
        ("Second Return", "arrival", "Theme", "moderate", "dominant"),
        ("Bridge", "turn", None, "strong", "borrowed"),
        ("Recap", "recap", "Theme", "moderate", "authentic"),
        ("Coda", "coda", "Recap", "moderate", "authentic"),
        ("Afterglow", "afterglow", "Recap", "light", "plagal"),
    ),
    "bridge": (
        ("Emergence", "invocation", None, "light", "tonic"),
        ("Theme", "statement", None, "none", "tonic"),
        ("Arrival", "arrival", "Theme", "moderate", "dominant"),
        ("Lift", "lift", "Arrival", "light", "predominant"),
        ("Bridge", "bridge", None, "strong", "borrowed"),
        ("Development", "development", "Bridge", "moderate", "predominant"),
        ("Recap", "recap", "Arrival", "moderate", "authentic"),
        ("Afterglow", "afterglow", "Theme", "light", "plagal"),
    ),
    "afterglow": (
        ("Emergence", "invocation", None, "light", "tonic"),
        ("Theme", "statement", None, "none", "tonic"),
        ("Development", "development", "Theme", "moderate", "predominant"),
        ("Bridge", "turn", None, "strong", "borrowed"),
        ("Bridge Variant", "bridge", "Bridge", "strong", "borrowed"),
        ("Arrival", "arrival", "Theme", "moderate", "dominant"),
        ("Coda", "coda", "Arrival", "moderate", "authentic"),
        ("Recap", "recap", "Theme", "moderate", "authentic"),
        ("Afterglow", "afterglow", "Theme", "strong", "plagal"),
    ),
    "through_composed": (
        ("Emergence", "invocation", None, "light", "tonic"),
        ("Theme", "statement", None, "none", "tonic"),
        ("Thread I", "through_line", "Theme", "light", "tonic"),
        ("Development", "development", "Thread I", "moderate", "predominant"),
        ("Bridge", "turn", None, "strong", "borrowed"),
        ("Thread III", "through_line", None, "moderate", "dominant"),
        ("Arrival", "arrival", "Thread III", "moderate", "authentic"),
        ("Recap", "recap", "Theme", "moderate", "authentic"),
        ("Coda", "coda", "Arrival", "strong", "authentic"),
        ("Afterglow", "afterglow", "Thread I", "light", "plagal"),
    ),
}


_CANDIDATE_FAMILIES: dict[tuple[str, str], tuple[str, ...]] = {
    ("micro", "hook_led"): ("mini_refrain", "afterglow", "ambient_arc"),
    ("micro", "hybrid"): ("mini_refrain", "ambient_arc", "afterglow"),
    ("micro", "through_composed"): ("mini_refrain", "ambient_arc", "through_composed"),
    ("song", "hook_led"): ("verse_chorus", "aaba", "rondo_return"),
    ("song", "hybrid"): ("aaba", "rondo_return", "ambient_arc", "verse_chorus"),
    ("song", "through_composed"): ("through_composed", "ambient_arc", "rondo_return"),
    ("extended", "hook_led"): ("rondo_return", "build_drop", "verse_chorus"),
    ("extended", "hybrid"): ("rondo_return", "build_drop", "ambient_arc", "through_composed"),
    ("extended", "through_composed"): ("through_composed", "ambient_arc", "build_drop", "rondo_return"),
    ("suite", "hook_led"): ("rondo_return", "build_drop", "verse_chorus", "through_composed"),
    ("suite", "hybrid"): ("rondo_return", "through_composed", "build_drop", "ambient_arc"),
    ("suite", "through_composed"): ("through_composed", "rondo_return", "ambient_arc", "build_drop"),
}


def _stable_index(parts: Sequence[str], count: int) -> int:
    if count <= 1:
        return 0
    return sum((index + 1) * ord(char) for index, part in enumerate(parts) for char in part) % count


def _section_signature(sections: Sequence[SectionSpec]) -> tuple[str, ...]:
    return tuple(section[1] for section in sections)


def _recent_form_data(
    repertoire_entries: Sequence[Mapping[str, object]],
) -> tuple[list[tuple[str, ...]], list[str]]:
    signatures: list[tuple[str, ...]] = []
    form_families: list[str] = []
    for entry in list(repertoire_entries)[-8:]:
        summary = entry.get("score_tree_summary")
        source = summary if isinstance(summary, Mapping) else entry
        raw_functions = source.get("section_functions")
        if isinstance(raw_functions, Sequence) and not isinstance(raw_functions, str):
            functions = tuple(str(function) for function in raw_functions if function)
            if functions:
                signatures.append(functions)
        raw_family = source.get("form_family") or entry.get("form_family")
        if raw_family:
            form_families.append(str(raw_family))
    return signatures, form_families


def _family_matches_recent(candidate: str, recent_family: str) -> bool:
    return recent_family == candidate or recent_family.endswith(f"_{candidate}")


def _fatigue_score(
    *,
    form_family: str,
    sections: Sequence[SectionSpec],
    recent_signatures: Sequence[tuple[str, ...]],
    recent_families: Sequence[str],
) -> int:
    signature = _section_signature(sections)
    score = 0
    for age, recent_signature in enumerate(reversed(recent_signatures), start=1):
        weight = max(1, 9 - age)
        if signature == recent_signature:
            score += 8 * weight
        elif signature[:3] == recent_signature[:3]:
            score += 2 * weight
    for age, recent_family in enumerate(reversed(recent_families), start=1):
        if _family_matches_recent(form_family, recent_family):
            score += 6 * max(1, 9 - age)
    return score


def _candidate_family_names(
    *,
    form_class: str,
    mode: str,
    brief: PieceBrief,
    form_family_hint: str,
) -> tuple[str, ...]:
    if form_family_hint in _FORM_LIBRARY:
        return (form_family_hint,)
    if brief.through_composed_pressure >= 0.82:
        preferred = ("through_composed", "ambient_arc", "rondo_return")
        extras = _CANDIDATE_FAMILIES.get((form_class, mode), ())
        return tuple(dict.fromkeys(preferred + extras))
    return _CANDIDATE_FAMILIES.get((form_class, mode), _CANDIDATE_FAMILIES[("song", "hybrid")])


def _deform_sections_for_class(
    sections: Sequence[SectionSpec],
    *,
    form_class: str,
    ending_family: str,
) -> tuple[SectionSpec, ...]:
    selected = list(sections)
    if form_class == "micro" and len(selected) > 3:
        first = selected[0]
        core = next(
            (
                section
                for section in selected[1:]
                if section[1] in {"arrival", "drop", "return", "chorus", "afterglow"}
            ),
            selected[1],
        )
        glow = next((section for section in reversed(selected) if section[1] == "afterglow"), selected[-1])
        selected = [first, core, glow]
    elif form_class == "song" and len(selected) > 9:
        recap = next((section for section in selected if section[0] == "Recap"), selected[-2])
        glow = next((section for section in reversed(selected) if section[1] == "afterglow"), selected[-1])
        selected = selected[:6] + [section for section in (recap, glow) if section not in selected[:6]]
    elif form_class == "extended" and len(selected) < 7:
        selected = selected[:-1] + [
            ("Development", "development", selected[1][0], "moderate", "predominant"),
            ("Recap", "recap", selected[2][0], "moderate", "authentic"),
            selected[-1],
        ]
    elif form_class == "suite" and len(selected) < 8:
        selected = selected[:-1] + [
            ("Development", "development", selected[1][0], "moderate", "predominant"),
            ("Bridge", "bridge", None, "strong", "borrowed"),
            ("Recap", "recap", selected[2][0], "moderate", "authentic"),
            selected[-1],
        ]

    if ending_family == "afterglow" and selected[-1][1] != "afterglow":
        selected.append(("Afterglow", "afterglow", selected[-1][0], "light", "plagal"))
    return tuple(selected)


def _base_sections(
    form_class: str,
    mode: str,
    brief: PieceBrief,
    *,
    family: str,
    ending_family: str,
    repertoire_entries: Sequence[Mapping[str, object]],
    form_family_hint: str,
) -> tuple[str, tuple[SectionSpec, ...]]:
    candidates = _candidate_family_names(
        form_class=form_class,
        mode=mode,
        brief=brief,
        form_family_hint=form_family_hint,
    )
    offset = _stable_index(
        (family, form_class, mode, brief.narrative_scale, brief.motion_character, brief.ending_feeling),
        len(candidates),
    )
    ordered = candidates[offset:] + candidates[:offset]
    recent_signatures, recent_families = _recent_form_data(repertoire_entries)
    selected_family = min(
        ordered,
        key=lambda candidate: _fatigue_score(
            form_family=candidate,
            sections=_FORM_LIBRARY[candidate],
            recent_signatures=recent_signatures,
            recent_families=recent_families,
        ),
    )
    return selected_family, _deform_sections_for_class(
        _FORM_LIBRARY[selected_family],
        form_class=form_class,
        ending_family=ending_family,
    )


def plan_form(
    *,
    commission: PieceCommission,
    brief: PieceBrief,
    family: str,
    repertoire_entries: Sequence[Mapping[str, object]] = (),
    form_family_hint: str = "",
) -> FormPlan:
    form_family, raw_sections = _base_sections(
        commission.form_class,
        commission.composition_mode,
        brief,
        family=family,
        ending_family=commission.ending_family,
        repertoire_entries=repertoire_entries,
        form_family_hint=form_family_hint,
    )
    weights = _weights_for_sections(
        len(raw_sections),
        mode=commission.composition_mode,
        form_class=commission.form_class,
    )
    total_weight = sum(weights) or 1.0
    sections: list[PlannedSection] = []
    for (scene_name, function, return_from, transform_strength, harmonic_role), weight in zip(raw_sections, weights):
        sections.append(
            PlannedSection(
                scene_name=scene_name,
                function=function,
                target_duration_s=round((commission.duration_target_s * weight) / total_weight, 1),
                return_from=return_from,
                transform_strength=transform_strength,
                harmonic_role=harmonic_role,
            )
        )
    return FormPlan(
        form_family=form_family if family == "default" else f"{family}_{form_family}",
        form_class=commission.form_class,
        composition_mode=commission.composition_mode,
        sections=tuple(sections),
        ending_family=commission.ending_family,
    )
