import math
from collections import Counter

from cypherclaw.render.events import Event, SectionEnvelope
from cypherclaw.render.rules.phrase_arch import ARC_SHAPES, PhraseArchRule

def test_phrase_arch_parabolic():
    rule = PhraseArchRule(arc_shape="parabolic", peak=0.6, k=1.0, tempo_deviation_pct=4.0)

    # At peak, base_arch should be 1.0
    event = Event(normalized_phrase_position=0.6, role="melody")
    rule.apply(event)
    assert event.tempo_mult == 1.04
    assert event.amp_mult == 1.04

    # At x=0, base_arch = -4*(0-0.6)**2 + 1 = 1 - 4*(0.36) = 1 - 1.44 = -0.44
    # tempo_mult = 1.0 + 1.0 * (-0.44) * 0.04 = 1.0 - 0.0176 = 0.9824
    event2 = Event(normalized_phrase_position=0.0, role="melody")
    rule.apply(event2)
    assert math.isclose(event2.tempo_mult, 0.9824)

def test_phrase_arch_cosine():
    rule = PhraseArchRule(arc_shape="cosine", peak=0.5, k=1.0, tempo_deviation_pct=4.0)
    event = Event(normalized_phrase_position=0.5, role="melody")
    rule.apply(event)
    assert event.tempo_mult == 1.04

    event2 = Event(normalized_phrase_position=0.0, role="melody")
    rule.apply(event2)
    # cos((0-0.5)*pi) = cos(-pi/2) = 0
    assert math.isclose(event2.tempo_mult, 1.0)

def test_phrase_arch_multiplicative_composition():
    rule = PhraseArchRule(arc_shape="parabolic", peak=0.6, k=1.0, tempo_deviation_pct=4.0)
    env = SectionEnvelope(tempo_base=1.05)
    
    event = Event(
        normalized_phrase_position=0.6,
        section_envelope=env,
        sensor_tempo_scale=0.01,
        role="melody",
    )
    rule.apply(event)
    
    # section_tempo_base = 1.05
    # tempo_arch_mult = 1.04
    # sensor_tempo_mult = 1.01
    # expected: 1.05 * 1.04 * 1.01 = 1.10292
    assert math.isclose(event.tempo_mult, 1.10292)


def test_phrase_arch_composes_with_section_envelope_sample():
    rule = PhraseArchRule(
        arc_shape="parabolic",
        peak=0.6,
        k=1.0,
        tempo_deviation_pct=4.0,
        amp_deviation_pct=4.0,
    )
    env = SectionEnvelope(
        tempo_base=((0.0, 1.0), (1.0, 1.1)),
        dynamic_plane=((0.0, 0.8), (1.0, 1.0)),
    )

    event = Event(
        normalized_phrase_position=0.6,
        normalized_section_position=0.5,
        section_envelope=env,
        role="melody",
    )
    rule.apply(event)

    assert math.isclose(event.tempo_mult, 1.05 * 1.04)
    assert math.isclose(event.amp_mult, 0.9 * 1.04)

def test_phrase_arch_clamps_composed_tempo():
    rule = PhraseArchRule(arc_shape="parabolic", peak=0.6, k=1.0, tempo_deviation_pct=4.0)
    high_env = SectionEnvelope(tempo_base=1.1)

    high_event = Event(
        normalized_phrase_position=0.6,
        section_envelope=high_env,
        sensor_tempo_scale=0.08,
        role="melody",
    )
    rule.apply(high_event)

    # section_tempo_base = 1.1
    # tempo_arch_mult = 1.04
    # sensor_tempo_mult = 1.08
    # expected: 1.1 * 1.04 * 1.08 = 1.23552, clamped to 1.15
    assert high_event.tempo_mult == 1.15

    low_env = SectionEnvelope(tempo_base=0.9)
    low_event = Event(
        normalized_phrase_position=0.0,
        section_envelope=low_env,
        sensor_tempo_scale=-0.08,
        role="melody",
    )
    rule.apply(low_event)

    assert low_event.tempo_mult == 0.85

def test_phrase_arch_variants():
    # Just verify they don't crash and return reasonable values at peak
    shapes = ["parabolic", "cosine", "flat", "inverted", "asymmetric-Bezier"]
    for shape in shapes:
        rule = PhraseArchRule(arc_shape=shape, peak=0.6, k=1.0)
        event = Event(normalized_phrase_position=0.6, role="melody")
        rule.apply(event)
        if shape == "flat":
            assert event.tempo_mult == 1.0
        elif shape == "inverted":
            assert event.tempo_mult < 1.0
        else:
            assert event.tempo_mult > 1.0


def test_phrase_arch_uses_performance_intent_arc_shape():
    rule = PhraseArchRule(seed=1)
    event = Event(
        normalized_phrase_position=0.5,
        role="melody",
        metadata={"phrase_id": "intent-arc"},
    )
    event.performance_intent = {  # type: ignore[attr-defined]
        "arc_shape": "cosine",
        "intent_tag": "withhold",
        "peak": 0.5,
    }

    rule.apply(event)

    assert event.metadata["phrase_arch_shape"] == "cosine"
    assert event.metadata["phrase_arch_peak"] == "0.500000"
    assert event.tempo_mult == 1.04


def test_phrase_arch_samples_intent_weighted_shapes_over_many_phrases():
    statement_counts = _sample_shapes("statement")
    withhold_counts = _sample_shapes("withhold")

    assert set(withhold_counts) == set(ARC_SHAPES)
    assert len(statement_counts) >= 3
    assert withhold_counts["flat"] > statement_counts["flat"]
    assert withhold_counts["inverted"] > statement_counts["inverted"]


def test_phrase_arch_withhold_flat_arc_has_zero_tempo_deviation():
    rule = PhraseArchRule(seed=11)
    flat_event = None
    for index in range(100):
        event = Event(
            normalized_phrase_position=0.5,
            role="melody",
            metadata={"phrase_id": f"withhold-{index}", "intent_tag": "withhold"},
        )
        rule.apply(event)
        if event.metadata["phrase_arch_shape"] == "flat":
            flat_event = event
            break

    assert flat_event is not None
    assert flat_event.metadata["phrase_arch_tempo_deviation_pct"] == "0.0"
    assert flat_event.tempo_mult == 1.0


def test_phrase_arch_samples_peak_once_per_phrase():
    rule = PhraseArchRule(seed=17)
    first = Event(
        normalized_phrase_position=0.25,
        role="melody",
        metadata={"phrase_id": "shared", "intent_tag": "development"},
    )
    second = Event(
        normalized_phrase_position=0.75,
        role="melody",
        metadata={"phrase_id": "shared", "intent_tag": "development"},
    )

    rule.apply(first)
    rule.apply(second)

    assert second.metadata["phrase_arch_shape"] == first.metadata["phrase_arch_shape"]
    assert second.metadata["phrase_arch_peak"] == first.metadata["phrase_arch_peak"]


def _sample_shapes(intent_tag: str) -> Counter[str]:
    rule = PhraseArchRule(seed=7)
    counts: Counter[str] = Counter()
    for index in range(400):
        event = Event(
            normalized_phrase_position=0.5,
            role="melody",
            metadata={"phrase_id": f"{intent_tag}-{index}", "intent_tag": intent_tag},
        )
        rule.apply(event)
        counts[event.metadata["phrase_arch_shape"]] += 1
    return counts
