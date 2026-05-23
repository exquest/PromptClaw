"""Compile approved score trees into tracker songs."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping, Sequence

from cypherclaw.composer_vocabulary_bridge import (
    VOCABULARY_METADATA_KEYS,
    citation_metadata_from_payload,
)
from cypherclaw.render.features import feature_metadata_for_phrase

from .generative_scores import (
    Note,
    Phrase,
    Score,
    _apply_hook_degrees,
    _shape_patch_ending,
    _shift_dynamic,
)
from .mix_engine import build_spatial_profile
from .music_tracker import (
    SceneTemplate,
    _resolve_counterpoint_rule_id,
    build_korsakov_tracker_song,
    enrich_score_for_tracker,
)
from .self_critique import revise_score
from .score_tree import PRODUCTION_COURSE_KEYS, MotifNode, ScoreTree, SectionNode


@dataclass(frozen=True)
class CompiledTrackerPiece:
    score_tree: ScoreTree
    source_score: Score
    tracker_song: object
    estimated_duration_s: float


_SECTION_DEFAULTS = {
    "Emergence": {"allowed_roles": ("bass", "melody", "color"), "tempo_multiplier": 0.9, "max_polyphony": 3, "automation": {"density": 0.24, "master_amp": 0.5, "reverb_send": 0.18, "stereo_width": 0.8, "depth": 0.7, "delay_send": 0.0}},
    "Theme": {"allowed_roles": ("bass", "melody", "color"), "tempo_multiplier": 1.0, "max_polyphony": 3, "automation": {"density": 0.4, "master_amp": 0.62, "reverb_send": 0.14, "stereo_width": 0.6, "depth": 0.5, "delay_send": 0.08}},
    "Lift": {"allowed_roles": ("bass", "melody", "counter"), "tempo_multiplier": 1.04, "max_polyphony": 3, "automation": {"density": 0.52, "master_amp": 0.66, "reverb_send": 0.12, "stereo_width": 0.55, "depth": 0.45, "delay_send": 0.1}},
    "Arrival": {"allowed_roles": ("bass", "melody", "counter", "color"), "tempo_multiplier": 1.08, "max_polyphony": 4, "automation": {"density": 0.72, "master_amp": 0.72, "reverb_send": 0.1, "stereo_width": 0.45, "depth": 0.35, "delay_send": 0.1}},
    "Development": {"allowed_roles": ("bass", "melody", "counter", "color"), "tempo_multiplier": 1.02, "max_polyphony": 5, "automation": {"density": 0.82, "master_amp": 0.74, "reverb_send": 0.16, "stereo_width": 0.45, "depth": 0.35, "delay_send": 0.1}},
    "Bridge": {"allowed_roles": ("melody", "counter", "color"), "tempo_multiplier": 0.96, "max_polyphony": 3, "automation": {"density": 0.48, "master_amp": 0.58, "reverb_send": 0.18, "stereo_width": 0.55, "depth": 0.5, "delay_send": 0.08}},
    "Recap": {"allowed_roles": ("bass", "melody", "counter", "color"), "tempo_multiplier": 0.98, "max_polyphony": 3, "automation": {"density": 0.44, "master_amp": 0.6, "reverb_send": 0.15, "stereo_width": 0.55, "depth": 0.45, "delay_send": 0.08}},
    "Release": {"allowed_roles": ("melody", "color"), "tempo_multiplier": 0.9, "max_polyphony": 2, "automation": {"density": 0.28, "master_amp": 0.48, "reverb_send": 0.16, "stereo_width": 0.65, "depth": 0.6, "delay_send": 0.12}},
    "Resolution": {"allowed_roles": ("melody", "color"), "tempo_multiplier": 0.84, "max_polyphony": 2, "automation": {"density": 0.18, "master_amp": 0.42, "reverb_send": 0.14, "stereo_width": 0.75, "depth": 0.7, "delay_send": 0.15}},
    "Afterglow": {"allowed_roles": ("melody", "color"), "tempo_multiplier": 0.8, "max_polyphony": 1, "automation": {"density": 0.1, "master_amp": 0.36, "reverb_send": 0.2, "stereo_width": 0.8, "depth": 0.75, "delay_send": 0.18}},
}

_SECTION_FUNCTION_ROOT_DEGREES = {
    "invocation": 1,
    "statement": 1,
    "lift": 4,
    "arrival": 5,
    "refrain": 1,
    "development": 5,
    "turn": 6,
    "instrumental_response": 4,
    "recap": 1,
    "coda": 1,
    "residue": 1,
}

_HARMONIC_ROLE_ROOT_DEGREES = {
    "tonic": 1,
    "predominant": 4,
    "dominant": 5,
    "borrowed": 6,
    "plagal": 4,
    "authentic": 1,
}

_SECTION_FUNCTION_PROGRESSIONS = {
    "invocation": (1, 1, 5, 1),
    "statement": (1, 4, 5, 1),
    "lift": (4, 2, 5, 1),
    "arrival": (5, 6, 4, 5),
    "refrain": (1, 5, 6, 4),
    "development": (4, 5, 6, 5),
    "turn": (6, 4, 7, 5),
    "instrumental_response": (4, 6, 2, 5),
    "recap": (1, 4, 5, 1),
    "coda": (1, 5, 4, 1),
    "residue": (1, 4, 1, 1),
}

_HARMONIC_ROLE_PROGRESSIONS = {
    "tonic": (1, 4, 5, 1),
    "predominant": (4, 2, 5, 5),
    "dominant": (5, 6, 4, 5),
    "borrowed": (6, 4, 7, 5),
    "plagal": (4, 1, 4, 1),
    "authentic": (1, 4, 5, 1),
}

_MOTIF_DEVELOPMENT_BY_FUNCTION = {
    "invocation": "seed",
    "statement": "statement",
    "lift": "sequence",
    "arrival": "arrival",
    "refrain": "refrain",
    "development": "sequence_fragment",
    "turn": "contrast_inversion",
    "instrumental_response": "response",
    "recap": "recall_answer",
    "coda": "liquidation",
    "residue": "residue",
}

_RHYTHM_DEVELOPMENT_BY_FUNCTION = {
    "invocation": "sparse_breath",
    "statement": "steady_statement",
    "lift": "forward_push",
    "arrival": "arrival_drive",
    "refrain": "refrain_pulse",
    "development": "syncopated_fragment",
    "turn": "half_time_displacement",
    "instrumental_response": "call_response",
    "recap": "recall_groove",
    "coda": "liquidation_slowdown",
    "residue": "residue_breath",
}

_RHYTHM_DURATION_CELLS = {
    "sparse_breath": (1.5, 1.0, 1.5, 2.0),
    "steady_statement": (1.0, 1.0, 1.0, 1.0),
    "forward_push": (0.75, 0.75, 1.0, 1.5),
    "arrival_drive": (0.5, 0.5, 1.0, 1.0),
    "refrain_pulse": (1.0, 0.5, 0.5, 1.0),
    "syncopated_fragment": (0.5, 1.0, 0.5, 1.5, 0.5),
    "half_time_displacement": (1.5, 0.5, 2.0, 1.0),
    "call_response": (0.75, 1.25, 0.75, 1.25),
    "recall_groove": (1.0, 0.5, 1.0, 1.5),
    "liquidation_slowdown": (1.5, 1.5, 2.0),
    "residue_breath": (2.0, 1.5, 2.5),
}

_SUPPORTED_TRANSITION_TECHNIQUES = (
    "pivot_event",
    "breath_silence",
    "metric_modulation",
    "timbral_morph",
    "harmonic_pivot_chord",
    "common_tone_bridge",
)

_PIVOT_EVENT_FUNCTIONS = {"arrival", "refrain", "recap"}
_BREATH_SILENCE_FUNCTIONS = {"invocation", "turn", "coda", "residue"}

_SAMPLE_GESTURE_DEFAULTS_BY_FUNCTION = {
    "development": {
        "mode": "grain_cloud",
        "voice": "sample_grain",
        "transforms": ("slice_rearrange", "granular_cloud", "reverse_accents", "pitch_window"),
        "density": 0.42,
        "max_events": 8,
    },
    "recap": {
        "mode": "window_echo",
        "voice": "sample_window",
        "transforms": ("slice_rearrange", "stretch", "pitch_window"),
        "density": 0.28,
        "max_events": 4,
    },
    "residue": {
        "mode": "freeze_bed",
        "voice": "sample_freeze",
        "transforms": ("stretch", "spectral_freeze"),
        "density": 0.18,
        "max_events": 3,
    },
}

_ARC_METADATA_KEYS = (
    "arc_phase",
    "arc_density",
    "arc_dynamic",
    "arc_harmonic",
    "arc_rhythm",
    "arc_timbre",
    "arc_spatial",
    "arc_compression",
    "arc_senseweave",
    "arc_synthesis",
)

_DYNAMIC_MASTER_AMP = {
    "pp": 0.38,
    "p": 0.48,
    "mp": 0.56,
    "mf": 0.66,
    "f": 0.76,
}


def _base_scene_duration_s(score: Score) -> float:
    max_beats = max(
        (sum(note.duration_beats for note in phrase.notes) for phrase in score.phrases),
        default=4.0,
    )
    return (max_beats * 60.0) / max(score.tempo_bpm, 1.0)


def _repeat_plan_for_ratio(ratio: float) -> tuple[int, float]:
    """Split a long section ratio into phrase repeats plus modest note scaling."""

    bounded = max(0.75, float(ratio))
    if bounded <= 1.35:
        return 1, round(bounded, 3)

    repeat_count = max(2, int(round(bounded)))
    note_scale = bounded / repeat_count

    while note_scale > 1.35:
        repeat_count += 1
        note_scale = bounded / repeat_count
    while repeat_count > 1 and note_scale < 0.75:
        repeat_count -= 1
        note_scale = bounded / repeat_count

    return repeat_count, round(max(0.75, min(note_scale, 1.35)), 3)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _float_metadata(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _shift_degree(degree: int, delta: int) -> int:
    shifted = degree + delta
    while shifted < 1:
        shifted += 7
    while shifted > 8:
        shifted -= 7
    return shifted


def _replace_phrase(
    phrase: Phrase,
    *,
    notes: list[Note] | None = None,
    dynamic: str | None = None,
    metadata: Mapping[str, str] | None = None,
) -> Phrase:
    return Phrase(
        notes=list(phrase.notes) if notes is None else notes,
        voice=phrase.voice,
        dynamic=phrase.dynamic if dynamic is None else dynamic,
        role=phrase.role,
        metadata=dict(phrase.metadata if metadata is None else metadata),
    )


def _scale_phrase_durations(phrase: Phrase, factor: float) -> Phrase:
    return _replace_phrase(
        phrase,
        notes=[
            Note(
                scale_degree=note.scale_degree,
                duration_beats=round(max(0.25, note.duration_beats * factor), 2),
                accent=note.accent,
            )
            for note in phrase.notes
        ],
    )


def _with_render_features(phrase: Phrase, *, key: str) -> Phrase:
    if not phrase.notes:
        return phrase
    metadata = dict(phrase.metadata)
    metadata.update(feature_metadata_for_phrase(phrase.notes, key=key))
    return _replace_phrase(phrase, metadata=metadata)


def _vocabulary_citation_for_section(
    score_tree: ScoreTree,
    section: SectionNode,
) -> Mapping[str, object]:
    citations = score_tree.arrangement_plan.get("vocabulary_fragments", {})
    if not isinstance(citations, Mapping):
        return {}
    citation = citations.get(section.scene_name)
    if not isinstance(citation, Mapping):
        return {}
    return citation


def _payload_sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return ()
        value = parsed
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


def _payload_int_sequence(value: object) -> tuple[int, ...]:
    result: list[int] = []
    for item in _payload_sequence(value):
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return tuple(result)


def _payload_float_sequence(value: object) -> tuple[float, ...]:
    result: list[float] = []
    for item in _payload_sequence(value):
        try:
            result.append(float(item))
        except (TypeError, ValueError):
            continue
    return tuple(result)


def _apply_vocabulary_citation(
    phrase: Phrase,
    citation: Mapping[str, object],
) -> Phrase:
    if not citation or phrase.role not in {"melody", "counter"}:
        return phrase
    degrees = _payload_int_sequence(citation.get("degree_pattern"))
    durations = _payload_float_sequence(citation.get("duration_pattern"))
    if not degrees and not durations:
        return phrase

    notes: list[Note] = []
    for index, note in enumerate(phrase.notes):
        degree = note.scale_degree
        duration = note.duration_beats
        if index < len(degrees):
            degree = int(_clamp(float(degrees[index]), 1.0, 8.0))
        if index < len(durations):
            duration = round(_clamp(float(durations[index]), 0.25, 4.0), 2)
        notes.append(
            Note(
                scale_degree=degree,
                duration_beats=duration,
                accent=note.accent or index == 0,
            )
        )

    metadata = dict(phrase.metadata)
    metadata.update(citation_metadata_from_payload(citation))
    return _replace_phrase(phrase, notes=notes, metadata=metadata)


def _thin_phrase(phrase: Phrase, keep_every: int) -> Phrase:
    if keep_every <= 1 or len(phrase.notes) <= 2:
        return phrase
    kept = [note for index, note in enumerate(phrase.notes) if index % keep_every == 0 or index == len(phrase.notes) - 1]
    if not kept:
        kept = phrase.notes[:1]
    return _replace_phrase(phrase, notes=kept)


def _rotate_phrase(phrase: Phrase, steps: int) -> Phrase:
    if not phrase.notes:
        return phrase
    rotation = steps % len(phrase.notes)
    notes = phrase.notes[rotation:] + phrase.notes[:rotation]
    return _replace_phrase(phrase, notes=notes)


def _accent_phrase(phrase: Phrase, every: int) -> Phrase:
    if every <= 1:
        return _replace_phrase(
            phrase,
            notes=[Note(note.scale_degree, note.duration_beats, True) for note in phrase.notes],
        )
    return _replace_phrase(
        phrase,
        notes=[
            Note(note.scale_degree, note.duration_beats, note.accent or index % every == 0)
            for index, note in enumerate(phrase.notes)
        ],
    )


def _split_phrase(phrase: Phrase, *, max_duration: float) -> Phrase:
    notes: list[Note] = []
    for note in phrase.notes:
        duration = max(0.25, note.duration_beats)
        if duration <= max_duration:
            notes.append(note)
            continue
        remaining = duration
        segment_index = 0
        while remaining > 0.001:
            segment = round(min(max_duration, remaining), 2)
            degree = note.scale_degree
            if segment_index > 0 and phrase.role in {"melody", "counter"}:
                degree = _shift_degree(degree, 1 if segment_index % 2 else -1)
            notes.append(Note(scale_degree=degree, duration_beats=segment, accent=note.accent and segment_index == 0))
            remaining = round(remaining - segment, 2)
            segment_index += 1
    return _replace_phrase(phrase, notes=notes)


def _transform_dynamics(phrase: Phrase, delta: int) -> Phrase:
    return _replace_phrase(phrase, dynamic=_shift_dynamic(phrase.dynamic, delta))


def _motif_for_section(score_tree: ScoreTree, section_name: str) -> MotifNode | None:
    motif_ids: list[str] = []
    for section in score_tree.sections:
        if section.scene_name != section_name:
            continue
        for phrase in section.phrases:
            motif_ids.extend(phrase.motif_refs)
        break
    if motif_ids:
        for motif_id in motif_ids:
            for motif in score_tree.motifs:
                if motif.motif_id == motif_id:
                    return motif
    return score_tree.motifs[0] if score_tree.motifs else None


def _section_mood(mood: Mapping[str, float], *, function: str) -> dict[str, float]:
    energy = float(mood.get("energy", 0.5) or 0.5)
    valence = float(mood.get("valence", 0.5) or 0.5)
    arousal = float(mood.get("arousal", 0.5) or 0.5)
    adjustments = {
        "invocation": (-0.12, -0.02, -0.08),
        "statement": (0.0, 0.0, 0.0),
        "lift": (0.08, 0.02, 0.1),
        "arrival": (0.14, 0.04, 0.12),
        "refrain": (0.14, 0.05, 0.12),
        "development": (0.05, -0.03, 0.08),
        "turn": (-0.03, -0.06, 0.04),
        "instrumental_response": (0.03, 0.0, 0.06),
        "recap": (-0.01, 0.02, -0.01),
        "coda": (-0.08, 0.0, -0.06),
        "residue": (-0.16, -0.02, -0.12),
    }
    de, dv, da = adjustments.get(function, (0.0, 0.0, 0.0))
    return {
        "energy": round(_clamp(energy + de, 0.0, 1.0), 3),
        "valence": round(_clamp(valence + dv, 0.0, 1.0), 3),
        "arousal": round(_clamp(arousal + da, 0.0, 1.0), 3),
    }


def _phrase_ops_for_section(score_tree: ScoreTree, scene_name: str) -> tuple[str, ...]:
    ops: list[str] = []
    for section in score_tree.sections:
        if section.scene_name != scene_name:
            continue
        for phrase in section.phrases:
            ops.extend(phrase.transform_ops)
        break
    return tuple(dict.fromkeys(ops))


def _section_root_degree(section: object) -> int:
    harmonic_role = str(getattr(section, "harmonic_role", "") or "")
    function = str(getattr(section, "function", "") or "")
    return int(
        _HARMONIC_ROLE_ROOT_DEGREES.get(
            harmonic_role,
            _SECTION_FUNCTION_ROOT_DEGREES.get(function, 1),
        )
    )


def _section_progression(section: object) -> tuple[int, ...]:
    harmonic_role = str(getattr(section, "harmonic_role", "") or "")
    function = str(getattr(section, "function", "") or "")
    progression = _HARMONIC_ROLE_PROGRESSIONS.get(
        harmonic_role,
        _SECTION_FUNCTION_PROGRESSIONS.get(function, (1, 4, 5, 1)),
    )
    return tuple(int(_clamp(degree, 1, 7)) for degree in progression)


def _section_motif_refs(section: object) -> set[str]:
    refs: set[str] = set()
    for phrase in getattr(section, "phrases", ()):
        refs.update(str(ref) for ref in getattr(phrase, "motif_refs", ()) if str(ref).strip())
    return refs


def _triad_degrees(root_degree: int) -> tuple[int, int, int]:
    return (
        _shift_degree(root_degree, 0),
        _shift_degree(root_degree, 2),
        _shift_degree(root_degree, 4),
    )


def _common_tone_degree(current_root: int, target_root: int) -> int:
    target_degrees = set(_triad_degrees(target_root))
    for degree in _triad_degrees(current_root):
        if degree in target_degrees:
            return degree
    return current_root


def _hard_cut_tagged(score_tree: ScoreTree, current: object, target: object) -> bool:
    arrangement_plan = getattr(score_tree, "arrangement_plan", {})
    if not isinstance(arrangement_plan, Mapping):
        return False
    raw_hard_cuts = arrangement_plan.get("hard_cuts", ())
    if isinstance(raw_hard_cuts, str):
        tags = {raw_hard_cuts}
    elif isinstance(raw_hard_cuts, Mapping):
        tags = {str(tag) for tag, enabled in raw_hard_cuts.items() if enabled}
    else:
        try:
            tags = {str(tag) for tag in raw_hard_cuts}
        except TypeError:
            tags = set()
    current_name = str(getattr(current, "scene_name", "") or "")
    target_name = str(getattr(target, "scene_name", "") or "")
    return bool(
        {
            f"{current_name}->{target_name}",
            f"{current_name}:{target_name}",
            f"{current_name}/{target_name}",
        }
        & tags
    )


def _transition_continuity_elements(
    current: object,
    target: object,
    *,
    current_root: int,
    target_root: int,
    common_tone: int,
    hard_cut: bool,
) -> tuple[str, ...]:
    if hard_cut:
        return ()

    elements: list[str] = []
    if _section_motif_refs(current) & _section_motif_refs(target):
        elements.append("motif")
    if current_root == target_root:
        elements.append("root")
    elif common_tone in _triad_degrees(current_root) and common_tone in _triad_degrees(target_root):
        elements.append("common_tone")
    if str(getattr(current, "cadence_type", "") or "") == str(getattr(target, "cadence_type", "") or ""):
        elements.append("cadence_shape")
    if str(getattr(current, "groove_state", "") or "") == str(getattr(target, "groove_state", "") or ""):
        elements.append("groove")
    if str(getattr(current, "transform_strength", "") or "") == str(getattr(target, "transform_strength", "") or ""):
        elements.append("timbre_density")
    if str(getattr(current, "function", "") or "") == str(getattr(target, "function", "") or ""):
        elements.append("section_function")
    if str(getattr(current, "return_from", "") or "") == str(getattr(target, "scene_name", "") or ""):
        elements.append("formal_return")
    if str(getattr(target, "return_from", "") or "") == str(getattr(current, "scene_name", "") or ""):
        elements.append("formal_return")
    if not elements:
        elements.append("planned_common_tone")
    return tuple(dict.fromkeys(elements))


def _transition_techniques_for_sections(
    current: object,
    target: object,
    *,
    current_root: int,
    target_root: int,
    continuity_elements: tuple[str, ...],
) -> tuple[str, ...]:
    current_function = str(getattr(current, "function", "") or "")
    target_function = str(getattr(target, "function", "") or "")
    current_cadence = str(getattr(current, "cadence_type", "") or "")
    target_cadence = str(getattr(target, "cadence_type", "") or "")
    current_groove = str(getattr(current, "groove_state", "") or "")
    target_groove = str(getattr(target, "groove_state", "") or "")
    current_transform = str(getattr(current, "transform_strength", "") or "")
    target_transform = str(getattr(target, "transform_strength", "") or "")

    techniques: list[str] = []
    if (
        target_function in _PIVOT_EVENT_FUNCTIONS
        or current_function in _PIVOT_EVENT_FUNCTIONS
        or current_cadence != target_cadence
    ):
        techniques.append("pivot_event")
    if target_function in _BREATH_SILENCE_FUNCTIONS or current_function in _BREATH_SILENCE_FUNCTIONS:
        techniques.append("breath_silence")
    if current_groove != target_groove:
        techniques.append("metric_modulation")
    if current_transform != target_transform:
        techniques.append("timbral_morph")
    if current_root != target_root or current_cadence != target_cadence:
        techniques.append("harmonic_pivot_chord")
    if current_root != target_root or {"motif", "common_tone", "planned_common_tone"} & set(continuity_elements):
        techniques.append("common_tone_bridge")
    if not techniques:
        techniques.append("common_tone_bridge")
    return tuple(dict.fromkeys(technique for technique in techniques if technique in _SUPPORTED_TRANSITION_TECHNIQUES))


def _metric_ratio_for_transition(current: object, target: object) -> str:
    current_function = str(getattr(current, "function", "") or "")
    target_function = str(getattr(target, "function", "") or "")
    current_groove = str(getattr(current, "groove_state", "") or "")
    target_groove = str(getattr(target, "groove_state", "") or "")
    if current_groove == target_groove:
        return "1:1"
    if target_function in {"turn", "coda", "residue"}:
        return "2:1"
    if current_function in {"invocation", "statement"} and target_function in {"lift", "arrival", "refrain"}:
        return "3:2"
    return "4:3"


def _transition_profile_for_section(score_tree: ScoreTree, section_index: int) -> dict[str, str]:
    if section_index < 0 or section_index >= len(score_tree.sections) - 1:
        return {}
    current = score_tree.sections[section_index]
    target = score_tree.sections[section_index + 1]
    current_root = _section_root_degree(current)
    target_root = _section_root_degree(target)
    common_tone = _common_tone_degree(current_root, target_root)
    hard_cut = _hard_cut_tagged(score_tree, current, target)
    continuity_elements = _transition_continuity_elements(
        current,
        target,
        current_root=current_root,
        target_root=target_root,
        common_tone=common_tone,
        hard_cut=hard_cut,
    )
    techniques = (
        ("hard_cut",)
        if hard_cut
        else _transition_techniques_for_sections(
            current,
            target,
            current_root=current_root,
            target_root=target_root,
            continuity_elements=continuity_elements,
        )
    )
    return {
        "transition_target_scene": target.scene_name,
        "transition_target_function": target.function,
        "transition_target_cadence": target.cadence_type,
        "transition_target_root_degree": str(target_root),
        "transition_motion": f"{current.function}_to_{target.function}",
        "transition_prepare_count": "2",
        "transition_technique": techniques[0],
        "transition_techniques": json.dumps(list(techniques)),
        "transition_continuity_elements": json.dumps(list(continuity_elements)),
        "transition_hard_cut": "true" if hard_cut else "false",
        "transition_pivot_event": f"{current.scene_name}_tail_to_{target.scene_name}_entrance",
        "transition_breath_rows": "4" if "breath_silence" in techniques else "0",
        "transition_metric_ratio": _metric_ratio_for_transition(current, target),
        "transition_timbral_morph": (
            f"{getattr(current, 'transform_strength', '') or 'none'}_to_"
            f"{getattr(target, 'transform_strength', '') or 'none'}"
        ),
        "transition_pivot_chord_degree": str(common_tone if current_root != target_root else target_root),
        "transition_common_tone_degree": str(common_tone),
    }


def _with_transition_profile(phrase: Phrase, profile: Mapping[str, str]) -> Phrase:
    if not profile or not phrase.notes:
        return phrase
    metadata = dict(phrase.metadata)
    metadata.update({str(key): str(value) for key, value in profile.items() if str(value).strip()})
    return _replace_phrase(phrase, metadata=metadata)


def _motif_development_for_function(function: str) -> str:
    return _MOTIF_DEVELOPMENT_BY_FUNCTION.get(function, "statement")


def _rhythm_development_for_function(function: str) -> str:
    return _RHYTHM_DEVELOPMENT_BY_FUNCTION.get(function, "steady_statement")


def _apply_rhythm_development(
    phrase: Phrase,
    *,
    section: object,
) -> Phrase:
    rhythm_development = _rhythm_development_for_function(str(getattr(section, "function", "") or "statement"))
    cell = _RHYTHM_DURATION_CELLS.get(rhythm_development, _RHYTHM_DURATION_CELLS["steady_statement"])
    if not phrase.notes:
        return phrase

    notes: list[Note] = []
    for index, note in enumerate(phrase.notes):
        duration = float(cell[index % len(cell)])
        degree = note.scale_degree
        accent = note.accent
        if phrase.role == "bass":
            duration = max(0.5, duration)
            accent = accent or index % len(cell) == 0
        elif phrase.role == "color":
            duration = max(1.0, duration * 1.5)
            accent = False if rhythm_development in {"residue_breath", "sparse_breath"} else accent
        elif phrase.role in {"melody", "counter"}:
            if rhythm_development == "syncopated_fragment":
                accent = accent or index % 3 == 1
            elif rhythm_development == "half_time_displacement":
                accent = accent or index % 4 == 0
            elif rhythm_development == "recall_groove":
                accent = accent or index % 4 in {0, 2}
        if rhythm_development in {"liquidation_slowdown", "residue_breath"} and index > len(phrase.notes) // 2:
            duration *= 1.25
        notes.append(
            Note(
                scale_degree=degree,
                duration_beats=round(max(0.25, min(duration, 3.0)), 2),
                accent=accent,
            )
        )

    if rhythm_development == "residue_breath" and phrase.role != "color":
        thinned = [note for index, note in enumerate(notes) if index % 2 == 0 or index == len(notes) - 1]
        notes = thinned or notes[:1]
    elif rhythm_development == "liquidation_slowdown" and phrase.role in {"melody", "counter"}:
        thinned = [note for index, note in enumerate(notes) if index % 2 == 0 or index == len(notes) - 1]
        notes = thinned or notes[:1]

    metadata = dict(phrase.metadata)
    metadata["rhythm_development"] = rhythm_development
    metadata["rhythm"] = json.dumps(list(cell))
    return _replace_phrase(phrase, notes=notes, metadata=metadata)


def _invert_degree(degree: int) -> int:
    return int(_clamp(9 - degree, 1, 8))


def _motif_degrees_for_development(
    motif: MotifNode | None,
    *,
    development: str,
) -> tuple[int, ...]:
    if motif is None:
        return ()
    anchor = tuple(int(_clamp(degree, 1, 8)) for degree in motif.anchor_degrees)
    answer = tuple(int(_clamp(degree, 1, 8)) for degree in motif.answer_degrees)
    contour = tuple(int(_clamp(degree, 1, 8)) for degree in motif.contour)
    if development == "statement":
        return anchor or contour
    if development == "sequence":
        seed = anchor or contour
        return tuple(_shift_degree(degree, 1 if index % 2 else 0) for index, degree in enumerate(seed))
    if development == "arrival":
        return answer or anchor or contour
    if development == "sequence_fragment":
        seed = answer or anchor or contour
        if len(seed) <= 2:
            return seed
        fragment = seed[1:] + seed[:1]
        return tuple(_shift_degree(degree, 1 if index % 2 == 0 else -1) for index, degree in enumerate(fragment))
    if development == "contrast_inversion":
        seed = tuple(reversed(answer or anchor or contour))
        return tuple(_invert_degree(degree) for degree in seed)
    if development == "recall_answer":
        seed = anchor or contour
        tail = answer[-2:] if len(answer) >= 2 else answer
        return tuple(seed[:2] + tail) if tail else seed
    if development in {"liquidation", "residue"}:
        seed = anchor or contour
        return tuple(seed[: max(1, min(2, len(seed)))])
    return anchor or answer or contour


def _develop_phrase_motif(
    phrase: Phrase,
    *,
    motif: MotifNode | None,
    section: object,
) -> Phrase:
    development = _motif_development_for_function(str(getattr(section, "function", "") or "statement"))
    transformed = _replace_phrase(phrase)
    target_degrees = _motif_degrees_for_development(motif, development=development)

    if target_degrees and transformed.role in {"melody", "counter"}:
        transformed = _apply_hook_degrees(transformed, target_degrees)
    if development == "sequence_fragment" and transformed.role in {"melody", "counter"}:
        transformed = _rotate_phrase(_split_phrase(transformed, max_duration=0.75), 1)
    elif development == "contrast_inversion" and transformed.role in {"melody", "counter", "color"}:
        transformed = _replace_phrase(
            transformed,
            notes=[
                Note(
                    scale_degree=_invert_degree(note.scale_degree) if note.scale_degree > 0 else note.scale_degree,
                    duration_beats=note.duration_beats,
                    accent=note.accent or index == 0,
                )
                for index, note in enumerate(transformed.notes)
            ],
        )
    elif development == "liquidation":
        transformed = _thin_phrase(transformed, 2)
        transformed = _scale_phrase_durations(transformed, 1.08)
    elif development == "residue":
        transformed = _thin_phrase(transformed, 2 if transformed.role != "color" else 1)
        transformed = _scale_phrase_durations(transformed, 1.18)

    metadata = dict(transformed.metadata)
    metadata["motif_development"] = development
    if motif is not None:
        metadata["motif_id"] = motif.motif_id
    metadata["section_function"] = str(getattr(section, "function", "") or "")
    return _replace_phrase(transformed, metadata=metadata)


def _progression_span(note_count: int, progression: tuple[int, ...]) -> int:
    if not progression:
        return max(1, note_count)
    return max(1, int(round(max(1, note_count) / len(progression))))


def _apply_section_progression(phrase: Phrase, progression: tuple[int, ...]) -> Phrase:
    if not progression or not phrase.notes:
        return phrase
    span = _progression_span(len(phrase.notes), progression)
    families_raw = phrase.metadata.get("internal_phrase_families")
    lengths_raw = phrase.metadata.get("internal_phrase_family_lengths")
    family_start_roots: dict[int, int] = {}
    try:
        families_for_starts = json.loads(families_raw) if families_raw else []
        lengths_for_starts = json.loads(lengths_raw) if lengths_raw else []
    except (TypeError, ValueError):
        families_for_starts = []
        lengths_for_starts = []
    if isinstance(families_for_starts, list) and isinstance(lengths_for_starts, list):
        cursor = 0
        for family_index, length in enumerate(lengths_for_starts):
            try:
                segment_length = int(length)
            except (TypeError, ValueError):
                continue
            if segment_length <= 0:
                continue
            family_start_roots[cursor] = progression[min(len(progression) - 1, family_index)]
            cursor += segment_length

    notes: list[Note] = []
    for index, note in enumerate(phrase.notes):
        root = progression[min(len(progression) - 1, index // span)]
        slot = index % span
        degree = note.scale_degree
        accent = note.accent
        if degree > 0:
            if phrase.role == "bass" and index in family_start_roots:
                degree = family_start_roots[index]
                accent = True
            elif phrase.role == "bass":
                if slot == 0:
                    degree = root
                    accent = True
                elif slot % 3 == 1:
                    degree = _shift_degree(root, 4)
                elif slot % 3 == 2:
                    degree = _shift_degree(root, 2)
                else:
                    degree = root
            elif phrase.role == "counter":
                if slot == 0:
                    degree = _shift_degree(root, 4)
                    accent = accent or index == 0
                elif slot % 2 == 0:
                    degree = _shift_degree(root, 2)
            elif phrase.role == "color":
                degree = (root, _shift_degree(root, 2), _shift_degree(root, 4))[slot % 3]
            elif phrase.role == "melody" and slot == 0 and index > 0:
                degree = _shift_degree(root, 2 if index % 2 else 0)
        notes.append(Note(scale_degree=degree, duration_beats=note.duration_beats, accent=accent))

    metadata = dict(phrase.metadata)
    metadata["section_progression"] = json.dumps(list(progression))
    metadata["section_progression_span"] = str(span)
    families_raw = metadata.get("internal_phrase_families")
    profiles_raw = metadata.get("internal_phrase_family_profiles")
    if families_raw and profiles_raw:
        try:
            families = json.loads(families_raw)
            profiles = json.loads(profiles_raw)
        except (TypeError, ValueError):
            families = []
            profiles = {}
        if isinstance(families, list) and isinstance(profiles, dict):
            for family_index, family_label in enumerate(families):
                if not isinstance(family_label, str):
                    continue
                profile = profiles.get(family_label)
                if not isinstance(profile, dict):
                    profile = {}
                profile["root_degree"] = progression[min(len(progression) - 1, family_index)]
                profiles[family_label] = profile
            metadata["internal_phrase_family_profiles"] = json.dumps(profiles)
    return _replace_phrase(phrase, notes=notes, metadata=metadata)


def _transform_phrase_for_section(
    phrase: Phrase,
    *,
    scene_name: str,
    function: str,
    patch_name: str,
    motif: MotifNode | None,
    ops: tuple[str, ...],
) -> Phrase:
    transformed = _replace_phrase(phrase)
    anchor = motif.anchor_degrees if motif is not None else ()
    answer = motif.answer_degrees if motif is not None else ()
    if function == "invocation":
        transformed = _thin_phrase(transformed, 2 if phrase.role != "bass" else 1)
        transformed = _scale_phrase_durations(transformed, 1.12)
        transformed = _transform_dynamics(transformed, -1)
    elif function == "statement":
        if phrase.role in {"melody", "counter"} and anchor:
            transformed = _apply_hook_degrees(transformed, anchor)
    elif function == "lift":
        transformed = _split_phrase(transformed, max_duration=1.0)
        transformed = _scale_phrase_durations(transformed, 0.94)
        transformed = _accent_phrase(transformed, 2)
        transformed = _transform_dynamics(transformed, 1 if phrase.role in {"melody", "bass"} else 0)
    elif function in {"arrival", "refrain"}:
        transformed = _split_phrase(transformed, max_duration=0.8)
        transformed = _accent_phrase(transformed, 2)
        if phrase.role in {"melody", "counter"} and anchor:
            transformed = _apply_hook_degrees(transformed, anchor)
        transformed = _transform_dynamics(transformed, 1 if phrase.role != "color" else 0)
    elif function in {"development", "instrumental_response"}:
        transformed = _rotate_phrase(transformed, 1)
        transformed = _split_phrase(transformed, max_duration=0.9)
        if phrase.role in {"melody", "counter"} and (answer or anchor):
            transformed = _apply_hook_degrees(transformed, answer or anchor)
    elif function == "turn":
        transformed = _rotate_phrase(transformed, 2)
        if phrase.role == "bass":
            transformed = _thin_phrase(transformed, 2)
        else:
            transformed = _split_phrase(transformed, max_duration=0.95)
        if phrase.role in {"melody", "counter"} and (answer or anchor):
            transformed = _apply_hook_degrees(transformed, tuple(reversed(answer or anchor)))
        transformed = _transform_dynamics(transformed, -1 if phrase.role == "color" else 0)
    elif function == "recap":
        if phrase.role in {"melody", "counter"} and (answer or anchor):
            transformed = _apply_hook_degrees(transformed, answer or anchor)
        transformed = _accent_phrase(transformed, 3)
    elif function == "coda":
        transformed = _thin_phrase(transformed, 2)
        transformed = _scale_phrase_durations(transformed, 1.08)
        if phrase.role in {"melody", "counter"} and (answer or anchor):
            transformed = _apply_hook_degrees(transformed, answer or anchor)
        transformed = _transform_dynamics(transformed, -1)
    elif function == "residue":
        transformed = _thin_phrase(transformed, 2 if phrase.role != "color" else 1)
        transformed = _scale_phrase_durations(transformed, 1.22)
        if phrase.role in {"melody", "counter"} and (answer or anchor):
            transformed = _apply_hook_degrees(transformed, answer or anchor)
        transformed = _transform_dynamics(transformed, -2 if phrase.role != "color" else -1)

    if "reharmonize" in ops and phrase.role in {"melody", "counter", "bass"}:
        transformed = _replace_phrase(
            transformed,
            notes=[
                Note(
                    scale_degree=_shift_degree(note.scale_degree, 1 if index % 2 == 0 else -1),
                    duration_beats=note.duration_beats,
                    accent=note.accent,
                )
                for index, note in enumerate(transformed.notes)
            ],
        )
    if "expand" in ops:
        transformed = _split_phrase(transformed, max_duration=0.85 if phrase.role != "color" else 1.1)
    if "answer" in ops and phrase.role in {"melody", "counter"} and answer:
        transformed = _apply_hook_degrees(transformed, answer)
    if phrase.role == "melody":
        transformed = _shape_patch_ending(transformed, patch_name=patch_name)
    return transformed


_INTERNAL_FAMILY_LABELS = ("A", "A_prime", "B", "A_double_prime")
_INTERNAL_FAMILY_PROFILES: dict[str, dict[str, object]] = {
    "A": {
        "root_degree": 1,
        "function": "statement",
        "counter_offset": 2,
        "texture_offsets": (0, 2, 4),
    },
    "A_prime": {
        "root_degree": 4,
        "function": "lift",
        "counter_offset": 4,
        "texture_offsets": (0, 2, 5),
    },
    "B": {
        "root_degree": 5,
        "function": "turn",
        "counter_offset": 2,
        "texture_offsets": (0, 3, 5),
    },
    "A_double_prime": {
        "root_degree": 1,
        "function": "return",
        "counter_offset": 2,
        "texture_offsets": (0, 2, 4),
    },
}


def _degree_from_root(root_degree: int, offset: int) -> int:
    return _shift_degree(int(root_degree), int(offset))


def _profile_for_family(label: str) -> dict[str, object]:
    return dict(_INTERNAL_FAMILY_PROFILES.get(label, _INTERNAL_FAMILY_PROFILES["A"]))


def _coordinate_variant_to_profile(
    phrase: Phrase,
    *,
    family_label: str,
    profile: Mapping[str, object],
) -> Phrase:
    if not phrase.notes:
        return phrase
    root = int(profile.get("root_degree", 1) or 1)
    counter_offset = int(profile.get("counter_offset", 2) or 2)
    texture_offsets_raw = profile.get("texture_offsets", (0, 2, 4))
    texture_offsets = tuple(int(value) for value in texture_offsets_raw) if isinstance(texture_offsets_raw, tuple) else (0, 2, 4)
    notes: list[Note] = []
    for index, note in enumerate(phrase.notes):
        degree = note.scale_degree
        accent = note.accent
        if degree > 0:
            if phrase.role == "bass":
                degree = root if index % 2 == 0 else _degree_from_root(root, 4 if family_label != "A_prime" else 3)
                accent = accent or index == 0
            elif phrase.role == "counter":
                degree = _degree_from_root(root, counter_offset if index % 2 == 0 else counter_offset - 1)
                accent = accent or (family_label == "B" and index == 0)
            elif phrase.role == "color":
                degree = _degree_from_root(root, texture_offsets[index % len(texture_offsets)])
            elif phrase.role == "melody" and index == 0:
                if family_label == "A":
                    degree = root
                elif family_label == "A_prime":
                    degree = _degree_from_root(root, 2)
                elif family_label == "B":
                    degree = _degree_from_root(root, 4)
        notes.append(Note(scale_degree=degree, duration_beats=note.duration_beats, accent=accent))
    return _replace_phrase(phrase, notes=notes)


def _shift_phrase_degrees(phrase: Phrase, *, family_label: str) -> Phrase:
    if not phrase.notes:
        return phrase
    notes: list[Note] = []
    for index, note in enumerate(phrase.notes):
        degree = note.scale_degree
        if degree > 0:
            if family_label == "A_prime":
                if phrase.role == "bass":
                    degree = _shift_degree(degree, 2 if index % 2 else 0)
                elif phrase.role == "color":
                    degree = _shift_degree(degree, 1 if index == len(phrase.notes) - 1 else 0)
                else:
                    degree = _shift_degree(degree, 1 if index % 2 else 0)
            elif family_label == "B":
                if phrase.role == "bass":
                    degree = _shift_degree(degree, 4 if index % 2 else 2)
                elif phrase.role == "color":
                    degree = _shift_degree(degree, 2)
                else:
                    degree = _shift_degree(degree, 2 if index % 2 == 0 else -1)
            elif family_label == "A_double_prime":
                if index == len(phrase.notes) - 1:
                    degree = 1 if phrase.role == "bass" else _shift_degree(degree, -1)
                elif index % 3 == 1:
                    degree = _shift_degree(degree, 1)
        notes.append(
            Note(
                scale_degree=degree,
                duration_beats=note.duration_beats,
                accent=note.accent or (family_label in {"A_prime", "B"} and index == 0),
            )
        )
    return _replace_phrase(phrase, notes=notes)


def _internal_variant_for_family(
    phrase: Phrase,
    *,
    family_label: str,
    motif: MotifNode | None,
    duration_factor: float,
) -> Phrase:
    profile = _profile_for_family(family_label)
    variant = _replace_phrase(phrase)
    if family_label == "A":
        pass
    elif family_label == "A_prime":
        variant = _rotate_phrase(variant, 1 if phrase.role != "bass" else 0)
        variant = _shift_phrase_degrees(variant, family_label=family_label)
        variant = _accent_phrase(variant, 2)
    elif family_label == "B":
        variant = _rotate_phrase(variant, 2 if len(variant.notes) > 2 else 1)
        if phrase.role in {"melody", "counter"} and motif is not None and motif.answer_degrees:
            variant = _apply_hook_degrees(variant, motif.answer_degrees)
        variant = _shift_phrase_degrees(variant, family_label=family_label)
        variant = _accent_phrase(variant, 2 if phrase.role != "color" else 1)
        variant = _transform_dynamics(variant, 1 if phrase.role in {"melody", "counter", "bass"} else 0)
    elif family_label == "A_double_prime":
        if phrase.role in {"melody", "counter"} and motif is not None and motif.anchor_degrees:
            variant = _apply_hook_degrees(variant, motif.anchor_degrees)
        variant = _shift_phrase_degrees(variant, family_label=family_label)
        variant = _accent_phrase(variant, 3)
    variant = _coordinate_variant_to_profile(
        variant,
        family_label=family_label,
        profile=profile,
    )
    return _scale_phrase_durations(variant, duration_factor)


def _expand_internal_phrase_families(
    phrase: Phrase,
    *,
    section: object,
    motif: MotifNode | None,
) -> Phrase:
    phrase_nodes = getattr(section, "phrases", ())
    family_count = min(len(phrase_nodes), len(_INTERNAL_FAMILY_LABELS))
    if family_count <= 1 or not phrase.notes:
        return phrase

    labels = _INTERNAL_FAMILY_LABELS[:family_count]
    # Keep the complete phrase family close to the original beat span; long-form
    # duration still comes from section budgets, not uncontrolled note bloat.
    duration_factor = max(0.25, round(1.0 / family_count, 3))
    notes: list[Note] = []
    lengths: list[int] = []
    used_labels: list[str] = []
    for label in labels:
        variant = _internal_variant_for_family(
            phrase,
            family_label=label,
            motif=motif,
            duration_factor=duration_factor,
        )
        if not variant.notes:
            continue
        notes.extend(variant.notes)
        lengths.append(len(variant.notes))
        used_labels.append(label)

    if not notes:
        return phrase

    metadata = dict(phrase.metadata)
    metadata["internal_phrase_families"] = json.dumps(used_labels)
    metadata["internal_phrase_family_lengths"] = json.dumps(lengths)
    metadata["internal_phrase_family_profiles"] = json.dumps(
        {
            label: {
                "root_degree": int(_profile_for_family(label).get("root_degree", 1) or 1),
                "function": str(_profile_for_family(label).get("function", "statement") or "statement"),
            }
            for label in used_labels
        }
    )
    metadata["internal_phrase_count"] = str(len(used_labels))
    return _replace_phrase(phrase, notes=notes, metadata=metadata)


def _sample_gesture_metadata_for_section(score_tree: ScoreTree, section: SectionNode) -> dict[str, str]:
    gestures = score_tree.arrangement_plan.get("sample_gestures", {})
    if not isinstance(gestures, Mapping):
        return {}
    raw = gestures.get(section.scene_name, gestures.get(section.function))
    if raw is True:
        raw = {}
    if raw is None or not isinstance(raw, Mapping):
        return {}

    defaults = _SAMPLE_GESTURE_DEFAULTS_BY_FUNCTION.get(
        section.function,
        {
            "mode": "slice_accents",
            "voice": "sample_slice",
            "transforms": ("slice_rearrange", "pitch_window"),
            "density": 0.24,
            "max_events": 4,
        },
    )
    transforms = raw.get("transforms", defaults["transforms"])
    if isinstance(transforms, str):
        transforms_payload = transforms
    else:
        transforms_payload = json.dumps([str(value) for value in transforms])
    source_kind = raw.get("source_kind") or raw.get("sample_origin") or "gesture"
    return {
        "sample_gesture_voice": str(raw.get("voice", defaults["voice"]) or defaults["voice"]),
        "sample_gesture_source": str(raw.get("source", "room_mic") or "room_mic"),
        "source_kind": str(source_kind),
        "sample_gesture_mode": str(raw.get("mode", defaults["mode"]) or defaults["mode"]),
        "sample_gesture_transforms": transforms_payload,
        "sample_gesture_density": str(raw.get("density", defaults["density"]) or defaults["density"]),
        "sample_gesture_max_events": str(raw.get("max_events", defaults["max_events"]) or defaults["max_events"]),
    }


def _production_arc_metadata_for_section(score_tree: ScoreTree, section: SectionNode) -> dict[str, str]:
    production_arc = score_tree.arrangement_plan.get("production_arc", {})
    if isinstance(production_arc, Mapping):
        raw = production_arc.get(section.scene_name, production_arc.get(section.function))
        if isinstance(raw, Mapping):
            return {
                key: str(raw.get(key, "") or "")
                for key in _ARC_METADATA_KEYS
                if str(raw.get(key, "") or "").strip()
            }
    return {
        key: str(score_tree.metadata.get(key, "") or "")
        for key in _ARC_METADATA_KEYS
        if str(score_tree.metadata.get(key, "") or "").strip()
    }


def _arc_automation_defaults(
    defaults: Mapping[str, float],
    arc_metadata: Mapping[str, str],
    *,
    cadence_state: str,
) -> dict[str, float]:
    automation = dict(defaults)
    density = _float_metadata(arc_metadata.get("arc_density"))
    if density is not None:
        automation["density"] = round(_clamp(density, 0.05, 1.0), 3)
    master_amp = _DYNAMIC_MASTER_AMP.get(str(arc_metadata.get("arc_dynamic", "")))
    if master_amp is not None:
        automation["master_amp"] = master_amp
    compression = _float_metadata(arc_metadata.get("arc_compression"))
    if compression is not None:
        automation["compression"] = round(_clamp(compression, 0.0, 1.0), 3)
    senseweave = _float_metadata(arc_metadata.get("arc_senseweave"))
    if senseweave is not None:
        automation["senseweave"] = round(_clamp(senseweave, 0.0, 1.0), 3)

    phase_name = arc_metadata.get("arc_phase")
    if phase_name:
        spatial = build_spatial_profile(phase_name, cadence_state=cadence_state)
        automation["stereo_width"] = round(spatial.stereo_width, 3)
        automation["depth"] = round(spatial.depth, 3)
        automation["reverb_send"] = round(spatial.reverb_size, 3)
        automation["delay_send"] = round(spatial.delay_send, 3)
    return automation


def _section_score(
    score_tree: ScoreTree,
    base_mood: Mapping[str, float],
    *,
    family_name: str,
    patch_name: str,
    cadence_state: str,
    progression_profile: str,
    section_index: int,
    scene_name: str,
    base_song_num: int,
    transition_profile: Mapping[str, str] | None = None,
) -> Score:
    section = next(section for section in score_tree.sections if section.scene_name == scene_name)
    motif = _motif_for_section(score_tree, scene_name)
    section_progression = _section_progression(section)
    motif_development = _motif_development_for_function(section.function)
    rhythm_development = _rhythm_development_for_function(section.function)
    sample_gesture_metadata = _sample_gesture_metadata_for_section(score_tree, section)
    arc_metadata = _production_arc_metadata_for_section(score_tree, section)
    vocabulary_citation = _vocabulary_citation_for_section(score_tree, section)
    section_mood = _section_mood(base_mood, function=section.function)
    revision = revise_score(
        section_mood,
        song_num=(base_song_num * 17) + section_index + 1,
        family=family_name,
        cadence_state=cadence_state,
        patch_name=patch_name,
        progression_profile=f"{progression_profile}:{section.function}:{section.transform_strength}",
        course=section.production_course if section.production_course else None,
    )
    section_score = revision.final_score
    section_score = enrich_score_for_tracker(section_score, mood=section_mood)
    ops = _phrase_ops_for_section(score_tree, scene_name)
    phrases: list[Phrase] = []
    for phrase in section_score.phrases:
        transformed = _transform_phrase_for_section(
            phrase,
            scene_name=scene_name,
            function=section.function,
            patch_name=patch_name,
            motif=motif,
            ops=ops,
        )
        developed = _develop_phrase_motif(
            transformed,
            motif=motif,
            section=section,
        )
        rhythm_shaped = _apply_rhythm_development(
            developed,
            section=section,
        )
        expanded = _expand_internal_phrase_families(
            rhythm_shaped,
            section=section,
            motif=motif,
        )
        progressed = _apply_section_progression(expanded, section_progression)
        vocabulary_shaped = _apply_vocabulary_citation(
            progressed,
            vocabulary_citation,
        )
        featured = _with_render_features(vocabulary_shaped, key=section_score.key)
        phrases.append(_with_transition_profile(featured, transition_profile or {}))
    metadata = dict(section_score.metadata)
    metadata.update(
        {
            "song_title": score_tree.title,
            "text_hook": score_tree.primary_hook_text,
            "hook_class": score_tree.motifs[0].hook_class if score_tree.motifs else "",
            "hook_anchor_degrees": json.dumps(list(score_tree.motifs[0].anchor_degrees)) if score_tree.motifs else "[]",
            "hook_answer_degrees": json.dumps(list(score_tree.motifs[0].answer_degrees)) if score_tree.motifs else "[]",
            "patch_name": patch_name,
            "cadence_state": cadence_state,
            "progression_profile": progression_profile,
            "scene_name": scene_name,
            "motif_development": motif_development,
            "rhythm_development": rhythm_development,
            "rhythm": json.dumps(list(_RHYTHM_DURATION_CELLS.get(rhythm_development, ()))),
            "section_progression": json.dumps(list(section_progression)),
        }
    )
    if sample_gesture_metadata:
        metadata.update(sample_gesture_metadata)
    if arc_metadata:
        metadata.update(arc_metadata)
    if vocabulary_citation:
        metadata.update(citation_metadata_from_payload(vocabulary_citation))
    if transition_profile:
        metadata.update({str(key): str(value) for key, value in transition_profile.items() if str(value).strip()})
    for key in PRODUCTION_COURSE_KEYS:
        value = section.production_course.get(key)
        if value:
            metadata[f"production_{key}"] = value
    counterpoint_relation = section.production_course.get("counterpoint_relation", "")
    if counterpoint_relation:
        metadata["counterpoint_rule_id"] = _resolve_counterpoint_rule_id(counterpoint_relation)
    return Score(
        phrases=phrases,
        key=section_score.key,
        tempo_bpm=section_score.tempo_bpm,
        mood=section_score.mood,
        created_at=section_score.created_at,
        metadata=metadata,
    )


def _scene_scores_for_tree(
    score_tree: ScoreTree,
    mood: Mapping[str, float],
    *,
    family_name: str,
    patch_name: str,
    cadence_state: str,
    progression_profile: str,
) -> dict[str, Score]:
    base_song_num = int(score_tree.metadata.get("song_num", "1") or 1)
    return {
        section.scene_name: _section_score(
            score_tree,
            mood,
            family_name=family_name,
            patch_name=patch_name,
            cadence_state=cadence_state,
            progression_profile=progression_profile,
            section_index=index,
            scene_name=section.scene_name,
            base_song_num=base_song_num,
            transition_profile=_transition_profile_for_section(score_tree, index),
        )
        for index, section in enumerate(score_tree.sections)
    }


def estimate_tracker_song_duration_s(song: object) -> float:
    total = 0.0
    for scene in getattr(song, "scenes", []):
        rows = float(getattr(getattr(scene, "pattern", None), "rows", 0) or 0)
        rows_per_beat = float(getattr(scene, "rows_per_beat", 4) or 4)
        tempo = float(getattr(scene, "tempo_bpm", 60.0) or 60.0)
        total += (rows / rows_per_beat) * 60.0 / max(tempo, 1.0)
    return round(total, 2)


def _scene_templates_for_tree(score_tree: ScoreTree, base_score: Score, scale: float = 1.0) -> tuple[SceneTemplate, ...]:
    base_duration_s = max(1.0, _base_scene_duration_s(base_score))
    templates: list[SceneTemplate] = []
    for section in score_tree.sections:
        defaults = _SECTION_DEFAULTS.get(section.scene_name, _SECTION_DEFAULTS["Theme"])
        arc_metadata = _production_arc_metadata_for_section(score_tree, section)
        automation_defaults = _arc_automation_defaults(
            defaults["automation"],
            arc_metadata,
            cadence_state=score_tree.metadata.get("cadence_state", ""),
        )
        allowed_roles = tuple(defaults["allowed_roles"])
        max_polyphony = int(defaults["max_polyphony"])
        if _sample_gesture_metadata_for_section(score_tree, section):
            allowed_roles = allowed_roles if "sample" in allowed_roles else (*allowed_roles, "sample")
            max_polyphony += 1
        ratio = (section.target_duration_s / base_duration_s) * scale
        repeat_count, length_multiplier = _repeat_plan_for_ratio(ratio)
        templates.append(
            SceneTemplate(
                name=section.scene_name,
                allowed_roles=allowed_roles,
                tempo_multiplier=float(defaults["tempo_multiplier"]),
                max_polyphony=max_polyphony,
                automation_defaults=automation_defaults,
                length_multiplier=length_multiplier,
                repeat_count=repeat_count,
            )
        )
    return tuple(templates)


def compile_score_tree_to_tracker(
    score_tree: ScoreTree,
    *,
    mood: Mapping[str, float],
    family_name: str,
    patch_name: str,
    cadence_state: str,
    progression_profile: str | None = None,
    role_hints: Mapping[str, Mapping[str, str]] | None = None,
    scene_keys: Mapping[str, str] | None = None,
    rows_per_beat: int = 4,
) -> CompiledTrackerPiece:
    progression = progression_profile or score_tree.metadata.get("progression_profile", "")
    first_course = next(
        (s.production_course for s in score_tree.sections if s.production_course),
        None,
    )
    revision = revise_score(
        dict(mood),
        song_num=int(score_tree.metadata.get("song_num", "1") or 1),
        family=family_name,
        cadence_state=cadence_state,
        patch_name=patch_name,
        progression_profile=progression,
        course=first_course or None,
    )
    score = revision.final_score
    score.metadata.update(
        {
            "song_title": score_tree.title,
            "text_hook": score_tree.primary_hook_text,
            "hook_class": score_tree.motifs[0].hook_class if score_tree.motifs else "",
            "hook_anchor_degrees": json.dumps(list(score_tree.motifs[0].anchor_degrees)) if score_tree.motifs else "[]",
            "hook_answer_degrees": json.dumps(list(score_tree.motifs[0].answer_degrees)) if score_tree.motifs else "[]",
            "patch_name": patch_name,
            "cadence_state": cadence_state,
            "progression_profile": progression,
            "section_functions": json.dumps({section.scene_name: section.function for section in score_tree.sections}),
            "section_cadences": json.dumps({section.scene_name: section.cadence_type for section in score_tree.sections}),
            "score_tree_id": score_tree.piece_id,
            "form_class": score_tree.commission.form_class,
            "composition_mode": score_tree.commission.composition_mode,
            "ending_family": score_tree.ending_family,
        }
    )
    for key in (*_ARC_METADATA_KEYS, "arc_phase_contour"):
        if key in score_tree.metadata:
            score.metadata[key] = score_tree.metadata[key]
    for key in VOCABULARY_METADATA_KEYS:
        if key in score_tree.metadata:
            score.metadata[key] = score_tree.metadata[key]
    section_courses = {
        section.scene_name: section.production_course
        for section in score_tree.sections
        if section.production_course
    }
    if section_courses:
        score.metadata["section_production_courses"] = json.dumps(section_courses)
    score = enrich_score_for_tracker(score, mood=mood)
    scene_scores = _scene_scores_for_tree(
        score_tree,
        dict(mood),
        family_name=family_name,
        patch_name=patch_name,
        cadence_state=cadence_state,
        progression_profile=progression,
    )
    templates = _scene_templates_for_tree(score_tree, score, scale=1.0)
    tracker_song = build_korsakov_tracker_song(
        score,
        title=score_tree.title,
        rows_per_beat=rows_per_beat,
        mood=mood,
        role_hints=role_hints,
        form_templates=templates,
        family_name=family_name,
        scene_keys=scene_keys,
        scene_scores=scene_scores,
    )
    estimated = estimate_tracker_song_duration_s(tracker_song)
    target = max(1.0, score_tree.planned_duration_s or score_tree.commission.duration_target_s)
    if estimated > 0 and abs(estimated - target) / target > 0.15:
        scale = target / estimated
        tracker_song = build_korsakov_tracker_song(
            score,
            title=score_tree.title,
            rows_per_beat=rows_per_beat,
            mood=mood,
            role_hints=role_hints,
            form_templates=_scene_templates_for_tree(score_tree, score, scale=scale),
            family_name=family_name,
            scene_keys=scene_keys,
            scene_scores=scene_scores,
        )
        estimated = estimate_tracker_song_duration_s(tracker_song)
    return CompiledTrackerPiece(
        score_tree=score_tree,
        source_score=score,
        tracker_song=tracker_song,
        estimated_duration_s=estimated,
    )
