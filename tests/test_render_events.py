from __future__ import annotations

import json
import math
from dataclasses import FrozenInstanceError, fields

import pytest

from cypherclaw.render.events import Event, IntentTag, PerformanceIntent, SectionEnvelope, VALID_ARC_SHAPES


class TestIntentTag:
    def test_has_exactly_six_values(self) -> None:
        assert len(IntentTag) == 6

    def test_contains_required_values(self) -> None:
        expected = {"build", "settle", "question", "answer", "withhold", "punctuate"}
        assert {tag.value for tag in IntentTag} == expected

    def test_values_accessible_by_name(self) -> None:
        assert IntentTag.BUILD.value == "build"
        assert IntentTag.SETTLE.value == "settle"
        assert IntentTag.QUESTION.value == "question"
        assert IntentTag.ANSWER.value == "answer"
        assert IntentTag.WITHHOLD.value == "withhold"
        assert IntentTag.PUNCTUATE.value == "punctuate"


def test_event_defines_render_contract_fields() -> None:
    field_names = {field.name for field in fields(Event)}

    assert {
        "event_id",
        "phrase_id",
        "section_id",
        "voice_id",
        "role",
        "pitch",
        "nominal_beat",
        "nominal_dur_beats",
        "harmonic_charge",
        "melodic_charge",
        "metric_weight",
        "is_phrase_start",
        "is_phrase_end",
        "is_cadential",
        "intent_tag",
        "onset_sec",
        "dur_sec",
        "velocity",
        "timing_deviation_ms",
        "articulation",
        "sensor_tempo_scale",
        "sensor_amp_scale",
        "sensor_brightness",
        "rule_stack",
        "seed_path",
    } <= field_names


def test_score_fields_lock_after_render_stage() -> None:
    event = Event(event_id="evt-1", role="melody", pitch=60)

    event.lock_score_fields()
    event.onset_sec = 1.25
    event.timing_deviation_ms = -2.5
    event.sensor_brightness = 0.4
    event.rule_stack.append("R8")

    assert event.onset_sec == 1.25
    assert event.timing_deviation_ms == -2.5
    assert event.sensor_brightness == 0.4
    assert event.rule_stack == ["R8"]
    with pytest.raises(FrozenInstanceError):
        event.pitch = 62
    with pytest.raises(FrozenInstanceError):
        event.role = "bass"


def test_event_json_and_osc_bundle_round_trip() -> None:
    event = Event(
        event_id="evt-1",
        phrase_id="phrase-a",
        section_id="intro",
        voice_id="vln-1",
        role="melody",
        pitch=64,
        nominal_beat=3.5,
        nominal_dur_beats=0.75,
        harmonic_charge=0.2,
        melodic_charge=0.8,
        metric_weight=1.0,
        is_phrase_start=True,
        intent_tag="withhold",
        onset_sec=1.2,
        dur_sec=0.4,
        velocity=0.72,
        timing_deviation_ms=3.0,
        articulation="legato",
        sensor_tempo_scale=1.02,
        sensor_amp_scale=0.95,
        sensor_brightness=-0.1,
        rule_stack=["R2", "R8"],
        seed_path=(7, 11),
    )

    json_payload = json.loads(json.dumps(event.to_json_dict()))
    restored = Event.from_json_dict(json_payload)
    osc_restored = Event.from_osc_bundle(event.to_osc_bundle())

    assert restored == event
    assert restored.seed_path == (7, 11)
    assert osc_restored == event


def test_event_carries_freq_hz_directly_through_osc() -> None:
    # When the active tuning is not 12-TET, the composer emits Hz directly
    # rather than relying on midinote -> midicps conversion downstream.
    event = Event(
        event_id="evt-2",
        role="melody",
        pitch=60,
        freq_hz=261.625565 * (5.0 / 4.0),
    )

    payload = event.to_json_dict()
    assert payload["freq_hz"] == pytest.approx(261.625565 * 5.0 / 4.0)

    osc_restored = Event.from_osc_bundle(event.to_osc_bundle())
    assert osc_restored.freq_hz == pytest.approx(261.625565 * 5.0 / 4.0)


def test_event_freq_hz_defaults_to_none_for_legacy_12tet_scenes() -> None:
    event = Event(event_id="evt-3", role="bass", pitch=48)

    assert event.freq_hz is None
    restored = Event.from_osc_bundle(event.to_osc_bundle())
    assert restored.freq_hz is None


