"""Section-boundary crossfade scheduler for instrument morph sections."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SectionTiming:
    """Absolute timing for one section on the arc."""

    section_id: str
    start: float
    duration: float

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass(frozen=True)
class SectionCrossfade:
    """Release-tail / attack overlap between two adjacent sections."""

    section_id: str
    next_section_id: str
    release_start: float
    release_end: float
    overlap_start: float
    overlap_end: float

    @property
    def overlap_duration(self) -> float:
        return self.overlap_end - self.overlap_start


def schedule_section_crossfades(
    sections: Sequence[SectionTiming] | Iterable[SectionTiming],
    *,
    crossfade_duration: float,
) -> tuple[SectionCrossfade, ...]:
    """Return release-tail windows that overlap each new section's attack.

    Each released section's tail extends past its nominal end by
    ``crossfade_duration`` seconds; the following section's attack begins at
    the prior section's nominal end, so the per-boundary overlap window is
    exactly ``crossfade_duration``.
    """

    timeline = tuple(sections)
    if not _is_finite_non_negative(crossfade_duration):
        raise ValueError(
            f"crossfade_duration must be a finite non-negative number, "
            f"got {crossfade_duration!r}"
        )
    if len(timeline) < 2:
        return ()

    fades: list[SectionCrossfade] = []
    for current, following in zip(timeline, timeline[1:]):
        if not math.isclose(current.end, following.start, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                f"section {following.section_id!r} must start at the end of "
                f"section {current.section_id!r} ({current.end}), "
                f"got {following.start}"
            )
        if crossfade_duration > current.duration:
            raise ValueError(
                f"crossfade_duration {crossfade_duration} exceeds "
                f"section {current.section_id!r} duration {current.duration}"
            )
        if crossfade_duration > following.duration:
            raise ValueError(
                f"crossfade_duration {crossfade_duration} exceeds "
                f"section {following.section_id!r} duration {following.duration}"
            )
        release_start = current.end
        release_end = current.end + crossfade_duration
        overlap_start = following.start
        overlap_end = following.start + crossfade_duration
        fades.append(
            SectionCrossfade(
                section_id=current.section_id,
                next_section_id=following.section_id,
                release_start=release_start,
                release_end=release_end,
                overlap_start=overlap_start,
                overlap_end=overlap_end,
            )
        )
    return tuple(fades)


def _is_finite_non_negative(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    return math.isfinite(number) and number >= 0.0


__all__ = [
    "SectionCrossfade",
    "SectionTiming",
    "schedule_section_crossfades",
]
