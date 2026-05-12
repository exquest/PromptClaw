"""Canonical score-tree data model for CypherClaw composition."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields as dataclass_fields
import json
from typing import Any, Mapping

from cypherclaw.render.events import PerformanceIntent, SectionEnvelope

from .form_grammar import FormPlan, PlannedSection
from .piece_brief import PieceBrief
from .piece_commission import PieceCommission
from .production_course import REQUIRED_CHAPTER_IDS


MOTIF_LIFECYCLE_STATES: tuple[str, ...] = (
    "statement",
    "variation",
    "contrast",
    "recall",
    "answer",
    "liquidation",
    "residue",
)


_MOTIF_LIFECYCLE_BANDS: Mapping[str, str] = {
    "statement": "introduction",
    "variation": "introduction",
    "contrast": "development",
    "recall": "development",
    "answer": "development",
    "liquidation": "resolution",
    "residue": "resolution",
}


_PERFORMANCE_INTENT_FIELDS: frozenset[str] = frozenset(
    dataclass_field.name for dataclass_field in dataclass_fields(PerformanceIntent)
)
_SECTION_ENVELOPE_FIELDS: frozenset[str] = frozenset(
    dataclass_field.name for dataclass_field in dataclass_fields(SectionEnvelope)
)


def _coerce_performance_intent(
    phrase_id: str,
    payload: object,
) -> PerformanceIntent:
    if isinstance(payload, PerformanceIntent):
        if payload.phrase_id == phrase_id:
            return payload
        data = asdict(payload)
        data["phrase_id"] = phrase_id
        return PerformanceIntent(**data)
    if payload is None:
        return PerformanceIntent(phrase_id=phrase_id)
    if isinstance(payload, Mapping):
        data = {
            str(key): value
            for key, value in payload.items()
            if str(key) in _PERFORMANCE_INTENT_FIELDS
        }
        data["phrase_id"] = str(data.get("phrase_id") or phrase_id)
        return PerformanceIntent(**data)
    raise TypeError(f"unsupported PerformanceIntent payload: {type(payload)!r}")


def _coerce_section_envelope(payload: object) -> SectionEnvelope:
    if isinstance(payload, SectionEnvelope):
        return payload
    if payload is None:
        return SectionEnvelope()
    if isinstance(payload, Mapping):
        data = {
            str(key): value
            for key, value in payload.items()
            if str(key) in _SECTION_ENVELOPE_FIELDS
        }
        return SectionEnvelope(**data)
    raise TypeError(f"unsupported SectionEnvelope payload: {type(payload)!r}")


@dataclass
class MotifNode:
    motif_id: str
    hook_class: str
    contour: tuple[int, ...]
    rhythm: tuple[float, ...]
    anchor_degrees: tuple[int, ...]
    answer_degrees: tuple[int, ...]
    text_hook: str
    timbral_tags: tuple[str, ...] = ()
    lifecycle_state: str = "statement"


@dataclass
class PhraseNode:
    phrase_id: str
    function: str
    motif_refs: tuple[str, ...]
    target_duration_s: float
    transform_ops: tuple[str, ...]
    phrase_family: str = "seed"
    seed_phrase_id: str | None = None
    intent_tag: str = ""
    performance_intent: PerformanceIntent = field(
        default_factory=lambda: PerformanceIntent(phrase_id="")
    )

    def __post_init__(self) -> None:
        self.performance_intent = _coerce_performance_intent(
            self.phrase_id,
            self.performance_intent,
        )


PRODUCTION_COURSE_KEYS: tuple[str, ...] = REQUIRED_CHAPTER_IDS


@dataclass
class SectionNode:
    section_id: str
    scene_name: str
    function: str
    target_duration_s: float
    phrases: list[PhraseNode]
    harmonic_role: str
    cadence_type: str
    groove_state: str
    return_from: str | None = None
    transform_strength: str = "none"
    production_course: dict[str, str] = field(default_factory=dict)
    harmonic_function: str = "tonic"
    transition_intent: str = "maintain"
    section_envelope: SectionEnvelope = field(default_factory=SectionEnvelope)

    def __post_init__(self) -> None:
        self.section_envelope = _coerce_section_envelope(self.section_envelope)


@dataclass
class ScoreTree:
    piece_id: str
    title: str
    commission: PieceCommission
    brief: PieceBrief
    form: FormPlan
    motifs: list[MotifNode]
    sections: list[SectionNode]
    harmonic_plan: dict[str, Any]
    arrangement_plan: dict[str, Any]
    ending_family: str
    narrative_map: dict[str, str]
    metadata: dict[str, str] = field(default_factory=dict)
    planned_duration_s: float = 0.0
    primary_hook_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScoreTree":
        commission_dict = dict(data.get("commission", {}))
        if "reason_tags" in commission_dict:
            commission_dict["reason_tags"] = tuple(commission_dict["reason_tags"])
        commission = PieceCommission(**commission_dict)
        brief_dict = dict(data.get("brief", {}))
        if "image_field" in brief_dict:
            brief_dict["image_field"] = tuple(brief_dict["image_field"])
        if "section_beats" in brief_dict:
            brief_dict["section_beats"] = tuple(brief_dict["section_beats"])
        brief = PieceBrief(**brief_dict)
        form_dict = dict(data.get("form", {}))
        sections_form = tuple(PlannedSection(**item) for item in form_dict.get("sections", ()))
        form = FormPlan(
            form_family=str(form_dict.get("form_family", "default")),
            form_class=str(form_dict.get("form_class", commission.form_class)),
            composition_mode=str(form_dict.get("composition_mode", commission.composition_mode)),
            sections=sections_form,
            ending_family=str(form_dict.get("ending_family", commission.ending_family)),
        )
        motifs = [
            MotifNode(
                motif_id=str(item.get("motif_id", "")),
                hook_class=str(item.get("hook_class", "")),
                contour=tuple(item.get("contour", ())),
                rhythm=tuple(item.get("rhythm", ())),
                anchor_degrees=tuple(item.get("anchor_degrees", ())),
                answer_degrees=tuple(item.get("answer_degrees", ())),
                text_hook=str(item.get("text_hook", "")),
                timbral_tags=tuple(item.get("timbral_tags", ())),
                lifecycle_state=str(item.get("lifecycle_state", "statement")),
            )
            for item in data.get("motifs", ())
        ]
        sections = [
            SectionNode(
                section_id=str(item.get("section_id", "")),
                scene_name=str(item.get("scene_name", "")),
                function=str(item.get("function", "")),
                target_duration_s=float(item.get("target_duration_s", 0.0) or 0.0),
                phrases=[
                    PhraseNode(
                        phrase_id=str(phrase.get("phrase_id", "")),
                        function=str(phrase.get("function", "")),
                        motif_refs=tuple(phrase.get("motif_refs", ())),
                        target_duration_s=float(phrase.get("target_duration_s", 0.0) or 0.0),
                        transform_ops=tuple(phrase.get("transform_ops", ())),
                        phrase_family=str(phrase.get("phrase_family", "seed")),
                        seed_phrase_id=str(phrase["seed_phrase_id"]) if phrase.get("seed_phrase_id") is not None else None,
                        intent_tag=str(phrase.get("intent_tag", "")),
                        performance_intent=phrase.get("performance_intent"),
                    )
                    for phrase in item.get("phrases", ())
                ],
                harmonic_role=str(item.get("harmonic_role", "tonic")),
                cadence_type=str(item.get("cadence_type", "authentic")),
                groove_state=str(item.get("groove_state", "")),
                return_from=str(item["return_from"]) if item.get("return_from") is not None else None,
                transform_strength=str(item.get("transform_strength", "none")),
                production_course={str(k): str(v) for k, v in dict(item.get("production_course", {})).items()},
                harmonic_function=str(item.get("harmonic_function", "tonic")),
                transition_intent=str(item.get("transition_intent", "maintain")),
                section_envelope=item.get("section_envelope"),
            )
            for item in data.get("sections", ())
        ]
        return cls(
            piece_id=str(data.get("piece_id", "")),
            title=str(data.get("title", "")),
            commission=commission,
            brief=brief,
            form=form,
            motifs=motifs,
            sections=sections,
            harmonic_plan=dict(data.get("harmonic_plan", {})),
            arrangement_plan=dict(data.get("arrangement_plan", {})),
            ending_family=str(data.get("ending_family", commission.ending_family)),
            narrative_map={str(k): str(v) for k, v in dict(data.get("narrative_map", {})).items()},
            metadata={str(k): str(v) for k, v in dict(data.get("metadata", {})).items()},
            planned_duration_s=float(data.get("planned_duration_s", 0.0) or 0.0),
            primary_hook_text=str(data.get("primary_hook_text", "")),
        )

    @classmethod
    def minimal(
        cls,
        *,
        piece_id: str,
        title: str,
        commission: PieceCommission,
    ) -> "ScoreTree":
        brief = PieceBrief(
            image_field=("room", "line"),
            dramatic_premise="room holds while the line changes",
            conflict="the room is trying to stay open",
            desired_payoff="let the room resolve without closing",
            residue="leave the line open",
            ending_feeling=commission.ending_family,
            motion_character=commission.groove_identity,
            hook_pressure=commission.hook_pressure,
            through_composed_pressure=0.25,
            section_beats=("opening image", "arrival", "residue"),
            narrative_scale=commission.narrative_scale,
        )
        form = FormPlan(
            form_family="minimal",
            form_class=commission.form_class,
            composition_mode=commission.composition_mode,
            sections=(),
            ending_family=commission.ending_family,
        )
        return cls(
            piece_id=piece_id,
            title=title,
            commission=commission,
            brief=brief,
            form=form,
            motifs=[],
            sections=[],
            harmonic_plan={},
            arrangement_plan={},
            ending_family=commission.ending_family,
            narrative_map={},
            planned_duration_s=commission.duration_target_s,
            primary_hook_text="",
        )


@dataclass(frozen=True)
class ScoreTreeSectionReport:
    section_id: str
    scene_name: str
    function: str
    harmonic_role: str
    harmonic_function: str
    cadence_type: str
    groove_state: str
    transition_intent: str
    transform_strength: str
    target_duration_s: float
    phrase_count: int
    phrase_load_band: str
    motif_refs: tuple[str, ...]
    production_course_complete: bool


@dataclass(frozen=True)
class ScoreTreeReport:
    piece_id: str
    title: str
    form_family: str
    form_class: str
    composition_mode: str
    ending_family: str
    planned_duration_s: float
    section_count: int
    motif_count: int
    phrase_count: int
    motif_lifecycle_counts: dict[str, int]
    unreferenced_motif_ids: tuple[str, ...]
    sections: tuple[ScoreTreeSectionReport, ...]


def motif_lifecycle_band(state: str) -> str:
    if state in _MOTIF_LIFECYCLE_BANDS:
        return _MOTIF_LIFECYCLE_BANDS[state]
    return "unclassified"


def section_phrase_load_band(count: int) -> str:
    if count <= 1:
        return "spare"
    if count <= 3:
        return "compact"
    if count <= 5:
        return "developed"
    return "saturated"


def count_motif_lifecycle_states(tree: ScoreTree) -> dict[str, int]:
    counts: dict[str, int] = {}
    for motif in tree.motifs:
        state = motif.lifecycle_state
        if state not in MOTIF_LIFECYCLE_STATES:
            continue
        counts[state] = counts.get(state, 0) + 1
    return counts


def build_score_tree_section_report(section: SectionNode) -> ScoreTreeSectionReport:
    seen: set[str] = set()
    ordered_refs: list[str] = []
    for phrase in section.phrases:
        for motif_id in phrase.motif_refs:
            if motif_id in seen:
                continue
            seen.add(motif_id)
            ordered_refs.append(motif_id)

    course = section.production_course
    course_complete = bool(REQUIRED_CHAPTER_IDS) and all(
        bool(course.get(chapter_id)) for chapter_id in REQUIRED_CHAPTER_IDS
    )

    phrase_count = len(section.phrases)
    return ScoreTreeSectionReport(
        section_id=section.section_id,
        scene_name=section.scene_name,
        function=section.function,
        harmonic_role=section.harmonic_role,
        harmonic_function=section.harmonic_function,
        cadence_type=section.cadence_type,
        groove_state=section.groove_state,
        transition_intent=section.transition_intent,
        transform_strength=section.transform_strength,
        target_duration_s=section.target_duration_s,
        phrase_count=phrase_count,
        phrase_load_band=section_phrase_load_band(phrase_count),
        motif_refs=tuple(ordered_refs),
        production_course_complete=course_complete,
    )


def build_score_tree_report(tree: ScoreTree) -> ScoreTreeReport:
    section_reports = tuple(
        build_score_tree_section_report(section) for section in tree.sections
    )

    raw_counts = count_motif_lifecycle_states(tree)
    lifecycle_counts: dict[str, int] = {
        state: raw_counts.get(state, 0) for state in MOTIF_LIFECYCLE_STATES
    }

    referenced: set[str] = set()
    phrase_count = 0
    for section in tree.sections:
        for phrase in section.phrases:
            phrase_count += 1
            for motif_id in phrase.motif_refs:
                referenced.add(motif_id)

    unreferenced: list[str] = []
    for motif in tree.motifs:
        if motif.motif_id not in referenced:
            unreferenced.append(motif.motif_id)

    return ScoreTreeReport(
        piece_id=tree.piece_id,
        title=tree.title,
        form_family=tree.form.form_family,
        form_class=tree.form.form_class,
        composition_mode=tree.form.composition_mode,
        ending_family=tree.ending_family,
        planned_duration_s=tree.planned_duration_s,
        section_count=len(tree.sections),
        motif_count=len(tree.motifs),
        phrase_count=phrase_count,
        motif_lifecycle_counts=lifecycle_counts,
        unreferenced_motif_ids=tuple(unreferenced),
        sections=section_reports,
    )


def _section_report_to_dict(report: ScoreTreeSectionReport) -> dict[str, Any]:
    return {
        "section_id": report.section_id,
        "scene_name": report.scene_name,
        "function": report.function,
        "harmonic_role": report.harmonic_role,
        "harmonic_function": report.harmonic_function,
        "cadence_type": report.cadence_type,
        "groove_state": report.groove_state,
        "transition_intent": report.transition_intent,
        "transform_strength": report.transform_strength,
        "target_duration_s": report.target_duration_s,
        "phrase_count": report.phrase_count,
        "phrase_load_band": report.phrase_load_band,
        "motif_refs": list(report.motif_refs),
        "production_course_complete": report.production_course_complete,
    }


def summarize_score_tree_report(report: ScoreTreeReport) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    for section_report in report.sections:
        sections.append(_section_report_to_dict(section_report))

    return {
        "piece_id": report.piece_id,
        "title": report.title,
        "form_family": report.form_family,
        "form_class": report.form_class,
        "composition_mode": report.composition_mode,
        "ending_family": report.ending_family,
        "planned_duration_s": report.planned_duration_s,
        "section_count": report.section_count,
        "motif_count": report.motif_count,
        "phrase_count": report.phrase_count,
        "motif_lifecycle_counts": dict(report.motif_lifecycle_counts),
        "unreferenced_motif_ids": list(report.unreferenced_motif_ids),
        "sections": sections,
    }
