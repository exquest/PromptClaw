"""Pydantic schemas for composer API requests."""

from __future__ import annotations

from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from cypherclaw.instrument_morph import (
    MorphInterpolationCurve,
    morph_curve_position,
    normalize_morph_interpolation_curve,
)
from cypherclaw.space_reverb import VOICE_REVERB_PROFILES


class MorphCurveType(str, Enum):
    """Supported morph crossfade laws for ``morph_voice``."""

    LINEAR = "linear"
    EQUAL_POWER = "equal-power"


SUPPORTED_MORPH_VOICES: tuple[str, ...] = tuple(VOICE_REVERB_PROFILES)
SUPPORTED_MORPH_CURVE_TYPES: tuple[str, ...] = tuple(
    curve.value for curve in MorphCurveType
)
SUPPORTED_PHRASE_CURVES: tuple[str, ...] = tuple(
    curve.value for curve in MorphInterpolationCurve
)
MORPH_CURVE_VALUE_BY_TYPE: dict[MorphCurveType, int] = {
    MorphCurveType.LINEAR: 0,
    MorphCurveType.EQUAL_POWER: 1,
}
MorphControlArg = str | int | float


class MorphPhraseRequest(BaseModel):
    """POST /api/v1/composer/morph-phrase body."""

    model_config = ConfigDict(extra="forbid")

    source_voice: str = Field(min_length=1)
    target_voice: str = Field(min_length=1)
    morph_curve_type: MorphCurveType
    phrase_curve: MorphInterpolationCurve | None = None
    phrase_frame_count: int = Field(default=5, ge=2)

    @field_validator("source_voice", "target_voice", mode="before")
    @classmethod
    def normalize_voice(cls, value: object, info: ValidationInfo) -> str:
        """Normalize a composer voice name to the canonical profile key."""

        voice = str(value or "").strip().lower()
        if voice.startswith("sw_"):
            voice = voice[3:]
        if not voice:
            raise ValueError(f"{info.field_name} must not be empty")
        if voice not in VOICE_REVERB_PROFILES:
            raise ValueError(
                f"{info.field_name} must be one of {SUPPORTED_MORPH_VOICES!r}, "
                f"got {value!r}"
            )
        return voice

    @field_validator("morph_curve_type", mode="before")
    @classmethod
    def normalize_morph_curve_type(cls, value: object) -> str:
        """Normalize curve aliases to the SynthDef's canonical curve types."""

        raw = getattr(value, "value", value)
        curve = str(raw or "").strip().lower().replace("_", "-").replace(" ", "-")
        if curve == MorphCurveType.EQUAL_POWER.value:
            return MorphCurveType.EQUAL_POWER.value
        if curve == MorphCurveType.LINEAR.value:
            return MorphCurveType.LINEAR.value
        raise ValueError(
            "morph_curve_type must be one of "
            f"{SUPPORTED_MORPH_CURVE_TYPES!r}, got {value!r}"
        )

    @field_validator("phrase_curve", mode="before")
    @classmethod
    def normalize_phrase_curve(cls, value: object) -> str | None:
        """Normalize composer-side phrase progression curve aliases."""

        if value is None:
            return None
        raw = getattr(value, "value", value)
        return normalize_morph_interpolation_curve(str(raw)).value

    @model_validator(mode="after")
    def validate_distinct_voices(self) -> Self:
        """Reject morphs that do not move between two different voices."""

        if self.source_voice == self.target_voice:
            raise ValueError("source_voice and target_voice must differ")
        return self

    @model_validator(mode="after")
    def validate_generation_fields(self) -> Self:
        """Reject generation-only fields when generation was not requested."""

        if self.phrase_curve is None and "phrase_frame_count" in self.model_fields_set:
            raise ValueError("phrase_frame_count requires phrase_curve")
        return self

    @property
    def morph_curve_value(self) -> int:
        """Return the numeric SuperCollider ``morph_curve`` value."""

        return MORPH_CURVE_VALUE_BY_TYPE[self.morph_curve_type]


