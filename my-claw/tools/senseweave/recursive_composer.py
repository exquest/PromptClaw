"""Recursive score-tree composition above the tracker runtime."""
from __future__ import annotations

import hashlib
import json
from typing import Mapping

from .form_grammar import FormPlan, PlannedSection, phrase_family_slots
from .hook_engine import build_hook_profile
from .piece_brief import PieceBrief
from .piece_commission import PieceCommission
from .procedural_arc import ArcDirective, directive_for_elapsed
from .production_course import course_for_section
from .score_tree import (
    MotifNode,
    PerformanceIntent,
    PhraseNode,
    ScoreTree,
    SectionNode,
)
from cypherclaw.render.narrative_envelope import beat_from_directive, envelope_for_beat


_INTENT_BY_FUNCTION: dict[str, str] = {
    "invocation": "build",
    "statement": "build",
    "arrival": "build",
    "lift": "build",
    "development": "build",
    "turn": "question",
    "contrast": "question",
    "bridge": "settle",
    "release": "settle",
    "residue": "settle",
    "recap": "answer",
    "resolution": "answer",
    "coda": "punctuate",
}

_CADENCE_BY_ROLE = {
    "tonic": "suspended",
    "predominant": "half",
    "dominant": "authentic",
    "borrowed": "deceptive",
    "plagal": "plagal",
    "authentic": "authentic",
}


def _arc_metadata(directive: ArcDirective) -> dict[str, str]:
    return {
        "arc_phase": directive.phase.name,
        "arc_density": str(directive.density_target),
        "arc_dynamic": directive.dynamic_target,
        "arc_harmonic": directive.harmonic_target,
        "arc_rhythm": directive.rhythm_target,
        "arc_timbre": directive.timbre_target,
        "arc_spatial": directive.spatial_target,
        "arc_compression": str(directive.compression_target),
        "arc_senseweave": str(directive.senseweave_target),
        "arc_synthesis": directive.synthesis_target,
    }


def _production_arc_for_sections(
    sections: tuple[PlannedSection, ...],
    *,
    commission: PieceCommission,
    cadence_state: str,
) -> tuple[dict[str, dict[str, str]], dict[str, ArcDirective]]:
    total_duration_s = max(1.0, sum(section.target_duration_s for section in sections))
    cycle_minutes = max(0.001, float(commission.arc_cycle_minutes or 30.0))
    cursor_s = 0.0
    production_arc: dict[str, dict[str, str]] = {}
    directives: dict[str, ArcDirective] = {}
    for section in sections:
        midpoint = (cursor_s + section.target_duration_s * 0.5) / total_duration_s
        elapsed_minutes = float(commission.arc_elapsed_minutes or 0.0) + midpoint * cycle_minutes
        directive = directive_for_elapsed(
            elapsed_minutes,
            cadence_state=cadence_state,
            cycle_minutes=cycle_minutes,
        )
        production_arc[section.scene_name] = _arc_metadata(directive)
        directives[section.scene_name] = directive
        cursor_s += section.target_duration_s
    return production_arc, directives


