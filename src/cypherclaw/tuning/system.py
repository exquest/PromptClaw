"""Tuning systems for CypherClaw composer pitch tables.

Defines a `TuningSystem` abstract base and three concrete implementations:
`TwelveTET`, `JustIntonation5Limit`, and `GamelanSlendro`. Each class produces a
pitch table (scale_degree -> Hz) anchored on a tonal center in Hertz.

The pitch tables described here back the higher-level `pitch_hz` and
`MorphOperator` pipeline (see T-034 / T-035 in `prd-cypherclaw-v2-2026-05-22.md`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass


_JI_5_LIMIT_RATIOS: tuple[float, ...] = (
    1.0,
    16.0 / 15.0,
    9.0 / 8.0,
    6.0 / 5.0,
    5.0 / 4.0,
    4.0 / 3.0,
    45.0 / 32.0,
    3.0 / 2.0,
    8.0 / 5.0,
    5.0 / 3.0,
    9.0 / 5.0,
    15.0 / 8.0,
)

# Cumulative cents above the tonal center for the 5 slendro steps within an
# octave, per the PRD's approximation of ~240, 240, 270, 240, 270 cents.
_SLENDRO_STEP_CENTS: tuple[float, ...] = (0.0, 240.0, 480.0, 750.0, 990.0)


class TuningSystem(ABC):
    """Abstract base for a scale-degree -> Hz pitch table generator."""

    name: str
    degrees_per_octave: int

    @abstractmethod
    def pitch_table(self, tonal_center_hz: float) -> dict[int, float]:
        """Return scale-degree -> Hz mapping for one octave at the tonal center.

        Keys are integer scale degrees starting at 0. Degree 0 is the tonal
        center itself.
        """


@dataclass(frozen=True)
class TwelveTET(TuningSystem):
    """12-tone equal temperament: 12 semitones of 100 cents each."""

    name: str = "twelve_tet"
    degrees_per_octave: int = 12

    def pitch_table(self, tonal_center_hz: float) -> dict[int, float]:
        center = _validated_center(tonal_center_hz)
        return {
            degree: center * (2.0 ** (degree / 12.0))
            for degree in range(self.degrees_per_octave)
        }


@dataclass(frozen=True)
class JustIntonation5Limit(TuningSystem):
    """5-limit just intonation chromatic scale anchored on the tonal center."""

    name: str = "just_intonation_5_limit"
    degrees_per_octave: int = 12

    def pitch_table(self, tonal_center_hz: float) -> dict[int, float]:
        center = _validated_center(tonal_center_hz)
        return {
            degree: center * _JI_5_LIMIT_RATIOS[degree]
            for degree in range(self.degrees_per_octave)
        }


@dataclass(frozen=True)
class GamelanSlendro(TuningSystem):
    """5-tone Javanese gamelan slendro scale (asymmetric ~240/240/270/240/270 c)."""

    name: str = "gamelan_slendro"
    degrees_per_octave: int = 5

    def pitch_table(self, tonal_center_hz: float) -> dict[int, float]:
        center = _validated_center(tonal_center_hz)
        return {
            degree: center * (2.0 ** (_SLENDRO_STEP_CENTS[degree] / 1200.0))
            for degree in range(self.degrees_per_octave)
        }


def _validated_center(tonal_center_hz: float) -> float:
    center = float(tonal_center_hz)
    if center <= 0.0:
        raise ValueError("tonal_center_hz must be positive")
    return center


SUPPORTED_TUNINGS: Mapping[str, type[TuningSystem]] = {
    TwelveTET().name: TwelveTET,
    JustIntonation5Limit().name: JustIntonation5Limit,
    GamelanSlendro().name: GamelanSlendro,
}


# Legacy scene metadata may use the historical "12-TET" label (and related
# variants) for equal temperament. Map those to TwelveTET so old scenes keep
# playing unchanged through the new pitch pipeline (T-037).
_TUNING_ALIASES: Mapping[str, type[TuningSystem]] = {
    "12_tet": TwelveTET,
    "12tet": TwelveTET,
    "twelve_tet": TwelveTET,
    "equal_temperament": TwelveTET,
    "just": JustIntonation5Limit,
    "just_intonation": JustIntonation5Limit,
    "just_intonation_5_limit": JustIntonation5Limit,
    "5_limit_ji": JustIntonation5Limit,
    "slendro": GamelanSlendro,
    "gamelan_slendro": GamelanSlendro,
}


def tuning_for_name(name: str) -> TuningSystem:
    """Resolve a tuning-system name (including legacy aliases) to an instance.

    Accepts the canonical names in `SUPPORTED_TUNINGS` as well as legacy labels
    such as ``"12-TET"`` carried in older scene metadata. Comparison is
    case-insensitive and dashes/spaces are folded to underscores.
    """

    key = str(name).strip().lower().replace("-", "_").replace(" ", "_")
    cls = _TUNING_ALIASES.get(key) or SUPPORTED_TUNINGS.get(key)
    if cls is None:
        raise ValueError(f"unknown tuning_system_name: {name!r}")
    return cls()
