"""Canonical score-tree data model for CypherClaw composition."""
from __future__ import annotations

from collections.abc import Sequence
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


def _coerce_string_map(payload: object) -> dict[str, str]:
    if not isinstance(payload, Mapping):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _coerce_polymeter(value: object) -> tuple[int, int] | None:
    if value is None or value == "":
        return None
    raw = value
    if isinstance(value, str):
        try:
            raw = json.loads(value)
        except (TypeError, ValueError):
            raw = value.replace(":", ",").split(",")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None
    if len(raw) != 2:
        return None
    try:
        return (int(raw[0]), int(raw[1]))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class MeterSceneValue:
    """One scene's planned meter value inside a larger trajectory."""

    scene_name: str
    meter: str
    subdivision: str = "straight"
    groove_timing: str = "grid"
    phrase_breath: str = "regular"
    metric_modulation: str = ""
    polymeter: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "scene_name", str(self.scene_name))
        object.__setattr__(self, "meter", str(self.meter))
        object.__setattr__(self, "subdivision", str(self.subdivision or "straight"))
        object.__setattr__(self, "groove_timing", str(self.groove_timing or "grid"))
        object.__setattr__(self, "phrase_breath", str(self.phrase_breath or "regular"))
        object.__setattr__(self, "metric_modulation", str(self.metric_modulation or ""))
        object.__setattr__(self, "polymeter", _coerce_polymeter(self.polymeter))

    def to_metadata_entry(self, *, index: int, scene_count: int) -> dict[str, object]:
        entry: dict[str, object] = {
            "scene_name": self.scene_name,
            "index": index,
            "scene_count": scene_count,
            "meter": self.meter,
            "subdivision": self.subdivision,
            "groove_timing": self.groove_timing,
            "phrase_breath": self.phrase_breath,
        }
        if self.metric_modulation:
            entry["metric_modulation"] = self.metric_modulation
        if self.polymeter is not None:
            entry["polymeter"] = list(self.polymeter)
        return entry


@dataclass(frozen=True)
class MeterTrajectory:
    """Arc-level meter plan spanning multiple score-tree scenes."""

    trajectory_id: str
    arc_plan: str
    scene_values: tuple[MeterSceneValue, ...]
    arc_phase: str = ""
    rationale: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "trajectory_id", str(self.trajectory_id))
        object.__setattr__(self, "arc_plan", str(self.arc_plan))
        object.__setattr__(self, "arc_phase", str(self.arc_phase or ""))
        object.__setattr__(self, "rationale", str(self.rationale or ""))
        object.__setattr__(
            self,
            "scene_values",
            tuple(_coerce_meter_scene_value(value) for value in self.scene_values),
        )

    def scene_value_for(self, scene_name: str) -> MeterSceneValue | None:
        for value in self.scene_values:
            if value.scene_name == scene_name:
                return value
        return None

    def metadata_for_scene(self, scene_name: str) -> dict[str, str]:
        for index, value in enumerate(self.scene_values):
            if value.scene_name != scene_name:
                continue
            metadata = {
                "meter_trajectory_id": self.trajectory_id,
                "meter_trajectory_arc_plan": self.arc_plan,
                "meter_trajectory_scene": value.scene_name,
                "meter_trajectory_index": str(index),
                "meter_trajectory_scene_count": str(len(self.scene_values)),
                "meter_trajectory_meter": value.meter,
                "meter_trajectory_subdivision": value.subdivision,
                "meter_trajectory_groove_timing": value.groove_timing,
                "meter_trajectory_phrase_breath": value.phrase_breath,
                "meter_trajectory_path": json.dumps([item.meter for item in self.scene_values]),
                "meter_trajectory_entry": json.dumps(
                    value.to_metadata_entry(
                        index=index,
                        scene_count=len(self.scene_values),
                    )
                ),
            }
            if self.arc_phase:
                metadata["meter_trajectory_arc_phase"] = self.arc_phase
            if self.rationale:
                metadata["meter_trajectory_rationale"] = self.rationale
            if value.metric_modulation:
                metadata["meter_trajectory_metric_modulation"] = value.metric_modulation
            if value.polymeter is not None:
                metadata["meter_trajectory_polymeter"] = json.dumps(list(value.polymeter))
            return metadata
        return {}


def _metadata_token(value: object) -> str:
    token = str(value or "").strip()
    if not token:
        return "none"
    return "_".join(token.split())