class TestPerformanceIntent:
    def test_defaults_match_kth_k1_calibrated_values(self) -> None:
        intent = PerformanceIntent(phrase_id="p-1")
        assert intent.arc_shape == "parabolic"
        assert intent.arc_peak_position == 0.6
        assert intent.tempo_deviation_pct == 4.0
        assert intent.dynamic_range_db == 9.0
        assert intent.articulation_mean == 0.5
        assert intent.breath_after_ms == 250.0
        assert intent.tension_target == 0.5
        assert intent.restraint == 0.0
        assert intent.call_response_role == ""

    def test_all_arc_shapes_accepted(self) -> None:
        for shape in VALID_ARC_SHAPES:
            intent = PerformanceIntent(phrase_id="p-1", arc_shape=shape)
            assert intent.arc_shape == shape

    def test_invalid_arc_shape_rejected(self) -> None:
        with pytest.raises(ValueError, match="arc_shape must be one of"):
            PerformanceIntent(phrase_id="p-1", arc_shape="triangle")

    def test_arc_peak_position_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="arc_peak_position"):
            PerformanceIntent(phrase_id="p-1", arc_peak_position=1.5)
        with pytest.raises(ValueError, match="arc_peak_position"):
            PerformanceIntent(phrase_id="p-1", arc_peak_position=-0.1)

    def test_negative_tempo_deviation_rejected(self) -> None:
        with pytest.raises(ValueError, match="tempo_deviation_pct"):
            PerformanceIntent(phrase_id="p-1", tempo_deviation_pct=-1.0)

    def test_negative_dynamic_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="dynamic_range_db"):
            PerformanceIntent(phrase_id="p-1", dynamic_range_db=-1.0)

    def test_articulation_mean_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="articulation_mean"):
            PerformanceIntent(phrase_id="p-1", articulation_mean=1.5)

    def test_negative_breath_after_rejected(self) -> None:
        with pytest.raises(ValueError, match="breath_after_ms"):
            PerformanceIntent(phrase_id="p-1", breath_after_ms=-10.0)

    def test_tension_target_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="tension_target"):
            PerformanceIntent(phrase_id="p-1", tension_target=2.0)

    def test_restraint_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="restraint"):
            PerformanceIntent(phrase_id="p-1", restraint=-0.5)
        with pytest.raises(ValueError, match="restraint"):
            PerformanceIntent(phrase_id="p-1", restraint=1.1)

    def test_custom_values_accepted(self) -> None:
        intent = PerformanceIntent(
            phrase_id="p-2",
            arc_shape="cosine",
            arc_peak_position=0.4,
            tempo_deviation_pct=6.0,
            dynamic_range_db=12.0,
            articulation_mean=0.7,
            breath_after_ms=400.0,
            tension_target=0.8,
            restraint=0.3,
            call_response_role="call",
        )
        assert intent.phrase_id == "p-2"
        assert intent.arc_shape == "cosine"
        assert intent.arc_peak_position == 0.4
        assert intent.tempo_deviation_pct == 6.0
        assert intent.dynamic_range_db == 12.0
        assert intent.articulation_mean == 0.7
        assert intent.breath_after_ms == 400.0
        assert intent.tension_target == 0.8
        assert intent.restraint == 0.3
        assert intent.call_response_role == "call"


