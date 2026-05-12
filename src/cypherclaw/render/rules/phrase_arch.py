from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, cast

from cypherclaw.render.events import Event
from cypherclaw.render.role_gate import role_is_eligible


MIN_TEMPO_MULT = 0.85
MAX_TEMPO_MULT = 1.15
ARC_SHAPES: Final[tuple[str, ...]] = (
    "parabolic",
    "cosine",
    "asymmetric-Bezier",
    "flat",
    "inverted",
)
DEFAULT_INTENT_TAG: Final[str] = "statement"
MIN_RANDOM_PEAK: Final[float] = 0.35
MAX_RANDOM_PEAK: Final[float] = 0.75
PEAK_VARIANCE: Final[float] = 0.15

ARC_SHAPE_DISTRIBUTIONS: Final[dict[str, tuple[tuple[str, float], ...]]] = {
    "statement": (
        ("parabolic", 5.0),
        ("cosine", 3.0),
        ("asymmetric-Bezier", 2.0),
        ("inverted", 1.0),
    ),
    "development": (
        ("asymmetric-Bezier", 4.0),
        ("cosine", 3.0),
        ("parabolic", 2.0),
        ("inverted", 2.0),
    ),
    "recap": (
        ("cosine", 4.0),
        ("parabolic", 4.0),
        ("asymmetric-Bezier", 2.0),
        ("inverted", 1.0),
    ),
    "withhold": (
        ("asymmetric-Bezier", 3.0),
        ("inverted", 3.0),
        ("cosine", 2.0),
        ("flat", 2.0),
        ("parabolic", 1.0),
    ),
    "release": (
        ("cosine", 4.0),
        ("parabolic", 3.0),
        ("asymmetric-Bezier", 2.0),
        ("inverted", 1.0),
    ),
}


@dataclass(frozen=True)
class _ArcProfile:
    shape: str
    peak: float
    tempo_deviation_pct: float
    amp_deviation_pct: float


@dataclass
class PhraseArchRule:
    tempo_deviation_pct: float = 4.0
    amp_deviation_pct: float = 4.0
    peak: float = 0.6
    k: float = 1.0
    arc_shape: str | None = None
    seed: int | None = 0
    _profiles_by_phrase: dict[object, _ArcProfile] = field(default_factory=dict, init=False, repr=False)
    _rng: random.Random = field(init=False, repr=False)

    rule_id = "R2"

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def applies_to(self, role: str, metadata: Mapping[str, object] | None = None) -> bool:
        return role_is_eligible(role, metadata)

    def _get_base_arch(
        self,
        x: float,
        arc_shape: str | None = None,
        peak: float | None = None,
    ) -> float:
        shape = _normalize_arc_shape(arc_shape) or _normalize_arc_shape(self.arc_shape) or "parabolic"
        peak_position = self.peak if peak is None else peak
        if shape == "parabolic":
            return -4 * (x - peak_position)**2 + 1
        elif shape == "cosine":
            return math.cos((x - peak_position) * math.pi)
        elif shape == "flat":
            return 0.0
        elif shape == "inverted":
            return 4 * (x - peak_position)**2 - 1
        elif shape == "asymmetric-Bezier":
            # Simple asymmetric curve peaking at peak_position.
            if x <= peak_position and peak_position > 0:
                t = x / peak_position
                return 1.0 - (1.0 - t)**2
            elif peak_position < 1:
                t = (x - peak_position) / (1.0 - peak_position)
                return 1.0 - t**2
            return 0.0
        return -4 * (x - peak_position)**2 + 1

    def apply(self, event: Event) -> None:
        if not self.applies_to(event.role, event.metadata):
            return
        x = event.normalized_phrase_position
        profile = self._profile_for_event(event)
        arch_val = self._get_base_arch(x, profile.shape, profile.peak)

        tempo_arch_mult = 1.0 + self.k * arch_val * (profile.tempo_deviation_pct / 100.0)
        amp_arch_mult = 1.0 + self.k * arch_val * (profile.amp_deviation_pct / 100.0)

        section_tempo_base = 1.0
        section_dynamic_plane = 1.0
        if event.section_envelope is not None:
            section_sample = event.section_envelope.sample(event.normalized_section_position)
            section_tempo_base = section_sample.tempo_base
            section_dynamic_plane = section_sample.dynamic_plane

        sensor_tempo_mult = 1.0 + event.sensor_tempo_scale
        event.tempo_mult = min(
            MAX_TEMPO_MULT,
            max(MIN_TEMPO_MULT, section_tempo_base * tempo_arch_mult * sensor_tempo_mult),
        )
        event.amp_mult *= section_dynamic_plane * amp_arch_mult
        event.metadata["phrase_arch_shape"] = profile.shape
        event.metadata["phrase_arch_peak"] = f"{profile.peak:.6f}"
        event.metadata["phrase_arch_tempo_deviation_pct"] = f"{profile.tempo_deviation_pct:.1f}"

    def _profile_for_event(self, event: Event) -> _ArcProfile:
        intent = _performance_intent(event)
        explicit_shape = _normalize_arc_shape(_source_value(intent, ("arc_shape",)))
        explicit_shape = explicit_shape or _normalize_arc_shape(
            _source_value(event.metadata, ("arc_shape",)),
        )

        restraint_val = _coerce_float(_source_value(intent, ("restraint",)))
        if restraint_val is None:
            restraint_val = _coerce_float(_source_value(event.metadata, ("restraint",)))
        restraint = min(1.0, max(0.0, restraint_val or 0.0))

        if explicit_shape is None and self.arc_shape is not None:
            shape = _normalize_arc_shape(self.arc_shape) or "parabolic"
            return _ArcProfile(
                shape,
                self.peak,
                self.tempo_deviation_pct * (1.0 - restraint),
                self.amp_deviation_pct * (1.0 - restraint * 0.7)
            )

        phrase_key = _phrase_key(event)
        if phrase_key is not None and phrase_key in self._profiles_by_phrase:
            return self._profiles_by_phrase[phrase_key]

        shape = explicit_shape or self._sample_shape(_intent_tag(event, intent))
        peak = _coerce_peak(_source_value(intent, ("peak", "arc_peak", "peak_position")))
        if peak is None:
            peak = _coerce_peak(_source_value(event.metadata, ("peak", "arc_peak", "peak_position")))
        if peak is None:
            peak = self._sample_peak()

        if shape == "flat":
            tempo_deviation_pct = 0.0
            amp_deviation_pct = 0.0
        else:
            tempo_deviation_pct = self.tempo_deviation_pct * (1.0 - restraint)
            amp_deviation_pct = self.amp_deviation_pct * (1.0 - restraint * 0.7)

        profile = _ArcProfile(shape, peak, tempo_deviation_pct, amp_deviation_pct)
        if phrase_key is not None:
            self._profiles_by_phrase[phrase_key] = profile
        return profile

    def _sample_shape(self, intent_tag: str) -> str:
        distribution = ARC_SHAPE_DISTRIBUTIONS.get(
            intent_tag,
            ARC_SHAPE_DISTRIBUTIONS[DEFAULT_INTENT_TAG],
        )
        shapes = tuple(shape for shape, _ in distribution)
        weights = tuple(weight for _, weight in distribution)
        return self._rng.choices(shapes, weights=weights, k=1)[0]

    def _sample_peak(self) -> float:
        peak = self.peak + self._rng.uniform(-PEAK_VARIANCE, PEAK_VARIANCE)
        return min(MAX_RANDOM_PEAK, max(MIN_RANDOM_PEAK, peak))