@dataclass(frozen=True)
class TuningSceneValue:
    """One scene's planned tuning value inside a larger trajectory."""

    scene_name: str
    arc_phase: str
    phase_category: str
    tuning_system_name: str
    transition_kind: str = "steady"
    tuning_morph_source_name: str = ""
    tuning_morph_target_name: str = ""
    tuning_morph_curve: str = "linear"

    def __post_init__(self) -> None:
        object.__setattr__(self, "scene_name", str(self.scene_name))
        object.__setattr__(self, "arc_phase", str(self.arc_phase or ""))
        object.__setattr__(self, "phase_category", str(self.phase_category or "legacy"))
        object.__setattr__(self, "tuning_system_name", str(self.tuning_system_name or "twelve_tet"))
        object.__setattr__(self, "transition_kind", str(self.transition_kind or "steady"))
        object.__setattr__(self, "tuning_morph_source_name", str(self.tuning_morph_source_name or ""))
        object.__setattr__(self, "tuning_morph_target_name", str(self.tuning_morph_target_name or ""))
        object.__setattr__(self, "tuning_morph_curve", str(self.tuning_morph_curve or "linear"))

    def to_metadata_entry(self, *, index: int, scene_count: int) -> dict[str, object]:
        return {
            "scene_name": self.scene_name,
            "index": index,
            "scene_count": scene_count,
            "arc_phase": self.arc_phase,
            "phase_category": self.phase_category,
            "tuning_system_name": self.tuning_system_name,
            "transition_kind": self.transition_kind,
            "tuning_morph_source_name": self.tuning_morph_source_name,
            "tuning_morph_target_name": self.tuning_morph_target_name,
            "tuning_morph_curve": self.tuning_morph_curve,
        }

    def composer_log_line(self, *, index: int, scene_count: int) -> str:
        """Return a deterministic operator log line for this tuning selection."""

        return (
            "composer_tuning_selection"
            f" scene={_metadata_token(self.scene_name)}"
            f" index={index + 1}/{scene_count}"
            f" phase={_metadata_token(self.arc_phase)}"
            f" category={_metadata_token(self.phase_category)}"
            f" tuning_system_name={_metadata_token(self.tuning_system_name)}"
            f" morph_source={_metadata_token(self.tuning_morph_source_name)}"
            f" morph_target={_metadata_token(self.tuning_morph_target_name)}"
            f" morph_curve={_metadata_token(self.tuning_morph_curve)}"
            f" transition={_metadata_token(self.transition_kind)}"
        )


@dataclass(frozen=True)
class TuningTrajectory:
    """Arc-level tuning plan spanning multiple score-tree scenes."""

    trajectory_id: str
    arc_plan: str
    scene_values: tuple[TuningSceneValue, ...]
    arc_phase: str = ""
    rationale: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "trajectory_id", str(self.trajectory_id))
        object.__setattr__(self, "arc_plan", str(self.arc_plan))
        object.__setattr__(self, "arc_phase", str(self.arc_phase or ""))
        object.__setattr__(self, "rationale", str(self.rationale or ""))
        object.__setattr__(
            self,
            "scene_values",
            tuple(_coerce_tuning_scene_value(value) for value in self.scene_values),
        )

    def scene_value_for(self, scene_name: str) -> TuningSceneValue | None:
        for value in self.scene_values:
            if value.scene_name == scene_name:
                return value
        return None

    def composer_log_lines(self) -> tuple[str, ...]:
        scene_count = len(self.scene_values)
        return tuple(
            value.composer_log_line(index=index, scene_count=scene_count)
            for index, value in enumerate(self.scene_values)
        )

    def metadata_for_scene(self, scene_name: str) -> dict[str, str]:
        for index, value in enumerate(self.scene_values):
            if value.scene_name != scene_name:
                continue
            metadata = {
                "tuning_trajectory_id": self.trajectory_id,
                "tuning_trajectory_arc_plan": self.arc_plan,
                "tuning_trajectory_scene": value.scene_name,
                "tuning_trajectory_index": str(index),
                "tuning_trajectory_scene_count": str(len(self.scene_values)),
                "tuning_arc_phase": value.arc_phase,
                "tuning_phase_category": value.phase_category,
                "tuning_system_name": value.tuning_system_name,
                "tuning_morph_source_name": value.tuning_morph_source_name,
                "tuning_morph_target_name": value.tuning_morph_target_name,
                "tuning_morph_curve": value.tuning_morph_curve,
                "tuning_transition_kind": value.transition_kind,
                "tuning_trajectory_path": json.dumps(
                    [item.tuning_system_name for item in self.scene_values]
                ),
                "tuning_trajectory_entry": json.dumps(
                    value.to_metadata_entry(
                        index=index,
                        scene_count=len(self.scene_values),
                    )
                ),
            }
            if self.arc_phase:
                metadata["tuning_trajectory_arc_phase"] = self.arc_phase
            if self.rationale:
                metadata["tuning_trajectory_rationale"] = self.rationale
            return metadata
        return {}


