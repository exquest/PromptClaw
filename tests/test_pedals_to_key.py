"""Tests for pedals_to_key.py — sustain/expression pedal to harmony mapping."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools" / "senseweave"))

from pedals_to_key import (
    pedal_to_harmonic_shift,
    expression_to_dynamics,
    key_shift_from_pedal_pattern,
)


# === pedal_to_harmonic_shift ===


class TestPedalToHarmonicShift:
    def test_sustain_on_holds_chord(self):
        result = pedal_to_harmonic_shift(sustain=True, expression=64)
        assert result["hold_chord"] is True

    def test_sustain_off_no_hold(self):
        result = pedal_to_harmonic_shift(sustain=False, expression=64)
        assert result["hold_chord"] is False

    def test_low_expression_low_tension(self):
        result = pedal_to_harmonic_shift(sustain=False, expression=0)
        assert result["tension"] < 0.1
        assert result["suggest_extensions"] is False

    def test_high_expression_high_tension(self):
        result = pedal_to_harmonic_shift(sustain=False, expression=127)
        assert result["tension"] > 0.9
        assert result["suggest_extensions"] is True

    def test_mid_expression_mid_tension(self):
        result = pedal_to_harmonic_shift(sustain=True, expression=64)
        assert 0.4 <= result["tension"] <= 0.6

    def test_tension_range_always_valid(self):
        for exp in (0, 32, 64, 96, 127):
            result = pedal_to_harmonic_shift(sustain=False, expression=exp)
            assert 0.0 <= result["tension"] <= 1.0

    def test_returns_expected_keys(self):
        result = pedal_to_harmonic_shift(sustain=True, expression=100)
        assert "hold_chord" in result
        assert "tension" in result
        assert "suggest_extensions" in result

    def test_extension_threshold_boundary(self):
        # Expression at midpoint: should not suggest extensions
        result = pedal_to_harmonic_shift(sustain=False, expression=63)
        assert result["suggest_extensions"] is False

        # Expression just above threshold: should suggest extensions
        result = pedal_to_harmonic_shift(sustain=False, expression=96)
        assert result["suggest_extensions"] is True

    def test_clamps_expression_below_zero(self):
        # Negative expression treated as 0
        result = pedal_to_harmonic_shift(sustain=False, expression=-5)
        assert result["tension"] == 0.0

    def test_clamps_expression_above_127(self):
        # Over-max expression treated as 127
        result = pedal_to_harmonic_shift(sustain=False, expression=200)
        assert result["tension"] == 1.0


# === expression_to_dynamics ===


class TestExpressionToDynamics:
    def test_zero_expression_quiet_dim(self):
        result = expression_to_dynamics(0)
        assert result["volume_factor"] <= 0.31
        assert result["brightness"] <= 0.01

    def test_max_expression_loud_bright(self):
        result = expression_to_dynamics(127)
        assert result["volume_factor"] >= 0.99
        assert result["brightness"] >= 0.99

    def test_mid_expression_mid_values(self):
        result = expression_to_dynamics(64)
        assert 0.5 <= result["volume_factor"] <= 0.8
        assert 0.4 <= result["brightness"] <= 0.6

    def test_returns_expected_keys(self):
        result = expression_to_dynamics(50)
        assert "volume_factor" in result
        assert "brightness" in result

    def test_volume_factor_range(self):
        for v in (0, 32, 64, 96, 127):
            result = expression_to_dynamics(v)
            assert 0.3 <= result["volume_factor"] <= 1.0

    def test_brightness_range(self):
        for v in (0, 32, 64, 96, 127):
            result = expression_to_dynamics(v)
            assert 0.0 <= result["brightness"] <= 1.0

    def test_monotonic_volume(self):
        """Volume should increase as expression increases."""
        values = [expression_to_dynamics(v)["volume_factor"] for v in range(0, 128, 8)]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_monotonic_brightness(self):
        """Brightness should increase as expression increases."""
        values = [expression_to_dynamics(v)["brightness"] for v in range(0, 128, 8)]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_clamps_negative(self):
        result = expression_to_dynamics(-10)
        assert result["volume_factor"] >= 0.3
        assert result["brightness"] >= 0.0

    def test_clamps_over_max(self):
        result = expression_to_dynamics(200)
        assert result["volume_factor"] <= 1.0
        assert result["brightness"] <= 1.0


# === key_shift_from_pedal_pattern ===


class TestKeyShiftFromPedalPattern:
    def test_empty_events_returns_none(self):
        assert key_shift_from_pedal_pattern([]) is None

    def test_single_event_returns_none(self):
        assert key_shift_from_pedal_pattern([(0.0, True)]) is None

    def test_rapid_on_off_on_modulate(self):
        # Rapid on-off-on within a short window => modulate
        events = [
            (0.0, True),
            (0.15, False),
            (0.3, True),
        ]
        assert key_shift_from_pedal_pattern(events) == "modulate"

    def test_long_hold_pedal_point(self):
        # Single long hold => pedal_point
        events = [
            (0.0, True),
            (3.0, True),  # still held after 3 seconds
        ]
        assert key_shift_from_pedal_pattern(events) == "pedal_point"

    def test_slow_on_off_returns_none(self):
        # Slow, deliberate pedal use — no special pattern
        events = [
            (0.0, True),
            (2.0, False),
        ]
        result = key_shift_from_pedal_pattern(events)
        assert result is None

    def test_returns_valid_values(self):
        # Whatever events, result must be one of the valid values
        events = [(0.0, True), (0.1, False), (0.2, True)]
        result = key_shift_from_pedal_pattern(events)
        assert result in ("modulate", "pedal_point", None)

    def test_rapid_pattern_timing_matters(self):
        # On-off-on but spread too far apart => not modulate
        events = [
            (0.0, True),
            (1.5, False),
            (3.0, True),
        ]
        result = key_shift_from_pedal_pattern(events)
        assert result != "modulate"

    def test_very_long_hold(self):
        # Very long hold = pedal_point
        events = [
            (0.0, True),
            (10.0, True),
        ]
        assert key_shift_from_pedal_pattern(events) == "pedal_point"


class PedalsToKeyEndToEndTests(unittest.TestCase):
    def test_expressive_pedal_phrase_produces_harmony_and_diagnostics(self) -> None:
        expression = 96
        rapid_modulation_events = [
            (10.0, True),
            (10.18, False),
            (10.35, True),
        ]
        held_landing_events = [
            (12.0, True),
            (14.25, True),
        ]

        harmonic_shift = pedal_to_harmonic_shift(sustain=True, expression=expression)
        dynamics = expression_to_dynamics(expression)
        modulation_intent = key_shift_from_pedal_pattern(rapid_modulation_events)
        landing_voicing = key_shift_from_pedal_pattern(held_landing_events)

        diagnostic = {
            "expression": expression,
            "harmony": harmonic_shift,
            "dynamics": dynamics,
            "modulation_intent": modulation_intent,
            "landing_voicing": landing_voicing,
            "score_hint": "hold_extended_modulation",
        }
        restored = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert harmonic_shift == {
            "hold_chord": True,
            "tension": 0.7559,
            "suggest_extensions": True,
        }
        assert dynamics == {
            "volume_factor": 0.8291,
            "brightness": 0.7559,
        }
        assert modulation_intent == "modulate"
        assert landing_voicing == "pedal_point"
        assert restored == diagnostic

    def test_expression_sweep_builds_json_safe_stage_diagnostics(self) -> None:
        stages = []
        for label, value in (("dim", 0), ("balanced", 64), ("bright", 127)):
            harmonic_shift = pedal_to_harmonic_shift(sustain=value >= 64, expression=value)
            dynamics = expression_to_dynamics(value)
            stages.append(
                {
                    "label": label,
                    "hold": harmonic_shift["hold_chord"],
                    "tension": harmonic_shift["tension"],
                    "volume": dynamics["volume_factor"],
                    "brightness": dynamics["brightness"],
                }
            )

        restored = json.loads(json.dumps(stages, sort_keys=True))

        assert [stage["label"] for stage in restored] == ["dim", "balanced", "bright"]
        assert restored[0]["volume"] < restored[1]["volume"] < restored[2]["volume"]
        assert restored[0]["brightness"] < restored[1]["brightness"] < restored[2]["brightness"]

    def test_sustain_release_phrase_changes_hold_state_without_losing_tension(self) -> None:
        phrase = [(True, 72), (False, 72), (True, 96)]
        states = []
        for sustain, expression in phrase:
            harmonic_shift = pedal_to_harmonic_shift(sustain=sustain, expression=expression)
            states.append((harmonic_shift["hold_chord"], harmonic_shift["tension"]))

        assert states[0][0] is True
        assert states[1][0] is False
        assert states[2][0] is True
        assert states[0][1] == states[1][1]
        assert states[2][1] > states[1][1]

    def test_modulation_window_sequence_survives_json_round_trip(self) -> None:
        windows = [
            {"events": [(0.0, True), (0.2, False), (0.4, True)], "expected": "modulate"},
            {"events": [(2.0, True), (4.4, True)], "expected": "pedal_point"},
        ]
        results = []
        for window in windows:
            intent = key_shift_from_pedal_pattern(window["events"])
            results.append({"intent": intent, "event_count": len(window["events"])})
            assert intent == window["expected"]

        restored = json.loads(json.dumps(results, sort_keys=True))

        assert restored == [
            {"intent": "modulate", "event_count": 3},
            {"intent": "pedal_point", "event_count": 2},
        ]

    def test_phrase_summary_labels_low_mid_and_high_expression(self) -> None:
        summaries = []
        for expression in (16, 64, 112):
            harmonic_shift = pedal_to_harmonic_shift(sustain=False, expression=expression)
            if harmonic_shift["tension"] >= 0.75:
                band = "high"
            elif harmonic_shift["tension"] >= 0.35:
                band = "mid"
            else:
                band = "low"
            summaries.append((expression, band, harmonic_shift["suggest_extensions"]))

        assert summaries == [
            (16, "low", False),
            (64, "mid", False),
            (112, "high", True),
        ]

    def test_recent_event_table_maps_to_expected_intents(self) -> None:
        cases = [
            ([(0.0, True), (0.1, False), (0.2, True)], "modulate"),
            ([(0.0, True), (1.2, False), (2.4, True)], None),
            ([(0.0, True), (2.1, True)], "pedal_point"),
        ]
        observed = []
        for events, expected in cases:
            result = key_shift_from_pedal_pattern(events)
            observed.append(result)
            assert result == expected

        assert observed == ["modulate", None, "pedal_point"]

    def test_score_hints_for_sustained_chord_use_extension_gate(self) -> None:
        hints = []
        for expression in (48, 80, 100):
            harmonic_shift = pedal_to_harmonic_shift(sustain=True, expression=expression)
            hint = "extended_hold" if harmonic_shift["suggest_extensions"] else "open_hold"
            hints.append((expression, hint, harmonic_shift["hold_chord"]))

        assert hints == [
            (48, "open_hold", True),
            (80, "extended_hold", True),
            (100, "extended_hold", True),
        ]

    def test_dynamic_profile_can_drive_renderer_controls(self) -> None:
        controls = []
        for expression in (0, 32, 96, 127):
            dynamics = expression_to_dynamics(expression)
            controls.append(
                {
                    "amp": dynamics["volume_factor"],
                    "filter_mix": dynamics["brightness"],
                    "active": dynamics["volume_factor"] > 0.5,
                }
            )

        assert controls[0]["active"] is False
        assert controls[-1]["active"] is True
        assert controls[1]["amp"] < controls[2]["amp"] < controls[3]["amp"]

    def test_pedal_story_combines_opening_transition_and_landing(self) -> None:
        story_events = [
            ("opening", [(0.0, True), (0.12, False), (0.28, True)]),
            ("landing", [(3.0, True), (5.2, True)]),
        ]
        story = {}
        for label, events in story_events:
            story[label] = key_shift_from_pedal_pattern(events)

        assert story == {"opening": "modulate", "landing": "pedal_point"}
        assert json.loads(json.dumps(story, sort_keys=True)) == story

    def test_expression_clamping_keeps_diagnostic_bounded(self) -> None:
        diagnostics = []
        for expression in (-20, 0, 127, 180):
            harmonic_shift = pedal_to_harmonic_shift(sustain=False, expression=expression)
            dynamics = expression_to_dynamics(expression)
            diagnostics.append(
                (
                    harmonic_shift["tension"],
                    dynamics["volume_factor"],
                    dynamics["brightness"],
                )
            )

        for tension, volume, brightness in diagnostics:
            assert 0.0 <= tension <= 1.0
            assert 0.3 <= volume <= 1.0
            assert 0.0 <= brightness <= 1.0

    def test_modulation_and_pedal_point_are_distinct_in_one_payload(self) -> None:
        payload = {
            "transition": key_shift_from_pedal_pattern(
                [(1.0, True), (1.1, False), (1.2, True)]
            ),
            "arrival": key_shift_from_pedal_pattern([(2.0, True), (4.5, True)]),
        }
        labels = []
        for key, value in payload.items():
            if value is not None:
                labels.append(f"{key}:{value}")

        assert labels == ["transition:modulate", "arrival:pedal_point"]
        assert payload["transition"] != payload["arrival"]

    def test_serialized_phrase_batch_preserves_ordered_intents(self) -> None:
        phrase_batch = [
            [(0.0, True), (0.2, False), (0.4, True)],
            [(1.0, True), (1.6, False)],
            [(2.0, True), (4.1, True)],
        ]
        intents = []
        for events in phrase_batch:
            intent = key_shift_from_pedal_pattern(events)
            intents.append("steady" if intent is None else intent)

        restored = json.loads(json.dumps({"intents": intents}, sort_keys=True))

        assert restored["intents"] == ["modulate", "steady", "pedal_point"]

    def test_harmonic_and_dynamic_tension_share_expression_curve(self) -> None:
        combined = []
        for expression in (24, 72, 120):
            harmonic_shift = pedal_to_harmonic_shift(sustain=True, expression=expression)
            dynamics = expression_to_dynamics(expression)
            combined.append(
                (
                    harmonic_shift["tension"],
                    dynamics["brightness"],
                    harmonic_shift["suggest_extensions"],
                )
            )

        assert combined[0][0] == combined[0][1]
        assert combined[1][0] == combined[1][1]
        assert combined[2][0] == combined[2][1]
        assert [row[2] for row in combined] == [False, False, True]

    def test_hold_chord_and_dynamics_form_playback_plan(self) -> None:
        playback_plan = []
        for sustain, expression in ((False, 40), (True, 88), (True, 112)):
            harmonic_shift = pedal_to_harmonic_shift(sustain=sustain, expression=expression)
            dynamics = expression_to_dynamics(expression)
            playback_plan.append(
                {
                    "hold": harmonic_shift["hold_chord"],
                    "extension": harmonic_shift["suggest_extensions"],
                    "volume": dynamics["volume_factor"],
                }
            )

        assert playback_plan[0] == {"hold": False, "extension": False, "volume": 0.5205}
        assert playback_plan[1]["hold"] is True
        assert playback_plan[1]["extension"] is True
        assert playback_plan[2]["volume"] > playback_plan[1]["volume"]

    def test_phrase_diagnostic_contains_only_json_primitives(self) -> None:
        diagnostic = {
            "harmonic": pedal_to_harmonic_shift(sustain=True, expression=100),
            "dynamic": expression_to_dynamics(100),
            "gesture": key_shift_from_pedal_pattern(
                [(0.0, True), (0.15, False), (0.3, True)]
            ),
        }
        restored = json.loads(json.dumps(diagnostic, sort_keys=True))
        primitive_types = (str, int, float, bool, type(None))

        for section in restored.values():
            if isinstance(section, dict):
                for value in section.values():
                    assert isinstance(value, primitive_types)
            else:
                assert isinstance(section, primitive_types)

        assert restored["gesture"] == "modulate"
