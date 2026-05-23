"""Tests for SenseweaveVoice — ADSR-controlled texture instrument."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.affective_state_bus import (
    AFFECTIVE_STATE_BUS_INDEX,
    CYPHERCLAW_V2_COUPLING_ENV,
)
from senseweave.synthesis.senseweave_voice import (
    PAD,
    PRESETS,
    RHYTHMIC,
    STAB,
    TIMBRE_MAP,
    SenseweaveVoice,
    read_affective_state_bus,
)


class _ControlBusReader:
    def __init__(self, value: float) -> None:
        self.value = value
        self.read_indices: list[int] = []

    def read_control_bus(self, bus_index: int) -> float:
        self.read_indices.append(bus_index)
        return self.value


class TestAffectiveStateBusReader:
    def test_reader_returns_bus_value_when_coupling_enabled(self) -> None:
        reader = _ControlBusReader(0.62)

        value = read_affective_state_bus(
            reader,
            env={CYPHERCLAW_V2_COUPLING_ENV: "1"},
        )

        assert value == 0.62
        assert reader.read_indices == [AFFECTIVE_STATE_BUS_INDEX]

    def test_reader_returns_zero_without_touching_bus_when_flag_off(self) -> None:
        reader = _ControlBusReader(0.91)

        default_off = read_affective_state_bus(reader, env={})
        explicit_off = read_affective_state_bus(
            reader,
            env={CYPHERCLAW_V2_COUPLING_ENV: "0"},
        )

        assert default_off == 0.0
        assert explicit_off == 0.0
        assert reader.read_indices == []

    def test_reader_clamps_bus_values_when_coupling_enabled(self) -> None:
        enabled_env = {CYPHERCLAW_V2_COUPLING_ENV: "true"}

        assert read_affective_state_bus(
            _ControlBusReader(1.5),
            env=enabled_env,
        ) == 1.0
        assert read_affective_state_bus(
            _ControlBusReader(-0.25),
            env=enabled_env,
        ) == 0.0


class TestADSR:
    def test_pad_is_sustained(self):
        assert not PAD.is_percussive
        assert PAD.sustain > 0.5

    def test_stab_is_percussive(self):
        assert STAB.is_percussive
        assert STAB.sustain == 0.0

    def test_rhythmic_is_percussive(self):
        assert RHYTHMIC.is_percussive

    def test_total_duration(self):
        assert PAD.total_duration == PAD.attack + PAD.decay

    def test_all_presets_exist(self):
        assert len(PRESETS) >= 6
        for name in ["pad", "swell", "stab", "rhythmic", "breath", "shimmer"]:
            assert name in PRESETS

    def test_frozen(self):
        try:
            PAD.attack = 99
            assert False, "Should be frozen"
        except AttributeError:
            pass


class TestSenseweaveVoice:
    def _make_voice(self):
        osc = MagicMock()
        voice = SenseweaveVoice(osc=osc)
        return voice, osc

    def test_note_on_sends_osc(self):
        voice, osc = self._make_voice()
        nid = voice.note_on(220.0, 0.06)
        assert isinstance(nid, int)
        assert osc.send_message.called
        args = osc.send_message.call_args[0]
        assert args[0] == "/s_new"
        assert args[1][0] == "sw_pad"  # default timbre
        assert "freq" in args[1]
        freq_idx = args[1].index("freq")
        assert args[1][freq_idx + 1] == 220.0

    def test_note_on_returns_node_id(self):
        voice, osc = self._make_voice()
        nid = voice.note_on(440.0)
        assert isinstance(nid, int)
        assert nid > 0

    def test_note_off_frees_node(self):
        voice, osc = self._make_voice()
        nid = voice.note_on(440.0)
        voice.note_off(nid)
        # Should have sent /n_free
        calls = [c[0] for c in osc.send_message.call_args_list]
        assert any("/n_free" in str(c) for c in calls)

    def test_note_off_all(self):
        voice, osc = self._make_voice()
        voice.note_on(220.0)
        voice.note_on(330.0)
        voice.note_on(440.0)
        assert voice.active_count == 3
        voice.note_off()
        assert voice.active_count == 0

    def test_set_preset(self):
        voice, osc = self._make_voice()
        voice.set_preset("stab")
        assert voice.adsr.is_percussive
        assert voice.timbre == "stab"

    def test_set_adsr_custom(self):
        voice, osc = self._make_voice()
        voice.set_adsr(0.1, 0.2, 0.5, 1.0)
        assert voice.adsr.attack == 0.1
        assert voice.adsr.sustain == 0.5

    def test_set_adsr_clamps(self):
        voice, osc = self._make_voice()
        voice.set_adsr(-1, -1, 2.0, -1)
        assert voice.adsr.attack >= 0.001
        assert voice.adsr.sustain <= 1.0
        assert voice.adsr.release >= 0.001

    def test_set_timbre(self):
        voice, osc = self._make_voice()
        voice.set_timbre("warm")
        assert voice.timbre == "warm"

    def test_chord(self):
        voice, osc = self._make_voice()
        nids = voice.chord([220.0, 330.0, 440.0])
        assert len(nids) == 3
        assert voice.active_count == 3

    def test_polyphony_limit(self):
        voice, osc = self._make_voice()
        voice.max_polyphony = 4
        for i in range(10):
            voice.note_on(220.0 + i * 10)
        assert voice.active_count <= 4

    def test_is_playing(self):
        voice, osc = self._make_voice()
        assert not voice.is_playing
        voice.note_on(440.0)
        assert voice.is_playing
        voice.release_all()
        assert not voice.is_playing

    def test_no_osc_doesnt_crash(self):
        voice = SenseweaveVoice(osc=None)
        nid = voice.note_on(440.0, 0.05)
        assert nid > 0
        voice.note_off(nid)
        voice.release_all()


class TestConvenienceMethods:
    def _make_voice(self):
        osc = MagicMock()
        return SenseweaveVoice(osc=osc), osc

    def test_pad_chord(self):
        voice, osc = self._make_voice()
        nids = voice.pad_chord(146.8, 220.0)
        assert len(nids) == 2
        # Should use pad envelope (long attack)
        args = osc.send_message.call_args_list[0][0][1]
        attack_idx = args.index("attack")
        assert args[attack_idx + 1] >= 2.0  # pad has long attack

    def test_stab_chord(self):
        voice, osc = self._make_voice()
        nids = voice.stab_chord(146.8, 185.0, 220.0)
        assert len(nids) == 3

    def test_rhythmic_hit(self):
        voice, osc = self._make_voice()
        nid = voice.rhythmic_hit(146.8)
        assert isinstance(nid, int)

    def test_breath_tone(self):
        voice, osc = self._make_voice()
        nid = voice.breath_tone(220.0)
        assert isinstance(nid, int)
        assert voice.active_count == 1

    def test_shimmer_note(self):
        voice, osc = self._make_voice()
        nid = voice.shimmer_note(440.0)
        assert isinstance(nid, int)
        assert voice.active_count == 1

    def test_swell(self):
        voice, osc = self._make_voice()
        nid = voice.swell(330.0)
        assert isinstance(nid, int)
        assert voice.active_count == 1


class TestTimbreMap:
    def test_all_presets_have_timbres(self):
        for preset_name in PRESETS:
            assert preset_name in TIMBRE_MAP, f"No timbre for preset {preset_name}"

    def test_timbres_are_valid_synths(self):
        valid_synths = {"sw_pad", "sw_pluck", "sw_bowed", "sw_kotekan",
                        "sw_gong", "sw_bell_warm", "sw_choir", "sw_breath"}
        for timbre, synth in TIMBRE_MAP.items():
            assert synth in valid_synths, f"Unknown synth {synth} for timbre {timbre}"