def _coerce_tuning_scene_value(payload: object) -> TuningSceneValue:
    if isinstance(payload, TuningSceneValue):
        return payload
    if isinstance(payload, Mapping):
        return TuningSceneValue(
            scene_name=str(payload.get("scene_name", "")),
            arc_phase=str(payload.get("arc_phase", "") or ""),
            phase_category=str(payload.get("phase_category", "legacy") or "legacy"),
            tuning_system_name=str(payload.get("tuning_system_name", "twelve_tet") or "twelve_tet"),
            transition_kind=str(payload.get("transition_kind", "steady") or "steady"),
            tuning_morph_source_name=str(payload.get("tuning_morph_source_name", "") or ""),
            tuning_morph_target_name=str(payload.get("tuning_morph_target_name", "") or ""),
            tuning_morph_curve=str(payload.get("tuning_morph_curve", "linear") or "linear"),
        )
    raise TypeError(f"unsupported TuningSceneValue payload: {type(payload)!r}")


def _coerce_tuning_trajectory(payload: object) -> TuningTrajectory | None:
    if payload is None:
        return None
    if isinstance(payload, TuningTrajectory):
        return payload
    if isinstance(payload, Mapping):
        raw_values = payload.get("scene_values", ())
        if not isinstance(raw_values, Sequence) or isinstance(raw_values, (str, bytes)):
            raw_values = ()
        return TuningTrajectory(
            trajectory_id=str(payload.get("trajectory_id", "")),
            arc_plan=str(payload.get("arc_plan", "")),
            arc_phase=str(payload.get("arc_phase", "") or ""),
            scene_values=tuple(_coerce_tuning_scene_value(value) for value in raw_values),
            rationale=str(payload.get("rationale", "") or ""),
        )
    raise TypeError(f"unsupported TuningTrajectory payload: {type(payload)!r}")


def _coerce_meter_scene_value(payload: object) -> MeterSceneValue:
    if isinstance(payload, MeterSceneValue):
        return payload
    if isinstance(payload, Mapping):
        return MeterSceneValue(
            scene_name=str(payload.get("scene_name", "")),
            meter=str(payload.get("meter", "4/4") or "4/4"),
            subdivision=str(payload.get("subdivision", "straight") or "straight"),
            groove_timing=str(payload.get("groove_timing", "grid") or "grid"),
            phrase_breath=str(payload.get("phrase_breath", "regular") or "regular"),
            metric_modulation=str(payload.get("metric_modulation", "") or ""),
            polymeter=_coerce_polymeter(payload.get("polymeter")),
        )
    raise TypeError(f"unsupported MeterSceneValue payload: {type(payload)!r}")


def _coerce_meter_trajectory(payload: object) -> MeterTrajectory | None:
    if payload is None:
        return None
    if isinstance(payload, MeterTrajectory):
        return payload
    if isinstance(payload, Mapping):
        raw_values = payload.get("scene_values", ())
        if not isinstance(raw_values, Sequence) or isinstance(raw_values, (str, bytes)):
            raw_values = ()
        return MeterTrajectory(
            trajectory_id=str(payload.get("trajectory_id", "")),
            arc_plan=str(payload.get("arc_plan", "")),
            arc_phase=str(payload.get("arc_phase", "") or ""),
            scene_values=tuple(_coerce_meter_scene_value(value) for value in raw_values),
            rationale=str(payload.get("rationale", "") or ""),
        )
    raise TypeError(f"unsupported MeterTrajectory payload: {type(payload)!r}")


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
    scene_metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.section_envelope = _coerce_section_envelope(self.section_envelope)
        self.scene_metadata = _coerce_string_map(self.scene_metadata)


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
    meter_trajectory: MeterTrajectory | None = None
    tuning_trajectory: TuningTrajectory | None = None
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
                scene_metadata=_coerce_string_map(item.get("scene_metadata", {})),
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
            meter_trajectory=_coerce_meter_trajectory(data.get("meter_trajectory")),
            tuning_trajectory=_coerce_tuning_trajectory(data.get("tuning_trajectory")),
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
