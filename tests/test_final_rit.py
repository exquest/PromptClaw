import math
from dataclasses import dataclass

from cypherclaw.render.events import Event
from cypherclaw.render.rules.final_rit import FinalRitRule


@dataclass(frozen=True)
class Phrase:
    is_cadential: bool


def test_final_rit_curve_shape() -> None:
    rule = FinalRitRule()
    phrase = Phrase(is_cadential=True)
    mid_event = Event(normalized_phrase_position=0.875, tempo_mult=1.2, phrase=phrase, role="melody")
    end_event = Event(normalized_phrase_position=1.0, tempo_mult=1.2, phrase=phrase, role="melody")

    rule.apply(mid_event)
    rule.apply(end_event)

    assert math.isclose(mid_event.tempo_mult, 1.2 * math.sqrt(0.825))
    assert math.isclose(end_event.tempo_mult, 1.2 * math.sqrt(0.65))
    assert end_event.tempo_mult < mid_event.tempo_mult


def test_final_rit_default_onset_position() -> None:
    rule = FinalRitRule()
    phrase = Phrase(is_cadential=True)
    before_onset = Event(normalized_phrase_position=0.74, tempo_mult=1.25, phrase=phrase, role="melody")
    at_onset = Event(normalized_phrase_position=0.75, tempo_mult=1.25, phrase=phrase, role="melody")

    rule.apply(before_onset)
    rule.apply(at_onset)

    assert before_onset.tempo_mult == 1.25
    assert at_onset.tempo_mult == 1.25


def test_final_rit_ignores_non_cadential_phrase() -> None:
    rule = FinalRitRule()
    event = Event(
        normalized_phrase_position=1.0,
        tempo_mult=1.25,
        phrase=Phrase(is_cadential=False),
        role="melody",
    )

    rule.apply(event)

    assert event.tempo_mult == 1.25