class TestSectionEnvelope:
    def test_linear_breakpoint_interpolation_samples_all_parameters(self) -> None:
        envelope = SectionEnvelope(
            tempo_base=((0.0, 0.95), (0.5, 1.05), (1.0, 1.0)),
            density_target=((0.0, 0.2), (1.0, 0.8)),
            dynamic_plane=((0.0, 0.5), (1.0, 1.0)),
            brightness=((0.0, 0.25), (1.0, 0.75)),
            tension_trajectory=((0.0, 0.1), (1.0, 0.9)),
        )

        sample = envelope.sample(0.25)

        assert math.isclose(sample.tempo_base, 1.0)
        assert math.isclose(sample.density_target, 0.35)
        assert math.isclose(sample.dynamic_plane, 0.625)
        assert math.isclose(sample.brightness, 0.375)
        assert math.isclose(sample.tension_trajectory, 0.3)

    def test_spline_interpolation_is_available(self) -> None:
        linear = SectionEnvelope(
            tempo_base=((0.0, 1.0), (0.5, 2.0), (1.0, 2.0)),
        )
        spline = SectionEnvelope(
            tempo_base=((0.0, 1.0), (0.5, 2.0), (1.0, 2.0)),
            interpolation="spline",
        )

        assert math.isclose(linear.sample(0.25).tempo_base, 1.5)
        assert math.isclose(spline.sample(0.25).tempo_base, 1.5625)

    def test_parameter_bounds_are_validated(self) -> None:
        with pytest.raises(ValueError, match="sample position"):
            SectionEnvelope().sample(1.1)
        with pytest.raises(ValueError, match="breakpoint position"):
            SectionEnvelope(tempo_base=((-0.1, 1.0), (1.0, 1.0)))
        with pytest.raises(ValueError, match="density_target"):
            SectionEnvelope(density_target=((0.0, 0.2), (1.0, 1.2)))
        with pytest.raises(ValueError, match="tempo_base"):
            SectionEnvelope(tempo_base=0.0)
        with pytest.raises(ValueError, match="interpolation"):
            SectionEnvelope(interpolation="step")


