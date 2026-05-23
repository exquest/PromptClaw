"""Tests for the section-boundary crossfade scheduler (T-049)."""

from __future__ import annotations

import pytest

from cypherclaw.instrument_morph import (
    SectionCrossfade,
    SectionTiming,
    schedule_section_crossfades,
)


def test_two_section_arc_overlap_matches_crossfade_duration() -> None:
    sections = (
        SectionTiming(section_id="A", start=0.0, duration=8.0),
        SectionTiming(section_id="B", start=8.0, duration=6.0),
    )

    fades = schedule_section_crossfades(sections, crossfade_duration=1.5)

    assert len(fades) == 1
    fade = fades[0]
    assert isinstance(fade, SectionCrossfade)
    assert fade.section_id == "A"
    assert fade.next_section_id == "B"
    assert fade.release_start == pytest.approx(8.0)
    assert fade.release_end == pytest.approx(9.5)
    assert fade.overlap_start == pytest.approx(8.0)
    assert fade.overlap_end == pytest.approx(9.5)
    assert fade.overlap_duration == pytest.approx(1.5)
    assert fade.release_end - fade.release_start == pytest.approx(1.5)


def test_multi_section_arc_returns_one_fade_per_boundary() -> None:
    sections = (
        SectionTiming(section_id="A", start=0.0, duration=4.0),
        SectionTiming(section_id="B", start=4.0, duration=3.0),
        SectionTiming(section_id="C", start=7.0, duration=5.0),
    )

    fades = schedule_section_crossfades(sections, crossfade_duration=0.75)

    assert [fade.section_id for fade in fades] == ["A", "B"]
    assert [fade.next_section_id for fade in fades] == ["B", "C"]
    for fade in fades:
        assert fade.overlap_duration == pytest.approx(0.75)


def test_zero_crossfade_duration_produces_zero_overlap() -> None:
    sections = (
        SectionTiming(section_id="A", start=0.0, duration=2.0),
        SectionTiming(section_id="B", start=2.0, duration=2.0),
    )

    fades = schedule_section_crossfades(sections, crossfade_duration=0.0)

    assert len(fades) == 1
    assert fades[0].overlap_duration == pytest.approx(0.0)
    assert fades[0].release_end == pytest.approx(fades[0].release_start)


def test_single_or_empty_section_yields_no_fades() -> None:
    assert schedule_section_crossfades((), crossfade_duration=0.5) == ()
    sections = (SectionTiming(section_id="A", start=0.0, duration=4.0),)
    assert schedule_section_crossfades(sections, crossfade_duration=0.5) == ()


def test_non_contiguous_sections_are_rejected() -> None:
    sections = (
        SectionTiming(section_id="A", start=0.0, duration=4.0),
        SectionTiming(section_id="B", start=5.0, duration=4.0),
    )
    with pytest.raises(ValueError):
        schedule_section_crossfades(sections, crossfade_duration=0.5)


def test_crossfade_longer_than_section_is_rejected() -> None:
    sections = (
        SectionTiming(section_id="A", start=0.0, duration=1.0),
        SectionTiming(section_id="B", start=1.0, duration=4.0),
    )
    with pytest.raises(ValueError):
        schedule_section_crossfades(sections, crossfade_duration=2.0)


@pytest.mark.parametrize("bad", [-0.1, float("nan"), float("inf")])
def test_invalid_crossfade_duration_is_rejected(bad: float) -> None:
    sections = (
        SectionTiming(section_id="A", start=0.0, duration=4.0),
        SectionTiming(section_id="B", start=4.0, duration=4.0),
    )
    with pytest.raises(ValueError):
        schedule_section_crossfades(sections, crossfade_duration=bad)