def _normalize_arc_shape(value: object | None) -> str | None:
    if value is None:
        return None
    shape = str(value).strip()
    if not shape:
        return None
    shape_key = shape.lower().replace("_", "-")
    for authored_shape in ARC_SHAPES:
        if shape_key == authored_shape.lower():
            return authored_shape
    return None


def _performance_intent(event: Event) -> object | None:
    intent = getattr(event, "performance_intent", None)
    if intent is not None:
        return intent

    phrase = getattr(event, "phrase", None)
    intent = getattr(phrase, "performance_intent", None)
    if intent is not None:
        return intent

    metadata_intent = event.metadata.get("performance_intent")
    if isinstance(metadata_intent, Mapping):
        return metadata_intent
    return None


def _intent_tag(event: Event, intent: object | None) -> str:
    for source in (
        intent,
        event.metadata,
        getattr(getattr(event, "phrase", None), "metadata", None),
        getattr(event, "phrase", None),
    ):
        value = _source_value(source, ("intent_tag", "intent_tags"))
        tag = _coerce_intent_tag(value)
        if tag is not None:
            return tag
    return DEFAULT_INTENT_TAG


def _source_value(source: object | None, names: tuple[str, ...]) -> object | None:
    if source is None:
        return None
    if isinstance(source, Mapping):
        for name in names:
            value = source.get(name)
            if value is not None:
                return value
        return None
    for name in names:
        value = getattr(source, name, None)
        if value is not None:
            return value
    return None


def _coerce_intent_tag(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        tags = value.split(",")
        tag = tags[0].strip().strip("[]'\"").lower()
        return tag or None
    if isinstance(value, (list, tuple)) and value:
        return str(value[0]).strip().lower() or None
    return str(value).strip().lower() or None


def _coerce_float(value: object | None) -> float | None:
    if value is None:
        return None
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return None


def _coerce_peak(value: object | None) -> float | None:
    if value is None:
        return None
    try:
        peak = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, peak))


def _phrase_key(event: Event) -> object | None:
    for key in ("phrase_id", "phrase_uid", "phrase_index"):
        value = event.metadata.get(key)
        if value is not None:
            return "metadata", key, value

    phrase = getattr(event, "phrase", None)
    if phrase is None:
        return None
    for attr in ("phrase_id", "id", "uid", "name"):
        value = getattr(phrase, attr, None)
        if value is not None:
            return "phrase", attr, value
    return "phrase", id(phrase)