class RenderEventsEndToEndTests:
    """End-to-end render-events lifecycle across the public surface."""

    __test__ = True

    def test_full_render_events_lifecycle_is_json_and_osc_round_trip_safe(
        self,
    ) -> None:
        from cypherclaw.render.events import (
            SECTION_ENVELOPE_PARAMETERS,
            SectionEnvelopeSample,
        )

        envelope = SectionEnvelope(
            tempo_base=((0.0, 0.95), (0.5, 1.05), (1.0, 1.0)),
            density_target=((0.0, 0.2), (1.0, 0.8)),
            dynamic_plane=((0.0, 0.5), (1.0, 1.0)),
            brightness=((0.0, 0.25), (1.0, 0.75)),
            tension_trajectory=((0.0, 0.1), (1.0, 0.9)),
        )
        sample = envelope.sample(0.25)

        assert isinstance(sample, SectionEnvelopeSample)
        for parameter in SECTION_ENVELOPE_PARAMETERS:
            assert math.isclose(
                getattr(sample, parameter),
                envelope.value_at(parameter, 0.25),
            )

        intent = PerformanceIntent(
            phrase_id="phrase-a",
            arc_shape="cosine",
            arc_peak_position=0.4,
            tempo_deviation_pct=6.0,
            dynamic_range_db=12.0,
            articulation_mean=0.7,
            breath_after_ms=400.0,
            tension_target=0.8,
            restraint=0.3,
            call_response_role="call",
        )
        assert intent.phrase_id == "phrase-a"
        assert intent.arc_shape == "cosine"
        assert intent.call_response_role == "call"

        start_event = Event(
            event_id="evt-start",
            phrase_id="phrase-a",
            section_id="intro",
            voice_id="vln-1",
            role="melody",
            pitch=64,
            nominal_beat=0.0,
            nominal_dur_beats=1.0,
            harmonic_charge=0.3,
            melodic_charge=0.6,
            metric_weight=1.0,
            is_phrase_start=True,
            intent_tag=IntentTag.BUILD.value,
            onset_sec=0.0,
            dur_sec=0.5,
            velocity=0.7,
            timing_deviation_ms=2.5,
            articulation="legato",
            sensor_tempo_scale=1.02,
            sensor_amp_scale=0.95,
            sensor_brightness=-0.1,
            rule_stack=["R2", "R8"],
            seed_path=(7, 11),
        )
        end_event = Event(
            event_id="evt-end",
            phrase_id="phrase-a",
            section_id="intro",
            voice_id="vln-1",
            role="melody",
            pitch=67,
            nominal_beat=3.5,
            nominal_dur_beats=0.5,
            harmonic_charge=0.4,
            melodic_charge=0.2,
            metric_weight=0.75,
            is_phrase_end=True,
            is_cadential=True,
            intent_tag=IntentTag.SETTLE.value,
            onset_sec=2.0,
            dur_sec=0.4,
            velocity=0.6,
            timing_deviation_ms=-1.0,
            articulation="staccato",
            sensor_tempo_scale=1.0,
            sensor_amp_scale=1.0,
            sensor_brightness=0.05,
            rule_stack=["R2"],
            seed_path=(7, 13),
        )

        for event in (start_event, end_event):
            event.lock_score_fields()
            assert event.score_fields_locked is True
            event.onset_sec = event.onset_sec + 0.01
            event.timing_deviation_ms = event.timing_deviation_ms + 0.5
            event.sensor_brightness = event.sensor_brightness + 0.01
            event.rule_stack.append("R10")
            with pytest.raises(FrozenInstanceError):
                event.pitch = 60
            with pytest.raises(FrozenInstanceError):
                event.intent_tag = IntentTag.WITHHOLD.value

        for event in (start_event, end_event):
            json_dict = event.to_json_dict()
            from_dict = Event.from_json_dict(json_dict)
            from_json = Event.from_json(event.to_json())
            from_osc = Event.from_osc_bundle(event.to_osc_bundle())

            assert from_dict == event
            assert from_json == event
            assert from_osc == event
            assert from_dict.seed_path == event.seed_path
            assert from_osc.rule_stack == event.rule_stack

        diagnostic = {
            "intent_tags": sorted(tag.value for tag in IntentTag),
            "valid_arc_shapes": sorted(VALID_ARC_SHAPES),
            "envelope_parameters": list(SECTION_ENVELOPE_PARAMETERS),
            "sample": {
                parameter: getattr(sample, parameter)
                for parameter in SECTION_ENVELOPE_PARAMETERS
            },
            "intent": {
                "phrase_id": intent.phrase_id,
                "arc_shape": intent.arc_shape,
                "tempo_deviation_pct": intent.tempo_deviation_pct,
                "tension_target": intent.tension_target,
                "call_response_role": intent.call_response_role,
            },
            "events": [start_event.to_json_dict(), end_event.to_json_dict()],
        }
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped["intent_tags"] == [
            "answer",
            "build",
            "punctuate",
            "question",
            "settle",
            "withhold",
        ]
        assert round_tripped["envelope_parameters"] == list(
            SECTION_ENVELOPE_PARAMETERS
        )
        assert round_tripped["intent"]["arc_shape"] == "cosine"
        assert round_tripped["events"][0]["intent_tag"] == "build"
        assert round_tripped["events"][1]["intent_tag"] == "settle"
        assert round_tripped["events"][0]["seed_path"] == [7, 11]
        assert round_tripped["events"][1]["is_cadential"] is True

    def test_round_trip_preserves_each_intent_tag_through_json_and_osc(
        self,
    ) -> None:
        for index, tag in enumerate(IntentTag):
            event = Event(
                event_id=f"evt-{index}",
                phrase_id="phrase-tag",
                role="melody",
                pitch=60 + index,
                intent_tag=tag.value,
                rule_stack=[f"R{index}"],
                seed_path=(index, index + 1),
            )
            from_json = Event.from_json(event.to_json())
            from_osc = Event.from_osc_bundle(event.to_osc_bundle())
            assert from_json == event
            assert from_osc == event
            assert from_json.intent_tag == tag.value
            assert from_osc.seed_path == (index, index + 1)

    def test_envelope_samples_each_arc_shape_intent_to_consistent_parameter_values(
        self,
    ) -> None:
        from cypherclaw.render.events import (
            SECTION_ENVELOPE_PARAMETERS,
            SectionEnvelopeSample,
        )

        envelope = SectionEnvelope(
            tempo_base=((0.0, 0.95), (0.5, 1.05), (1.0, 1.0)),
            density_target=((0.0, 0.2), (1.0, 0.8)),
            dynamic_plane=((0.0, 0.5), (1.0, 1.0)),
            brightness=((0.0, 0.25), (1.0, 0.75)),
            tension_trajectory=((0.0, 0.1), (1.0, 0.9)),
        )
        for shape in sorted(VALID_ARC_SHAPES):
            intent = PerformanceIntent(phrase_id=f"p-{shape}", arc_shape=shape)
            sample = envelope.sample(0.5)
            assert isinstance(sample, SectionEnvelopeSample)
            assert intent.arc_shape == shape
            for parameter in SECTION_ENVELOPE_PARAMETERS:
                assert math.isclose(
                    getattr(sample, parameter),
                    envelope.value_at(parameter, 0.5),
                )
