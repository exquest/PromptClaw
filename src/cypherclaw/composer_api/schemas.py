"""Pydantic schemas for composer API requests."""

from __future__ import annotations

from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from cypherclaw.space_reverb import VOICE_REVERB_PROFILES


class MorphCurveType(str, Enum):
    """Supported morph crossfade laws for ``morph_voice``."""

    LINEAR = "linear"
    EQUAL_POWER = "equal-power"


SUPPORTED_MORPH_VOICES: tuple[str, ...] = tuple(VOICE_REVERB_PROFILES)
SUPPORTED_MORPH_CURVE_TYPES: tuple[str, ...] = tuple(
    curve.value for curve in MorphCurveType
)
MORPH_CURVE_VALUE_BY_TYPE: dict[MorphCurveType, int] = {
    MorphCurveType.LINEAR: 0,
    MorphCurveType.EQUAL_POWER: 1,
}


class MorphPhraseRequest(BaseModel):
    """POST /api/v1/composer/morph-phrase body."""

    model_config = ConfigDict(extra="forbid")

    source_voice: str = Field(min_length=1)
    target_voice: str = Field(min_length=1)
    morph_curve_type: MorphCurveType

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

    @model_validator(mode="after")
    def validate_distinct_voices(self) -> Self:
        """Reject morphs that do not move between two different voices."""

        if self.source_voice == self.target_voice:
            raise ValueError("source_voice and target_voice must differ")
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


def build_morph_phrase_response(request: MorphPhraseRequest) -> MorphPhraseResponse:
    """Build the JSON-safe response for a validated morph phrase request."""

    return MorphPhraseResponse(
        source_voice=request.source_voice,
        target_voice=request.target_voice,
        morph_curve_type=request.morph_curve_type,
        morph_curve_value=request.morph_curve_value,
    )


__all__ = [
    "MORPH_CURVE_VALUE_BY_TYPE",
    "SUPPORTED_MORPH_CURVE_TYPES",
    "SUPPORTED_MORPH_VOICES",
    "MorphCurveType",
    "MorphPhraseRequest",
    "MorphPhraseResponse",
    "build_morph_phrase_response",
]
