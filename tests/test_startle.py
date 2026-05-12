"""Tests for startle.py — sudden-sound detection and startle response for CypherClaw."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools" / "senseweave"))

import startle as startle_module  # noqa: E402
from startle import (
    detect_startle,
    should_mute_output,
    StartleState,
    startle_cooldown,
    startle_to_face_reaction,
    update_startle,
)


# === detect_startle ===


class TestDetectStartle:
    def test_loud_spike_triggers_startle(self):
        assert detect_startle(current_rms=0.6, baseline_rms=0.05) is True

    def test_normal_level_no_startle(self):
        assert detect_startle(current_rms=0.1, baseline_rms=0.05) is False

    def test_exactly_at_threshold(self):
        # 6x baseline = 0.3, current is exactly 0.3
        result = detect_startle(current_rms=0.3, baseline_rms=0.05)
        # At boundary, should be false (not exceeding)
        assert result is False

    def test_just_above_threshold(self):
        assert detect_startle(current_rms=0.31, baseline_rms=0.05) is True

    def test_custom_threshold(self):
        # 3x threshold: 0.05 * 3 = 0.15
        assert detect_startle(current_rms=0.2, baseline_rms=0.05, threshold_ratio=3.0) is True

    def test_zero_baseline_no_crash(self):
        # Zero baseline should not divide by zero or crash
        result = detect_startle(current_rms=0.5, baseline_rms=0.0)
        assert isinstance(result, bool)

    def test_zero_current_no_startle(self):
        assert detect_startle(current_rms=0.0, baseline_rms=0.05) is False

    def test_both_zero(self):
        assert detect_startle(current_rms=0.0, baseline_rms=0.0) is False

    def test_high_baseline_needs_higher_current(self):
        # baseline 0.5, threshold 6x -> need > 3.0
        assert detect_startle(current_rms=2.0, baseline_rms=0.5) is False
        assert detect_startle(current_rms=3.1, baseline_rms=0.5) is True


# === startle_cooldown ===


class TestStartleCooldown:
    def test_ready_after_cooldown(self):
        past = time.time() - 10.0
        assert startle_cooldown(last_startle_time=past, cooldown_seconds=5.0) is True

    def test_not_ready_during_cooldown(self):
        recent = time.time() - 1.0
        assert startle_cooldown(last_startle_time=recent, cooldown_seconds=5.0) is False

    def test_exactly_at_cooldown_boundary(self):
        boundary = time.time() - 5.0
        # At boundary, should be ready
        result = startle_cooldown(last_startle_time=boundary, cooldown_seconds=5.0)
        assert result is True

    def test_zero_last_startle_time_is_ready(self):
        assert startle_cooldown(last_startle_time=0.0, cooldown_seconds=5.0) is True

    def test_custom_cooldown(self):
        recent = time.time() - 2.0
        assert startle_cooldown(last_startle_time=recent, cooldown_seconds=1.0) is True
        assert startle_cooldown(last_startle_time=recent, cooldown_seconds=3.0) is False


# === StartleState ===


class TestStartleState:
    def test_dataclass_fields(self):
        state = StartleState(
            startled=False,
            startle_count=0,
            last_startle_time=0.0,
            cooldown_active=False,
        )
        assert state.startled is False
        assert state.startle_count == 0
        assert state.last_startle_time == 0.0
        assert state.cooldown_active is False

    def test_default_values(self):
        state = StartleState()
        assert state.startled is False
        assert state.startle_count == 0
        assert state.last_startle_time == 0.0
        assert state.cooldown_active is False


# === update_startle ===


class TestUpdateStartle:
    def test_startle_detected(self):
        state = StartleState()
        new_state = update_startle(state, current_rms=0.6, baseline_rms=0.05)
        assert new_state.startled is True
        assert new_state.startle_count == 1
        assert new_state.last_startle_time > 0.0

    def test_no_startle_quiet(self):
        state = StartleState()
        new_state = update_startle(state, current_rms=0.1, baseline_rms=0.05)
        assert new_state.startled is False
        assert new_state.startle_count == 0

    def test_startle_count_increments(self):
        state = StartleState(startle_count=2, last_startle_time=0.0)
        new_state = update_startle(state, current_rms=0.6, baseline_rms=0.05)
        assert new_state.startle_count == 3

    def test_cooldown_blocks_startle(self):
        recent = time.time()
        state = StartleState(startled=False, startle_count=1, last_startle_time=recent, cooldown_active=True)
        new_state = update_startle(state, current_rms=0.6, baseline_rms=0.05)
        # During cooldown, should not re-startle
        assert new_state.startled is False
        assert new_state.startle_count == 1

    def test_cooldown_expires_allows_startle(self):
        old = time.time() - 10.0
        state = StartleState(startled=False, startle_count=1, last_startle_time=old, cooldown_active=False)
        new_state = update_startle(state, current_rms=0.6, baseline_rms=0.05)
        assert new_state.startled is True
        assert new_state.startle_count == 2

    def test_returns_startle_state(self):
        state = StartleState()
        new_state = update_startle(state, current_rms=0.1, baseline_rms=0.05)
        assert isinstance(new_state, StartleState)

    def test_cooldown_active_set_on_startle(self):
        state = StartleState()
        new_state = update_startle(state, current_rms=0.6, baseline_rms=0.05)
        assert new_state.cooldown_active is True


# === startle_to_face_reaction ===


class TestStartleToFaceReaction:
    def test_startled_reaction(self):
        state = StartleState(startled=True, startle_count=1, last_startle_time=time.time())
        reaction = startle_to_face_reaction(state)
        assert reaction["expression"] == "surprised"
        assert reaction["eye_widen"] is True
        assert reaction["duration_ms"] == 500

    def test_calm_reaction(self):
        state = StartleState(startled=False, startle_count=0)
        reaction = startle_to_face_reaction(state)
        assert reaction["expression"] == "calm"
        assert reaction["eye_widen"] is False

    def test_returns_dict(self):
        state = StartleState()
        reaction = startle_to_face_reaction(state)
        assert isinstance(reaction, dict)
        assert "expression" in reaction
        assert "eye_widen" in reaction
        assert "duration_ms" in reaction


# === should_mute_output ===


class TestShouldMuteOutput:
    def test_mute_after_3_rapid_startles(self):
        now = time.time()
        state = StartleState(
            startled=True,
            startle_count=3,
            last_startle_time=now,
            cooldown_active=True,
        )
        assert should_mute_output(state) is True

    def test_no_mute_with_few_startles(self):
        state = StartleState(startled=True, startle_count=2, last_startle_time=time.time())
        assert should_mute_output(state) is False

    def test_no_mute_with_zero_startles(self):
        state = StartleState()
        assert should_mute_output(state) is False

    def test_no_mute_if_startles_spread_out(self):
        old = time.time() - 60.0  # 60 seconds ago — well outside 30s window
        state = StartleState(startled=False, startle_count=5, last_startle_time=old)
        assert should_mute_output(state) is False

    def test_mute_threshold_exactly_3(self):
        now = time.time()
        state = StartleState(startled=True, startle_count=3, last_startle_time=now)
        assert should_mute_output(state) is True

    def test_mute_above_threshold(self):
        now = time.time()
        state = StartleState(startled=True, startle_count=10, last_startle_time=now)
        assert should_mute_output(state) is True


class StartleEndToEndTests:
    """End-to-end diagnostic coverage for the public startle surface."""

    __test__ = True

    def test_startle_lifecycle_reacts_cools_down_mutes_and_round_trips_json_diagnostic(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        now = {"value": 1_000.0}
        monkeypatch.setattr(startle_module.time, "time", lambda: now["value"])

        baseline_rms = 0.05
        quiet_rms = 0.10
        loud_rms = 0.60
        state = StartleState()

        assert detect_startle(quiet_rms, baseline_rms) is False
        assert startle_cooldown(state.last_startle_time) is True

        quiet_state = update_startle(
            state,
            current_rms=quiet_rms,
            baseline_rms=baseline_rms,
        )
        quiet_face = startle_to_face_reaction(quiet_state)
        assert quiet_state.startled is False
        assert quiet_state.startle_count == 0
        assert quiet_state.cooldown_active is False
        assert quiet_face == {
            "expression": "calm",
            "eye_widen": False,
            "duration_ms": 0,
        }
        assert should_mute_output(quiet_state) is False

        now["value"] = 1_001.0
        assert detect_startle(loud_rms, baseline_rms) is True
        first_startle = update_startle(
            quiet_state,
            current_rms=loud_rms,
            baseline_rms=baseline_rms,
        )
        first_face = startle_to_face_reaction(first_startle)
        assert first_startle.startled is True
        assert first_startle.startle_count == 1
        assert first_startle.last_startle_time == 1_001.0
        assert first_startle.cooldown_active is True
        assert first_face == {
            "expression": "surprised",
            "eye_widen": True,
            "duration_ms": 500,
        }
        assert should_mute_output(first_startle) is False

        now["value"] = 1_002.0
        cooldown_blocked = update_startle(
            first_startle,
            current_rms=0.70,
            baseline_rms=baseline_rms,
        )
        assert cooldown_blocked.startled is False
        assert cooldown_blocked.startle_count == 1
        assert cooldown_blocked.last_startle_time == 1_001.0
        assert cooldown_blocked.cooldown_active is True

        now["value"] = 1_007.1
        second_startle = update_startle(
            cooldown_blocked,
            current_rms=0.65,
            baseline_rms=baseline_rms,
        )
        assert second_startle.startled is True
        assert second_startle.startle_count == 2
        assert should_mute_output(second_startle) is False

        now["value"] = 1_013.0
        third_startle = update_startle(
            second_startle,
            current_rms=0.62,
            baseline_rms=baseline_rms,
        )
        third_face = startle_to_face_reaction(third_startle)
        assert third_startle.startled is True
        assert third_startle.startle_count == 3
        assert len(third_startle._recent_startle_times) == 3
        assert should_mute_output(third_startle) is True
        assert third_face["expression"] == "surprised"
        assert third_face["eye_widen"] is True

        diagnostic = {
            "baseline_rms": baseline_rms,
            "quiet": {
                "rms": quiet_rms,
                "detected": detect_startle(quiet_rms, baseline_rms),
                "state": self._state_snapshot(quiet_state),
                "face": quiet_face,
                "should_mute": should_mute_output(quiet_state),
            },
            "first_startle": {
                "rms": loud_rms,
                "detected": detect_startle(loud_rms, baseline_rms),
                "state": self._state_snapshot(first_startle),
                "face": first_face,
                "should_mute": should_mute_output(first_startle),
            },
            "cooldown_blocked": {
                "state": self._state_snapshot(cooldown_blocked),
                "ready_for_next": startle_cooldown(
                    cooldown_blocked.last_startle_time
                ),
            },
            "third_startle": {
                "state": self._state_snapshot(third_startle),
                "face": third_face,
                "should_mute": should_mute_output(third_startle),
            },
        }
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped == diagnostic
        assert round_tripped["quiet"]["face"]["expression"] == "calm"
        assert round_tripped["first_startle"]["state"]["startle_count"] == 1
        assert round_tripped["cooldown_blocked"]["state"]["cooldown_active"] is True
        assert round_tripped["third_startle"]["state"]["startle_count"] == 3
        assert round_tripped["third_startle"]["should_mute"] is True

    @staticmethod
    def _state_snapshot(state: StartleState) -> dict[str, object]:
        return {
            "startled": state.startled,
            "startle_count": state.startle_count,
            "last_startle_time": state.last_startle_time,
            "cooldown_active": state.cooldown_active,
            "recent_startle_times": list(state._recent_startle_times),
        }