class MorphPhraseResponse(BaseModel):
    """Accepted normalized morph phrase request."""

    model_config = ConfigDict(extra="ignore")

    accepted: bool = True
    source_voice: str
    target_voice: str
    morph_curve_type: MorphCurveType
    morph_curve_value: int
    synthdef_name: str = "morph_voice"


class SingleLineMorphFrame(BaseModel):
    """One endpoint-inclusive composer frame for a morph phrase."""

    model_config = ConfigDict(extra="forbid")

    frame_index: int
    position: float
    morph_x: float
    synthdef_name: str = "morph_voice"
    control_args: tuple[MorphControlArg, ...]


class SingleLineMorphPhrase(BaseModel):
    """Generated single-line morph phrase for later OSC scheduling."""

    model_config = ConfigDict(extra="forbid")

    source_voice: str
    target_voice: str
    phrase_curve: MorphInterpolationCurve
    frame_count: int
    morph_curve_value: int
    synthdef_name: str = "morph_voice"
    frames: tuple[SingleLineMorphFrame, ...]


class GeneratedMorphPhraseResponse(MorphPhraseResponse):
    """Accepted morph phrase request with generated composer frames."""

    single_line_phrase: SingleLineMorphPhrase


def build_morph_phrase_response(request: MorphPhraseRequest) -> MorphPhraseResponse:
    """Build the JSON-safe response for a validated morph phrase request."""

    return MorphPhraseResponse(
        source_voice=request.source_voice,
        target_voice=request.target_voice,
        morph_curve_type=request.morph_curve_type,
        morph_curve_value=request.morph_curve_value,
    )


def build_single_line_morph_phrase(
    request: MorphPhraseRequest,
) -> SingleLineMorphPhrase:
    """Generate an endpoint-inclusive morph phrase from a validated request."""

    phrase_curve = request.phrase_curve or MorphInterpolationCurve.LINEAR
    last_index = request.phrase_frame_count - 1
    frames: list[SingleLineMorphFrame] = []
    for index in range(request.phrase_frame_count):
        position = index / last_index
        morph_x = morph_curve_position(position, phrase_curve)
        frames.append(
            SingleLineMorphFrame(
                frame_index=index,
                position=position,
                morph_x=morph_x,
                control_args=(
                    "morph_x",
                    morph_x,
                    "morph_curve",
                    request.morph_curve_value,
                ),
            )
        )
    return SingleLineMorphPhrase(
        source_voice=request.source_voice,
        target_voice=request.target_voice,
        phrase_curve=phrase_curve,
        frame_count=request.phrase_frame_count,
        morph_curve_value=request.morph_curve_value,
        frames=tuple(frames),
    )


def build_generated_morph_phrase_response(
    request: MorphPhraseRequest,
) -> GeneratedMorphPhraseResponse:
    """Build a response containing a generated single-line morph phrase."""

    return GeneratedMorphPhraseResponse(
        source_voice=request.source_voice,
        target_voice=request.target_voice,
        morph_curve_type=request.morph_curve_type,
        morph_curve_value=request.morph_curve_value,
        single_line_phrase=build_single_line_morph_phrase(request),
    )


__all__ = [
    "GeneratedMorphPhraseResponse",
    "MORPH_CURVE_VALUE_BY_TYPE",
    "SUPPORTED_MORPH_CURVE_TYPES",
    "SUPPORTED_MORPH_VOICES",
    "SUPPORTED_PHRASE_CURVES",
    "MorphCurveType",
    "MorphPhraseRequest",
    "MorphPhraseResponse",
    "SingleLineMorphFrame",
    "SingleLineMorphPhrase",
    "build_generated_morph_phrase_response",
    "build_morph_phrase_response",
    "build_single_line_morph_phrase",
]
