"""End-to-end pipeline tests for the instrument morph stack (T-052).

Exercises scheduling, curve shaping, and OSC arg construction together so the
contract between the three modules is regression-protected. The composer
schedules section crossfades, shapes morph_x through a phrase curve, and ships
the result to scsynth as `/n_set <node_id> morph_x <value> morph_curve <law>`
arg lists (see ``SingleLineMorphFrame.control_args``); this file pins those
seams in one place.
"""

from __future__ import annotations

import pytest

from cypherclaw.composer_api.schemas import (
    MorphCurveType,
    MorphPhraseRequest,
    build_single_line_morph_phrase,
)
from cypherclaw.instrument_morph import (
    MorphInterpolationCurve,
    SectionTiming,
    build_morph_parameter_frames,
    morph_curve_position,
    schedule_section_crossfades,
)


_MORPH_VOICE_NODE_ID = 1101
_OSC_CONTROL_ADDRESS = "/n_set"


def _morph_n_set_args(
    node_id: int,
    morph_x: float,
    morph_curve_value: int,
) -> tuple[object, ...]:
    """Return the `/n_set` arg tuple the composer would ship to scsynth."""

    return (node_id, "morph_x", float(morph_x), "morph_curve", int(morph_curve_value))


def test_section_crossfades_and_morph_frames_share_a_single_timeline() -> None:
    """A scheduled crossfade boundary maps onto a frame in each adjacent phrase."""

    sections = (
        SectionTiming(section_id="A", start=0.0, duration=4.0),
        SectionTiming(section_id="B", start=4.0, duration=4.0),
    )

    fades = schedule_section_crossfades(sections, crossfade_duration=1.0)

    assert len(fades) == 1
    boundary = fades[0]
    assert boundary.section_id == "A"
    assert boundary.next_section_id == "B"
    assert boundary.overlap_duration == pytest.approx(1.0)

    a_frames = build_morph_parameter_frames(
        {"morph_x": 0.0},
        {"morph_x": 1.0},
        frame_count=5,
        curve="linear",
    )
    b_frames = build_morph_parameter_frames(
        {"morph_x": 1.0},
        {"morph_x": 0.0},
        frame_count=5,
        curve="linear",
    )

    assert a_frames[-1].parameters == {"morph_x": pytest.approx(1.0)}
    assert b_frames[0].parameters == {"morph_x": pytest.approx(1.0)}
    assert a_frames[-1].position == pytest.approx(1.0)
    assert b_frames[0].position == pytest.approx(0.0)


@pytest.mark.parametrize(
    "phrase_curve",
    [curve.value for curve in MorphInterpolationCurve],
)
def test_osc_arg_stream_morph_x_follows_phrase_curve(phrase_curve: str) -> None:
    """The OSC `/n_set` morph_x values trace the requested phrase curve."""

    request = MorphPhraseRequest(
        source_voice="pluck",
        target_voice="bowed",
        morph_curve_type=MorphCurveType.EQUAL_POWER,
        phrase_curve=phrase_curve,
        phrase_frame_count=5,
    )
    phrase = build_single_line_morph_phrase(request)

    osc_messages = [
        (_OSC_CONTROL_ADDRESS,)
        + _morph_n_set_args(
            _MORPH_VOICE_NODE_ID,
            frame.morph_x,
            phrase.morph_curve_value,
        )
        for frame in phrase.frames
    ]

    assert [msg[0] for msg in osc_messages] == [_OSC_CONTROL_ADDRESS] * 5
    assert [msg[1] for msg in osc_messages] == [_MORPH_VOICE_NODE_ID] * 5

    # The morph_curve law is constant across the phrase: scsynth only needs
    # the gain-law selector set once, but the composer ships it every frame
    # so late subscribers stay in sync.
    assert {msg[5] for msg in osc_messages} == {1}

    morph_x_stream = [msg[3] for msg in osc_messages]
    expected_positions = [0.0, 0.25, 0.5, 0.75, 1.0]
    assert morph_x_stream == pytest.approx(
        [morph_curve_position(position, phrase_curve) for position in expected_positions]
    )
    assert morph_x_stream[0] == 0.0
    assert morph_x_stream[-1] == 1.0
    for earlier, later in zip(morph_x_stream, morph_x_stream[1:]):
        assert later >= earlier - 1e-12


def test_osc_arg_stream_endpoints_align_across_crossfade_boundary() -> None:
    """Adjacent phrase OSC streams meet at morph_x = 1.0 / 0.0 on a fade boundary."""

    sections = (
        SectionTiming(section_id="A", start=0.0, duration=6.0),
        SectionTiming(section_id="B", start=6.0, duration=6.0),
    )
    fades = schedule_section_crossfades(sections, crossfade_duration=2.0)
    assert len(fades) == 1
    assert fades[0].overlap_duration == pytest.approx(2.0)

    forward = build_single_line_morph_phrase(
        MorphPhraseRequest(
            source_voice="pluck",
            target_voice="bowed",
            morph_curve_type=MorphCurveType.EQUAL_POWER,
            phrase_curve=MorphInterpolationCurve.LINEAR,
            phrase_frame_count=5,
        )
    )
    reverse = build_single_line_morph_phrase(
        MorphPhraseRequest(
            source_voice="bowed",
            target_voice="pluck",
            morph_curve_type=MorphCurveType.EQUAL_POWER,
            phrase_curve=MorphInterpolationCurve.LINEAR,
            phrase_frame_count=5,
        )
    )

    last_a = _morph_n_set_args(
        _MORPH_VOICE_NODE_ID, forward.frames[-1].morph_x, forward.morph_curve_value
    )
    first_b = _morph_n_set_args(
        _MORPH_VOICE_NODE_ID + 1, reverse.frames[0].morph_x, reverse.morph_curve_value
    )

    assert last_a[2] == pytest.approx(1.0)
    assert first_b[2] == pytest.approx(0.0)
    # The morph_curve law (equal-power = 1) carries identically across the
    # boundary so the perceived crossfade stays musical.
    assert last_a[4] == first_b[4] == 1


def test_equal_power_curve_law_threads_into_osc_arg_stream() -> None:
    """The crossfade law value the composer chose reaches every OSC frame."""

    for curve_type, expected_value in (
        (MorphCurveType.LINEAR, 0),
        (MorphCurveType.EQUAL_POWER, 1),
    ):
        phrase = build_single_line_morph_phrase(
            MorphPhraseRequest(
                source_voice="pluck",
                target_voice="bowed",
                morph_curve_type=curve_type,
                phrase_curve=MorphInterpolationCurve.LINEAR,
                phrase_frame_count=3,
            )
        )
        for frame in phrase.frames:
            args = _morph_n_set_args(
                _MORPH_VOICE_NODE_ID, frame.morph_x, phrase.morph_curve_value
            )
            assert args[3] == "morph_curve"
            assert args[4] == expected_value