def _seed_id(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _scoped_seed_id(composition_seed: str | None, *parts: object) -> str:
    if composition_seed is None:
        return _seed_id(*parts)
    return _seed_id(composition_seed, *parts)


def _section_phrase_count(section: PlannedSection, *, commission: PieceCommission) -> int:
    if commission.form_class == "micro":
        return 1
    if section.function in {"development", "turn"} and commission.form_class in {"extended", "suite"}:
        return 3
    if section.function in {"arrival", "recap", "coda"}:
        return 2
    return 2 if commission.form_class in {"song", "extended", "suite"} else 1


def compose_score_tree(
    *,
    commission: PieceCommission,
    brief: PieceBrief,
    form: FormPlan,
    family: str,
    cadence_state: str,
    progression_profile: str,
    song_num: int,
    mood: Mapping[str, float],
    composition_seed: str | int | None = None,
    repertoire_hint: Mapping[str, object] | None = None,
) -> ScoreTree:
    normalized_seed = str(composition_seed) if composition_seed is not None else None
    hook = build_hook_profile(
        family=family,
        progression_profile=progression_profile,
        cadence_state=cadence_state,
        song_num=song_num or 1,
        mood=mood,
        repertoire_hint=repertoire_hint,
    )
    primary_motif = MotifNode(
        motif_id=_scoped_seed_id(normalized_seed, hook.title, "primary"),
        hook_class=hook.hook_class,
        contour=hook.contour,
        rhythm=hook.rhythm,
        timbral_tags=hook.timbral_tags,
        anchor_degrees=hook.anchor_degrees,
        answer_degrees=hook.answer_degrees,
        text_hook=hook.text_hook,
        lifecycle_state="statement",
    )
    contrast_motifs: list[MotifNode] = []
    if commission.composition_mode != "hook_led" or commission.form_class in {"extended", "suite"}:
        contrast_motifs.append(
            MotifNode(
                motif_id=_scoped_seed_id(normalized_seed, hook.title, "contrast"),
                hook_class=hook.hook_class,
                contour=tuple(reversed(primary_motif.contour)),
                rhythm=tuple(reversed(primary_motif.rhythm)),
                timbral_tags=hook.timbral_tags,
                anchor_degrees=hook.answer_degrees or hook.anchor_degrees,
                answer_degrees=hook.anchor_degrees,
                text_hook=hook.text_hook,
                lifecycle_state="contrast",
            )
        )

    sections: list[SectionNode] = []
    section_functions: dict[str, str] = {}
    section_cadences: dict[str, str] = {}
    narrative_map: dict[str, str] = {}
    production_arc, section_directives = _production_arc_for_sections(
        form.sections,
        commission=commission,
        cadence_state=cadence_state,
    )
    for index, section in enumerate(form.sections):
        motif_refs = [primary_motif.motif_id]
        if contrast_motifs and section.function in {"development", "turn", "coda"}:
            motif_refs.append(contrast_motifs[0].motif_id)
        phrase_count = _section_phrase_count(section, commission=commission)
        slots = phrase_family_slots(section.function, phrase_count)
        # Section-level harmonic ops that apply on top of family-specific ops.
        section_ops: list[str] = [
            op
            for op in (
                "reharmonize" if section.harmonic_role in {"borrowed", "authentic"} else "",
                "answer" if section.scene_name in {"Recap", "Release", "Resolution", "Afterglow"} else "",
            )
            if op
        ]
        seed_phrase_id: str | None = None
        phrases: list[PhraseNode] = []
        for phrase_index, slot in enumerate(slots):
            pid = _scoped_seed_id(normalized_seed, section.scene_name, index, phrase_index)
            if slot.is_seed:
                seed_phrase_id = pid
            # Merge family transform ops with section-level ops, deduplicating.
            merged_ops = tuple(dict.fromkeys((*slot.transform_ops, *section_ops)))
            intent_tag = _INTENT_BY_FUNCTION.get(section.function, "build")
            phrases.append(
                PhraseNode(
                    phrase_id=pid,
                    function=section.function,
                    motif_refs=tuple(motif_refs),
                    target_duration_s=round(section.target_duration_s / phrase_count, 2),
                    transform_ops=merged_ops,
                    phrase_family=slot.family,
                    seed_phrase_id=None if slot.is_seed else seed_phrase_id,
                    intent_tag=intent_tag,
                    performance_intent=PerformanceIntent(phrase_id=pid),
                ),
            )
        cadence_type = _CADENCE_BY_ROLE.get(section.harmonic_role, "authentic")
        section_functions[section.scene_name] = section.function
        section_cadences[section.scene_name] = cadence_type
        beat_index = min(index, len(brief.section_beats) - 1)
        if beat_index >= 0:
            narrative_map[section.scene_name] = brief.section_beats[beat_index]
        next_section = form.sections[index + 1] if index < len(form.sections) - 1 else None
        course = course_for_section(
            function=section.function,
            harmonic_role=section.harmonic_role,
            arc_metadata=production_arc.get(section.scene_name, {}),
            groove_identity=commission.groove_identity,
            next_function=next_section.function if next_section is not None else None,
            next_harmonic_role=(
                next_section.harmonic_role if next_section is not None else None
            ),
        )
        section_id = _scoped_seed_id(normalized_seed, "section", section.scene_name, index)
        sections.append(
            SectionNode(
                section_id=section_id,
                scene_name=section.scene_name,
                function=section.function,
                target_duration_s=section.target_duration_s,
                phrases=phrases,
                harmonic_role=section.harmonic_role,
                cadence_type=cadence_type,
                groove_state=commission.groove_identity,
                return_from=section.return_from,
                transform_strength=section.transform_strength,
                production_course=course,
                section_envelope=envelope_for_beat(
                    beat_from_directive(
                        section_directives.get(section.scene_name, commission.arc_directive),
                        section.function,
                    )
                ),
            )
        )

    planned_duration_s = round(sum(section.target_duration_s for section in sections), 2)
    metadata = {
        "family": family,
        "cadence_state": cadence_state,
        "progression_profile": progression_profile,
        "hook_class": hook.hook_class,
        "text_hook": hook.text_hook,
        "song_num": str(song_num),
    }
    if normalized_seed is not None:
        metadata["composition_seed"] = normalized_seed
    if commission.arc_directive:
        metadata.update(_arc_metadata(commission.arc_directive))
    if production_arc:
        metadata["arc_phase_contour"] = json.dumps(
            [production_arc[section.scene_name]["arc_phase"] for section in sections]
        )

    return ScoreTree(
        piece_id=_scoped_seed_id(
            normalized_seed,
            family,
            cadence_state,
            progression_profile,
            song_num,
            hook.title,
        ),
        title=hook.title,
        commission=commission,
        brief=brief,
        form=form,
        motifs=[primary_motif, *contrast_motifs],
        sections=sections,
        harmonic_plan={
            "progression_profile": progression_profile,
            "section_functions": section_functions,
            "section_cadences": section_cadences,
        },
        arrangement_plan={
            "groove_identity": commission.groove_identity,
            "sonic_world_count": commission.sonic_world_count,
            "production_arc": production_arc,
        },
        ending_family=commission.ending_family,
        narrative_map=narrative_map,
        metadata=metadata,
        planned_duration_s=planned_duration_s,
        primary_hook_text=hook.text_hook,
    )
