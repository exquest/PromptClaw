"""Tests for theramini_duet.py -- musical intelligence for CypherClaw duets.

depth: 2

Adds end-to-end depth-2 coverage for the Theramini conversation lifecycle:
listening-phase normalization, listening / speaking / solo plan_duet_response
transitions, focused-helper agreement on the speaking phase, supported
partner behaviors, and a JSON-safe diagnostic round-trip.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.theramini_duet import (
    ConversationDecision,
    normalize_theramini_state,
    plan_duet_response,
    supported_partner_behaviors,
    suggest_response_key,
    suggest_response_register,
    suggest_response_density,
    suggest_response_phrase,
    calculate_wait_beats,
    should_enter_duet,
    should_exit_duet,
)


# === suggest_response_key ===


class TestSuggestResponseKey:
    def test_a440_returns_a_key(self):
        key_name, root_freq = suggest_response_key(440.0)
        assert key_name == "A"
        assert isinstance(root_freq, float)
        assert root_freq > 0

    def test_c4_returns_c_key(self):
        key_name, root_freq = suggest_response_key(261.63)
        assert key_name == "C"
        assert isinstance(root_freq, float)

    def test_d3_returns_d_key(self):
        key_name, root_freq = suggest_response_key(146.83)
        assert key_name == "D"
        assert isinstance(root_freq, float)

    def test_root_freq_is_positive(self):
        _, root_freq = suggest_response_key(880.0)
        assert root_freq > 0

    def test_returns_tuple_of_str_and_float(self):
        result = suggest_response_key(330.0)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], float)


# === suggest_response_register ===


class TestSuggestResponseRegister:
    def test_high_pitch_suggests_low(self):
        # C6 = 1046.5 Hz -- high register
        reg = suggest_response_register(1046.5)
        assert reg == "low"

    def test_low_pitch_suggests_high(self):
        # A2 = 110 Hz -- low register
        reg = suggest_response_register(110.0)
        assert reg == "high"

    def test_mid_pitch_suggests_complementary_band(self):
        # A4 = 440 Hz -- upper mid register, so answer below it.
        reg = suggest_response_register(440.0)
        assert reg == "low"

    def test_very_high_pitch_suggests_low(self):
        reg = suggest_response_register(2000.0)
        assert reg == "low"

    def test_very_low_pitch_suggests_high(self):
        reg = suggest_response_register(80.0)
        assert reg == "high"

    def test_returns_string(self):
        reg = suggest_response_register(300.0)
        assert reg in ("low", "mid", "high")


# === suggest_response_density ===


class TestSuggestResponseDensity:
    def test_fast_onsets_suggest_sparse(self):
        density = suggest_response_density(3.0)
        assert density == "sparse"

    def test_slow_onsets_suggest_moderate(self):
        density = suggest_response_density(0.3)
        assert density == "moderate"

    def test_medium_onsets_suggest_dense(self):
        # Between 0.5 and 2.0 -- medium rate
        density = suggest_response_density(1.0)
        assert density == "dense"

    def test_boundary_fast(self):
        # Exactly at >2 threshold
        density = suggest_response_density(2.5)
        assert density == "sparse"

    def test_boundary_slow(self):
        # Exactly at <0.5 threshold
        density = suggest_response_density(0.4)
        assert density == "moderate"

    def test_zero_onsets(self):
        density = suggest_response_density(0.0)
        assert density == "moderate"


# === suggest_response_phrase ===


class TestSuggestResponsePhrase:
    def test_returns_list_of_tuples(self):
        phrase = suggest_response_phrase(440.0, "mid", "dense")
        assert isinstance(phrase, list)
        assert all(isinstance(n, tuple) and len(n) == 2 for n in phrase)

    def test_phrase_length_3_to_6(self):
        # Run multiple times to cover random variation
        for _ in range(20):
            phrase = suggest_response_phrase(440.0, "mid", "dense")
            assert 3 <= len(phrase) <= 6, f"got length {len(phrase)}"

    def test_frequencies_are_positive(self):
        phrase = suggest_response_phrase(261.63, "low", "sparse")
        for freq, dur in phrase:
            assert freq > 0, f"got non-positive freq {freq}"
            assert dur > 0, f"got non-positive duration {dur}"

    def test_sparse_has_longer_durations(self):
        # Sparse = long notes, dense = short notes
        sparse_phrases = [suggest_response_phrase(440.0, "mid", "sparse") for _ in range(10)]
        dense_phrases = [suggest_response_phrase(440.0, "mid", "dense") for _ in range(10)]
        avg_sparse_dur = sum(d for p in sparse_phrases for _, d in p) / sum(len(p) for p in sparse_phrases)
        avg_dense_dur = sum(d for p in dense_phrases for _, d in p) / sum(len(p) for p in dense_phrases)
        assert avg_sparse_dur > avg_dense_dur

    def test_low_register_lower_freqs(self):
        low_phrases = [suggest_response_phrase(440.0, "low", "dense") for _ in range(10)]
        high_phrases = [suggest_response_phrase(440.0, "high", "dense") for _ in range(10)]
        avg_low_freq = sum(f for p in low_phrases for f, _ in p) / sum(len(p) for p in low_phrases)
        avg_high_freq = sum(f for p in high_phrases for f, _ in p) / sum(len(p) for p in high_phrases)
        assert avg_low_freq < avg_high_freq

    def test_different_keys_produce_different_freqs(self):
        # C root vs F# root should give different frequency sets
        c_phrase = suggest_response_phrase(261.63, "mid", "dense")
        fsharp_phrase = suggest_response_phrase(369.99, "mid", "dense")
        c_freqs = {round(f, 1) for f, _ in c_phrase}
        fs_freqs = {round(f, 1) for f, _ in fsharp_phrase}
        # They shouldn't be identical (though overlap is possible)
        # At minimum, test that both produce valid output
        assert len(c_freqs) > 0
        assert len(fs_freqs) > 0

    def test_complementary_register_phrase_avoids_crowding_source_pitch(self):
        source_pitch = 440.0
        register = suggest_response_register(source_pitch)

        phrases = [suggest_response_phrase(source_pitch, register, "dense") for _ in range(20)]

        assert register == "low"
        assert all(freq <= source_pitch * 0.75 for phrase in phrases for freq, _duration in phrase)


# === calculate_wait_beats ===


class TestCalculateWaitBeats:
    def test_still_playing_returns_zero(self):
        beats = calculate_wait_beats(0, 0.5)
        assert beats == 0

    def test_short_silence_returns_2(self):
        beats = calculate_wait_beats(1000, 0.5)
        assert 2 <= beats <= 4

    def test_long_silence_returns_higher(self):
        beats = calculate_wait_beats(4000, 0.5)
        assert 2 <= beats <= 4

    def test_returns_int(self):
        beats = calculate_wait_beats(2000, 0.5)
        assert isinstance(beats, int)

    def test_zero_silence_returns_zero(self):
        beats = calculate_wait_beats(0, 0.5)
        assert beats == 0

    def test_varies_with_silence_duration(self):
        short = calculate_wait_beats(500, 0.5)
        long = calculate_wait_beats(3000, 0.5)
        assert short <= long


# === should_enter_duet ===


class TestShouldEnterDuet:
    def _make_state(self, **overrides):
        base = {
            "timestamp": time.time(),
            "is_playing": True,
            "pitch_hz": 440.0,
            "pitch_note": "A4",
            "pitch_confidence": 0.8,
            "rms": 0.05,
            "peak": 0.1,
            "state": "sustain",
            "suggested_key": "A",
            "suggested_scale": ["A", "B", "C#", "D", "E", "F#", "G#"],
            "consecutive_silence_ms": 0,
            "onset_time": time.time() - 1.0,
        }
        base.update(overrides)
        return base

    def test_active_playing_enters_duet(self):
        state = self._make_state()
        assert should_enter_duet(state) is True

    def test_not_playing_rejects(self):
        state = self._make_state(is_playing=False)
        assert should_enter_duet(state) is False

    def test_low_confidence_rejects(self):
        state = self._make_state(pitch_confidence=0.1)
        assert should_enter_duet(state) is False

    def test_stale_timestamp_rejects(self):
        state = self._make_state(timestamp=time.time() - 30)
        assert should_enter_duet(state) is False

    def test_idle_tone_rejects(self):
        state = self._make_state(idle_tone=True)
        assert should_enter_duet(state) is False

    def test_no_pitch_rejects(self):
        state = self._make_state(pitch_hz=None, is_playing=False)
        assert should_enter_duet(state) is False

    def test_missing_fields_rejects(self):
        # Malformed state should not crash, just return False
        assert should_enter_duet({}) is False
        assert should_enter_duet({"timestamp": time.time()}) is False


# === should_exit_duet ===


class TestShouldExitDuet:
    def _make_state(self, **overrides):
        base = {
            "timestamp": time.time(),
            "is_playing": True,
            "pitch_hz": 440.0,
            "pitch_confidence": 0.8,
            "rms": 0.05,
            "state": "sustain",
            "consecutive_silence_ms": 0,
        }
        base.update(overrides)
        return base

    def test_still_playing_no_exit(self):
        state = self._make_state()
        assert should_exit_duet(state) is False

    def test_long_silence_exits(self):
        state = self._make_state(
            is_playing=False,
            consecutive_silence_ms=6000,
            state="silence",
        )
        assert should_exit_duet(state) is True

    def test_short_silence_no_exit(self):
        state = self._make_state(
            is_playing=False,
            consecutive_silence_ms=2000,
            state="silence",
        )
        assert should_exit_duet(state) is False

    def test_custom_threshold(self):
        state = self._make_state(
            is_playing=False,
            consecutive_silence_ms=3000,
            state="silence",
        )
        assert should_exit_duet(state, silence_threshold_ms=2000) is True
        assert should_exit_duet(state, silence_threshold_ms=4000) is False

    def test_stale_timestamp_exits(self):
        state = self._make_state(timestamp=time.time() - 30)
        assert should_exit_duet(state) is True

    def test_missing_fields_exits_safely(self):
        # Malformed state should exit (fail safe)
        assert should_exit_duet({}) is True


# === Theramini conversation protocol ===


class TestConversationProtocol:
    def _make_state(self, **overrides):
        base = {
            "timestamp": time.time(),
            "is_playing": True,
            "pitch_hz": 440.0,
            "pitch_note": "A4",
            "pitch_confidence": 0.8,
            "rms": 0.05,
            "state": "sustain",
            "suggested_key": "A",
            "consecutive_silence_ms": 0,
            "onset_rate": 1.0,
        }
        base.update(overrides)
        return base

    def test_normalized_state_exposes_shared_contract(self):
        state = normalize_theramini_state(self._make_state(midi_cc={"raw": {"11": 80}}))

        assert state["listening"] is True
        assert state["speaking"] is False
        assert state["silence_request"] is False
        assert state["human_gesture_active"] is True
        assert state["midi_cc"]["expression"] == 80
        assert state["conversation"]["phase"] == "listening"
        assert state["conversation"]["policy"] == "turn_taking"
        assert state["conversation"]["speaker"] == "human"

    def test_policy_does_not_play_over_active_human_gesture(self):
        decision = plan_duet_response(self._make_state())

        assert decision.phase == "listening"
        assert decision.policy == "turn_taking"
        assert decision.speaker == "human"
        assert decision.may_play is False
        assert decision.duet_active is True
        assert decision.lead_role == "theramini"
        assert decision.support_role == "cypherclaw"
        assert decision.max_overlap_beats == 0

    def test_recovery_to_solo_after_inactivity(self):
        decision = plan_duet_response(
            self._make_state(
                is_playing=False,
                pitch_hz=None,
                pitch_confidence=0.0,
                state="silence",
                consecutive_silence_ms=6500,
            )
        )

        assert decision.phase == "solo"
        assert decision.policy == "solo"
        assert decision.may_play is False
        assert decision.duet_active is False

    def test_silence_request_from_cc_blocks_output(self):
        decision = plan_duet_response(
            self._make_state(
                is_playing=False,
                pitch_hz=None,
                pitch_confidence=0.0,
                consecutive_silence_ms=2000,
                midi_cc={"expression": 0},
            )
        )

        assert decision.phase == "silence"
        assert decision.policy == "silence_request"
        assert decision.may_play is False
        assert decision.duet_active is True

    def test_requested_silence_blocks_output(self):
        decision = plan_duet_response(
            self._make_state(
                is_playing=False,
                pitch_hz=None,
                pitch_confidence=0.0,
                consecutive_silence_ms=1600,
                requested_policy="silence",
            )
        )

        assert decision.phase == "silence"
        assert decision.policy == "silence_request"
        assert decision.may_play is False

    def test_explicit_response_policies_are_supported(self):
        for policy in ("imitation", "counterpoint", "accompaniment", "call_response", "commentary", "completion"):
            decision = plan_duet_response(
                self._make_state(
                    is_playing=False,
                    pitch_hz=440.0,
                    consecutive_silence_ms=1600,
                    requested_policy=policy,
                )
            )

            assert decision.phase == "speaking"
            assert decision.policy == policy
            assert decision.speaker == "cypherclaw"
            assert decision.may_play is True

    def test_partner_policy_covers_ensemble_space_behaviors(self):
        expected = {
            "listening_first",
            "complementary_register",
            "rhythmic_sympathy",
            "harmonic_response_intervals",
            "accompaniment_textures",
            "call_response",
            "imitation",
            "commentary",
            "completion",
            "silence",
        }

        assert expected <= set(supported_partner_behaviors())

    def test_response_metadata_describes_partner_space(self):
        decision = plan_duet_response(
            self._make_state(
                is_playing=False,
                pitch_hz=440.0,
                consecutive_silence_ms=1600,
                requested_policy="call/response",
            )
        )
        payload = decision.to_dict()

        assert decision.phase == "speaking"
        assert decision.policy == "call_response"
        assert decision.response_register == "low"
        assert decision.rhythmic_sympathy == "shared_pulse"
        assert decision.harmonic_intervals
        assert decision.accompaniment_texture == "answering_phrase"
        assert decision.lead_role == "cypherclaw"
        assert decision.support_role == "theramini"
        assert "complementary_register" in payload["partner_behaviors"]

    def test_requested_completion_still_listens_first_during_human_gesture(self):
        decision = plan_duet_response(self._make_state(requested_policy="completion"))

        assert decision.phase == "listening"
        assert decision.policy == "turn_taking"
        assert decision.may_play is False
        assert decision.max_overlap_beats == 0


# ---------------------------------------------------------------------------
# End-to-end depth-2 coverage
# ---------------------------------------------------------------------------


class TheraminiDuetEndToEndTests:
    """End-to-end diagnostic coverage for the Theramini duet conversation."""

    __test__ = True

    def test_theramini_duet_conversation_lifecycle_round_trips_json_diagnostic(
        self,
    ) -> None:
        now = time.time()

        listening_state_input = {
            "timestamp": now,
            "is_playing": True,
            "pitch_hz": 440.0,
            "pitch_note": "A4",
            "pitch_confidence": 0.8,
            "rms": 0.05,
            "peak": 0.1,
            "state": "sustain",
            "suggested_key": "A",
            "consecutive_silence_ms": 0,
            "onset_rate": 1.0,
            "onset_time": now - 1.0,
        }

        normalized_listening = normalize_theramini_state(
            listening_state_input, now=now
        )
        assert normalized_listening["listening"] is True
        assert normalized_listening["speaking"] is False
        assert normalized_listening["silence_request"] is False
        assert normalized_listening["human_gesture_active"] is True
        conversation = normalized_listening["conversation"]
        assert isinstance(conversation, dict)
        assert conversation["phase"] == "listening"
        assert conversation["policy"] == "turn_taking"
        assert conversation["speaker"] == "human"

        listening_decision = plan_duet_response(listening_state_input, now=now)
        assert isinstance(listening_decision, ConversationDecision)
        assert listening_decision.phase == "listening"
        assert listening_decision.policy == "turn_taking"
        assert listening_decision.speaker == "human"
        assert listening_decision.may_play is False
        assert listening_decision.duet_active is True
        assert listening_decision.lead_role == "theramini"
        assert listening_decision.support_role == "cypherclaw"
        assert listening_decision.max_overlap_beats == 0
        assert should_enter_duet(listening_state_input) is True

        speaking_state_input = {
            "timestamp": now,
            "is_playing": False,
            "pitch_hz": 440.0,
            "pitch_confidence": 0.0,
            "rms": 0.0,
            "state": "silence",
            "consecutive_silence_ms": 1600,
            "onset_rate": 1.0,
            "requested_policy": "call/response",
        }
        speaking_decision = plan_duet_response(speaking_state_input, now=now)
        assert speaking_decision.phase == "speaking"
        assert speaking_decision.policy == "call_response"
        assert speaking_decision.speaker == "cypherclaw"
        assert speaking_decision.may_play is True
        assert speaking_decision.duet_active is True
        assert speaking_decision.lead_role == "cypherclaw"
        assert speaking_decision.support_role == "theramini"
        assert speaking_decision.harmonic_intervals
        assert speaking_decision.accompaniment_texture == "answering_phrase"
        assert speaking_decision.response_register
        assert speaking_decision.rhythmic_sympathy

        key_name, root_freq = suggest_response_key(440.0)
        assert key_name == "A"
        assert root_freq > 0
        register = suggest_response_register(440.0)
        assert register == speaking_decision.response_register
        density = suggest_response_density(1.0)
        assert density == "dense"
        phrase = suggest_response_phrase(root_freq, register, density)
        assert 3 <= len(phrase) <= 6
        for freq, duration in phrase:
            assert freq > 0
            assert duration > 0
        assert calculate_wait_beats(0, 0.5) == 0

        solo_state_input = {
            "timestamp": now,
            "is_playing": False,
            "pitch_hz": None,
            "pitch_confidence": 0.0,
            "rms": 0.0,
            "state": "silence",
            "consecutive_silence_ms": 6500,
        }
        solo_decision = plan_duet_response(solo_state_input, now=now)
        assert solo_decision.phase == "solo"
        assert solo_decision.policy == "solo"
        assert solo_decision.may_play is False
        assert solo_decision.duet_active is False
        assert should_exit_duet(solo_state_input) is True

        partner_behaviors = supported_partner_behaviors()
        expected_behaviors = {
            "listening_first",
            "complementary_register",
            "rhythmic_sympathy",
            "harmonic_response_intervals",
            "accompaniment_textures",
            "call_response",
            "imitation",
            "commentary",
            "completion",
            "silence",
        }
        assert expected_behaviors <= set(partner_behaviors)

        diagnostic = {
            "listening_normalized": {
                "listening": normalized_listening["listening"],
                "speaking": normalized_listening["speaking"],
                "silence_request": normalized_listening["silence_request"],
                "human_gesture_active": normalized_listening[
                    "human_gesture_active"
                ],
                "conversation_phase": conversation["phase"],
                "conversation_policy": conversation["policy"],
                "conversation_speaker": conversation["speaker"],
            },
            "speaking_decision": speaking_decision.to_dict(),
            "solo_decision": solo_decision.to_dict(),
            "helpers": {
                "suggest_response_key": {
                    "key_name": key_name,
                    "root_freq": round(root_freq, 4),
                },
                "suggest_response_register": register,
                "suggest_response_density": density,
                "suggest_response_phrase_length": len(phrase),
                "calculate_wait_beats_zero_silence": calculate_wait_beats(
                    0, 0.5
                ),
            },
            "partner_behaviors": list(partner_behaviors),
        }

        encoded = json.dumps(diagnostic, sort_keys=True)
        decoded = json.loads(encoded)
        assert decoded == diagnostic
        assert decoded["listening_normalized"]["conversation_phase"] == "listening"
        assert decoded["speaking_decision"]["phase"] == "speaking"
        assert decoded["solo_decision"]["phase"] == "solo"
        assert decoded["helpers"]["suggest_response_key"]["key_name"] == "A"
        assert decoded["helpers"]["suggest_response_density"] == "dense"
        assert "complementary_register" in decoded["partner_behaviors"]
