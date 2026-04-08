"""Tests for the inner life loop."""
from __future__ import annotations

import json
import os
import sys
import time


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from inner_life.world_model import WorldModel, read_world, _read_state
from inner_life.inner_state import InnerState, save_volatile
from inner_life.presence import update_presence
from inner_life.narrative_arc import update_arc, start_new_cycle, energy_for_phase
from inner_life.mood import evolve_mood
from inner_life.decision_engine import decide
from inner_life.actions import Action


# ---------------------------------------------------------------------------
# WorldModel
# ---------------------------------------------------------------------------

class TestWorldModel:
    def test_default_values(self):
        w = WorldModel()
        assert w.energy == 0.5
        assert w.someone_here is False
        assert w.current_key == "C"

    def test_read_state_missing_file(self, tmp_path):
        assert _read_state(str(tmp_path / "nonexistent.json")) == {}

    def test_read_state_valid(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text(json.dumps({"key": "D", "movement": "Theme"}))
        result = _read_state(str(f))
        assert result["key"] == "D"

    def test_read_state_corrupt(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json{{{")
        assert _read_state(str(f)) == {}

    def test_read_state_stale(self, tmp_path):
        f = tmp_path / "old.json"
        f.write_text(json.dumps({"data": 1}))
        os.utime(str(f), (0, 0))  # set mtime to epoch
        assert _read_state(str(f), max_age=60) == {}

    def test_stale_sources_tracked(self):
        # read_world will have stale sources since /tmp files don't exist in test
        w = read_world()
        assert len(w.stale_sources) > 0

    def test_time_of_day(self):
        w = read_world()
        assert w.time_of_day in ("night", "dawn", "morning", "afternoon", "evening")


# ---------------------------------------------------------------------------
# InnerState
# ---------------------------------------------------------------------------

class TestInnerState:
    def test_defaults(self):
        s = InnerState()
        assert s.mood == 0.0
        assert s.mode == "solitary"

    def test_add_observation(self):
        s = InnerState()
        s.add_observation("test")
        assert "test" in s.recent_observations

    def test_observations_capped(self):
        s = InnerState()
        for i in range(25):
            s.add_observation(f"obs {i}")
        assert len(s.recent_observations) == 20

    def test_cooldown(self):
        s = InnerState()
        assert s.cooldown_ok("last_face_message_at", 60)
        s.mark_cooldown("last_face_message_at")
        assert not s.cooldown_ok("last_face_message_at", 60)

    def test_add_event(self):
        s = InnerState()
        s.add_event("test_event", "detail")
        assert s.today_events[0]["type"] == "test_event"

    def test_add_opinion(self):
        s = InnerState()
        s.add_opinion("D major", "too repetitive")
        assert s.opinions_formed[0]["opinion"] == "too repetitive"

    def test_save_volatile(self, tmp_path):
        import inner_life.inner_state as mod
        old_path = mod.VOLATILE_PATH
        mod.VOLATILE_PATH = str(tmp_path / "state.json")
        try:
            s = InnerState(mood=0.7, mode="engaged")
            save_volatile(s)
            data = json.loads((tmp_path / "state.json").read_text())
            assert data["mood"] == 0.7
            assert data["mode"] == "engaged"
        finally:
            mod.VOLATILE_PATH = old_path


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------

class TestPresence:
    def test_solitary_to_aware(self):
        w = WorldModel(someone_here=True)
        s = InnerState(mode="solitary", mode_entered_at=time.time() - 100)
        result = update_presence(w, s)
        assert s.mode == "aware"
        assert result is not None

    def test_aware_to_engaged(self):
        w = WorldModel(someone_here=True)
        s = InnerState(mode="aware", mode_entered_at=time.time() - 60)
        update_presence(w, s)
        assert s.mode == "engaged"

    def test_aware_to_solitary(self):
        w = WorldModel(someone_here=False)
        s = InnerState(mode="aware", mode_entered_at=time.time() - 120)
        update_presence(w, s)
        assert s.mode == "solitary"

    def test_engaged_to_performing(self):
        w = WorldModel(someone_here=True, theramini_playing=True)
        s = InnerState(mode="engaged", mode_entered_at=time.time() - 10)
        update_presence(w, s)
        assert s.mode == "performing"

    def test_performing_exits_after_timeout(self):
        w = WorldModel(someone_here=True, theramini_playing=False)
        s = InnerState(mode="performing", mode_entered_at=time.time() - 120)
        update_presence(w, s)
        assert s.mode == "engaged"

    def test_no_transition_stays_same(self):
        w = WorldModel(someone_here=False)
        s = InnerState(mode="solitary", mode_entered_at=time.time())
        result = update_presence(w, s)
        assert result is None
        assert s.mode == "solitary"


# ---------------------------------------------------------------------------
# Narrative Arc
# ---------------------------------------------------------------------------

class TestNarrativeArc:
    def test_arc_position_advances(self):
        s = InnerState(cycle_started_at=time.time() - 900)  # 15 min in
        update_arc(s)
        assert 0.45 < s.arc_position < 0.55

    def test_cycle_completes(self):
        s = InnerState(cycle_started_at=time.time() - 2000)  # past 30 min
        assert update_arc(s) is True

    def test_phase_names(self):
        s = InnerState(cycle_started_at=time.time())
        update_arc(s)
        assert s.arc_phase == "build"

    def test_start_new_cycle(self):
        s = InnerState(cycle_id=5)
        start_new_cycle(s)
        assert s.cycle_id == 6
        assert s.arc_position == 0.0

    def test_energy_for_phase(self):
        assert energy_for_phase("rest") < energy_for_phase("climax")


# ---------------------------------------------------------------------------
# Mood
# ---------------------------------------------------------------------------

class TestMood:
    def test_theramini_lifts_mood(self):
        w = WorldModel(theramini_playing=True, timestamp=time.time())
        s = InnerState(mood=0.0, mode="engaged", mode_entered_at=time.time())
        evolve_mood(w, s)
        assert s.mood > 0.0

    def test_startle_drops_mood(self):
        w = WorldModel(startle_active=True, timestamp=time.time())
        s = InnerState(mood=0.5, mode="solitary", mode_entered_at=time.time())
        evolve_mood(w, s)
        assert s.mood < 0.5

    def test_curiosity_recharges_in_solitude(self):
        w = WorldModel(timestamp=time.time())
        s = InnerState(curiosity=0.3, mode="solitary", mode_entered_at=time.time())
        evolve_mood(w, s)
        assert s.curiosity > 0.3

    def test_mood_clamped(self):
        w = WorldModel(theramini_playing=True, midi_active=True, timestamp=time.time())
        s = InnerState(mood=0.99, mode="performing", mode_entered_at=time.time())
        for _ in range(100):
            evolve_mood(w, s)
        assert s.mood <= 1.0


# ---------------------------------------------------------------------------
# Decision Engine
# ---------------------------------------------------------------------------

class TestDecisions:
    def test_returns_list(self):
        w = WorldModel(timestamp=time.time())
        s = InnerState(mode="solitary", mode_entered_at=time.time() - 100,
                       arc_phase="climax")
        result = decide(w, s)
        assert isinstance(result, list)

    def test_max_two_actions(self):
        w = WorldModel(timestamp=time.time())
        s = InnerState(mode="solitary", mode_entered_at=time.time() - 100,
                       arc_phase="climax")
        # Run many times to check max
        for _ in range(20):
            result = decide(w, s)
            assert len(result) <= 2

    def test_rest_phase_quiet(self):
        w = WorldModel(timestamp=time.time())
        s = InnerState(mode="solitary", arc_phase="rest",
                       mode_entered_at=time.time() - 100)
        # Rest phase should produce few actions
        action_count = sum(len(decide(w, s)) for _ in range(20))
        assert action_count < 10  # mostly empty


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

class TestActions:
    def test_action_creation(self):
        a = Action(action_type="face_message", payload={"text": "hi"},
                   cooldown_key="last_face_message_at", min_cooldown_s=60)
        assert a.action_type == "face_message"

    def test_cooldown_prevents_dispatch(self):
        from inner_life.actions import dispatch
        s = InnerState()
        s.mark_cooldown("last_face_message_at")
        a = Action(action_type="face_message", payload={"text": "hi"},
                   cooldown_key="last_face_message_at", min_cooldown_s=60)
        assert dispatch(a, s) is False
