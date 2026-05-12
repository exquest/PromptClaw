"""Quality gate for score-tree composition."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev
from typing import Mapping

from cypherclaw.render.events import IntentTag

from .form_grammar import minimum_function_count
from .score_tree import ScoreTree, SectionNode

INTENT_TAG_VALUES: frozenset[str] = frozenset(tag.value for tag in IntentTag)


@dataclass(frozen=True)
class GateReport:
    approved: bool
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    metrics: Mapping[str, float]


_TRANSFORM_STRENGTH = {
    "none": 0.0,
    "light": 0.35,
    "moderate": 0.7,
    "strong": 1.0,
}

_FUNCTION_ENERGY = {
    "invocation": 0.2,
    "statement": 0.45,
    "arrival": 0.75,
    "lift": 0.72,
    "turn": 0.58,
    "contrast": 0.62,
    "bridge": 0.62,
    "recap": 0.86,
    "release": 0.82,
    "resolution": 0.78,
    "residue": 0.24,
    "coda": 0.28,
}

_HARMONIC_ENERGY = {
    "tonic": 0.2,
    "predominant": 0.52,
    "dominant": 0.72,
    "borrowed": 0.68,
    "authentic": 0.82,
    "plagal": 0.34,
}

_GROOVE_ENERGY = {
    "drone": 0.08,
    "static": 0.1,
    "sustain": 0.12,
    "pad": 0.16,
    "pulse": 0.48,
    "lift": 0.72,
    "drive": 0.82,
}

_PAYOFF_TERMS = (
    "arrival",
    "answer",
    "afterglow",
    "closure",
    "final",
    "landing",
    "payoff",
    "release",
    "resolution",
    "resolve",
    "return",
)

_DRONE_GROOVES = {"drone", "static", "sustain", "pad"}
_STATIC_CADENCES = {"none", "static", "suspended"}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _is_micro(tree: ScoreTree) -> bool:
    return tree.commission.form_class == "micro" or tree.form.form_class == "micro"


def _section_duration(section: SectionNode) -> float:
    return max(0.0, float(section.target_duration_s or 0.0))


def _section_durations(tree: ScoreTree) -> list[float]:
    return [_section_duration(section) for section in tree.sections]


def _planned_duration(tree: ScoreTree, section_durations: list[float]) -> float:
    planned_duration = float(tree.planned_duration_s or 0.0)
    if planned_duration > 0.0:
        return planned_duration
    return sum(section_durations)


def _duration_fit(tree: ScoreTree, planned_duration_s: float) -> float:
    target_duration_s = float(tree.commission.duration_target_s or 0.0)
    if target_duration_s <= 0.0 or planned_duration_s <= 0.0:
        return 0.0
    return _clamp(1.0 - abs(planned_duration_s - target_duration_s) / target_duration_s)


def _duration_balance(section_durations: list[float]) -> float:
    positive_durations = [duration for duration in section_durations if duration > 0.0]
    if len(positive_durations) < 2:
        return 0.0
    mean_duration = sum(positive_durations) / len(positive_durations)
    if mean_duration <= 0.0:
        return 0.0
    coefficient_of_variation = pstdev(positive_durations) / mean_duration
    return _clamp(1.0 - coefficient_of_variation)


def _recurrence_score(tree: ScoreTree) -> float:
    if len(tree.sections) < 2:
        return 0.0
    recurring_sections = sum(1 for section in tree.sections if section.return_from)
    return _clamp(recurring_sections / max(1, len(tree.sections) - 1))


def _transformation_score(tree: ScoreTree) -> float:
    if not tree.sections:
        return 0.0
    section_motion = sum(
        _TRANSFORM_STRENGTH.get(section.transform_strength, 0.0)
        for section in tree.sections
    ) / len(tree.sections)
    phrases = [phrase for section in tree.sections for phrase in section.phrases]
    phrase_motion = 0.0
    if phrases:
        phrase_motion = sum(1 for phrase in phrases if phrase.transform_ops) / len(phrases)
    return _clamp((section_motion * 0.7) + (phrase_motion * 0.3))


def _arrangement_contrast_score(tree: ScoreTree) -> float:
    if len(tree.sections) < 2:
        return 0.0
    harmonic_roles = {section.harmonic_role for section in tree.sections}
    cadences = {section.cadence_type for section in tree.sections}
    grooves = {section.groove_state for section in tree.sections}
    combinations = {
        (section.harmonic_role, section.cadence_type, section.groove_state)
        for section in tree.sections
    }
    role_score = len(harmonic_roles) / min(len(tree.sections), 4)
    cadence_score = len(cadences) / min(len(tree.sections), 4)
    groove_score = len(grooves) / min(len(tree.sections), 3)
    combination_score = len(combinations) / min(len(tree.sections), 4)
    return _clamp(
        (combination_score * 0.5)
        + (role_score * 0.2)
        + (cadence_score * 0.2)
        + (groove_score * 0.1)
    )


def _section_energy(section: SectionNode) -> float:
    function_energy = _FUNCTION_ENERGY.get(section.function, 0.48)
    harmonic_energy = _HARMONIC_ENERGY.get(section.harmonic_role, 0.45)
    groove_energy = _GROOVE_ENERGY.get(section.groove_state, 0.45)
    transform_energy = _TRANSFORM_STRENGTH.get(section.transform_strength, 0.0)
    return _clamp(
        (function_energy * 0.55)
        + (harmonic_energy * 0.2)
        + (groove_energy * 0.15)
        + (transform_energy * 0.1)
    )


def _energy_curve_score(tree: ScoreTree) -> float:
    if len(tree.sections) < 2:
        return 0.0
    energies = [_section_energy(section) for section in tree.sections]
    energy_range = max(energies) - min(energies)
    peak_index = energies.index(max(energies))
    peak_position = peak_index / max(1, len(energies) - 1)
    peak_score = _clamp(1.0 - abs(peak_position - 0.72) / 0.72)
    release_score = 0.0
    if len(energies) > 2:
        release_score = _clamp(energies[-2] - energies[-1])
    else:
        release_score = _clamp(energies[-1] - energies[0])
    return _clamp((energy_range * 1.25 * 0.55) + (peak_score * 0.25) + (release_score * 0.2))


def _motif_clarity_score(tree: ScoreTree) -> float:
    phrases = [phrase for section in tree.sections for phrase in section.phrases]
    if not phrases:
        return 0.0
    phrase_ref_count = sum(1 for phrase in phrases if phrase.motif_refs)
    motif_counts: dict[str, int] = {}
    for phrase in phrases:
        for motif_ref in phrase.motif_refs:
            motif_counts[motif_ref] = motif_counts.get(motif_ref, 0) + 1
    if not motif_counts:
        return 0.0
    coverage_score = phrase_ref_count / len(phrases)
    dominant_motif_score = max(motif_counts.values()) / sum(motif_counts.values())
    hook_score = 1.0 if tree.primary_hook_text else 0.0
    return _clamp((coverage_score + dominant_motif_score + hook_score) / 3.0)


def _narrative_payoff_score(tree: ScoreTree) -> float:
    if not tree.narrative_map:
        return 0.0
    narrative_text = " ".join(str(value).lower() for value in tree.narrative_map.values())
    matching_terms = sum(1 for term in _PAYOFF_TERMS if term in narrative_text)
    return _clamp(matching_terms / 2.0)


def _is_drone_like_long_section(section: SectionNode, planned_duration_s: float) -> bool:
    duration_s = _section_duration(section)
    long_section_threshold = max(45.0, min(72.0, planned_duration_s * 0.3))
    if duration_s < long_section_threshold:
        return False

    phrase_transform_count = sum(1 for phrase in section.phrases if phrase.transform_ops)
    motif_refs = {
        motif_ref
        for phrase in section.phrases
        for motif_ref in phrase.motif_refs
    }
    phrase_functions = {phrase.function for phrase in section.phrases}
    low_motion_surface = (
        section.groove_state in _DRONE_GROOVES
        or (
            section.transform_strength == "none"
            and section.cadence_type in _STATIC_CADENCES
        )
    )
    return (
        low_motion_surface
        and phrase_transform_count == 0
        and len(motif_refs) <= 1
        and len(phrase_functions) <= 1
    )


def evaluate_score_tree(tree: ScoreTree) -> GateReport:
    failures: list[str] = []
    warnings: list[str] = []

    section_count = len(tree.sections)
    transform_count = sum(
        1
        for section in tree.sections
        if section.transform_strength != "none"
    )
    recurring_sections = sum(1 for section in tree.sections if section.return_from)
    section_durations = _section_durations(tree)
    duration_s = _planned_duration(tree, section_durations)
    micro_piece = _is_micro(tree)

    duration_fit = _duration_fit(tree, duration_s)
    duration_balance = _duration_balance(section_durations)
    recurrence = _recurrence_score(tree)
    transformation = _transformation_score(tree)
    arrangement_contrast = _arrangement_contrast_score(tree)
    energy_curve = _energy_curve_score(tree)
    motif_clarity = _motif_clarity_score(tree)
    narrative_payoff = _narrative_payoff_score(tree)

    if section_count < minimum_function_count(tree.form.form_class):
        failures.append("too few section functions for form class")
    if duration_fit < 0.55 and not micro_piece:
        failures.append("planned duration is below minimum structural threshold")
    if duration_balance < 0.5 and section_count > 1:
        failures.append("section durations are unbalanced")
    if not tree.ending_family:
        failures.append("missing ending family")
    if not tree.primary_hook_text and tree.commission.composition_mode != "through_composed":
        failures.append("missing primary hook text")
    if recurring_sections <= 0 and not micro_piece:
        failures.append("piece has no structural recurrence")
    if transform_count <= 0 and transformation <= 0.0 and not micro_piece:
        failures.append("piece has no transformed return or development")
    if arrangement_contrast < 0.45:
        failures.append("arrangement lacks contrast")
    if narrative_payoff <= 0.0:
        failures.append("piece has no narrative payoff")
    if any(_is_drone_like_long_section(section, duration_s) for section in tree.sections):
        failures.append("section is drone-like for too long")
    if len(tree.narrative_map) < max(2, section_count - 1):
        warnings.append("narrative map is sparse")
    if tree.commission.form_class in {"extended", "suite"} and section_count < 5:
        failures.append("long-form piece is structurally underwritten")

    is_long = tree.commission.form_class in {"extended", "suite"}
    for section in tree.sections:
        course = section.production_course
        intent = course.get("intent", "")
        valid_sparse = micro_piece and intent == "sparse"

        if not valid_sparse:
            if not course.get("mode_scale") or not course.get("harmonic_function"):
                failures.append("missing harmonic metadata")
            if not course.get("meter_groove"):
                failures.append("missing rhythm metadata")
            if not course.get("mix_role"):
                failures.append("missing mix role")
            if not course.get("transition_type"):
                failures.append("missing transition continuity")

            density = course.get("density")
            phase = course.get("phase_profile")
            if density in ("dense", "high") and phase in ("sleep", "wind_down"):
                failures.append("phase-inappropriate density")
            
            register = course.get("register")
            if register == "unsafe":
                failures.append("unsafe register")
            
            dynamics = course.get("dynamics")
            if dynamics == "flat":
                failures.append("flat dynamics")

        if is_long and not course.get("genre_strategy"):
            failures.append("untagged genre/strategy choices for long pieces")

        for phrase in section.phrases:
            tag = phrase.intent_tag or (IntentTag.PUNCTUATE.value if micro_piece else "")
            if not tag:
                failures.append("phrase missing intent_tag")
                break
            if tag not in INTENT_TAG_VALUES:
                failures.append("phrase has invalid intent_tag")
                break

    metrics = {
        "section_count": float(section_count),
        "duration_s": duration_s,
        "transform_count": float(transform_count),
        "recurring_sections": float(recurring_sections),
        "duration_fit": duration_fit,
        "duration_balance": duration_balance,
        "recurrence": recurrence,
        "transformation": transformation,
        "arrangement_contrast": arrangement_contrast,
        "energy_curve": energy_curve,
        "motif_clarity": motif_clarity,
        "narrative_payoff": narrative_payoff,
    }
    return GateReport(
        approved=not failures,
        failures=tuple(failures),
        warnings=tuple(warnings),
        metrics=metrics,
    )
