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
    DEFAULT_COUPLING_STRENGTH,
    PAD,
    PRESETS,
    RHYTHMIC,
    STAB,
    TIMBRE_MAP,
    SenseweaveVoice,
    coupling_multiplier_from_bus_value,
    read_affective_state_bus,
    scale_modulator_depths,
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


class TestCouplingMultiplier:
    def test_default_strength_boundary_values(self) -> None:
        assert coupling_multiplier_from_bus_value(0.0) == 1.0
        assert coupling_multiplier_from_bus_value(0.5) == 1.25
        assert coupling_multiplier_from_bus_value(1.0) == 1.5

    def test_clamps_bus_value_and_coupling_strength(self) -> None:
        assert coupling_multiplier_from_bus_value(-0.5) == 1.0
        assert coupling_multiplier_from_bus_value(2.0) == 1.5
        assert coupling_multiplier_from_bus_value(
            1.0,
            coupling_strength=-0.25,
        ) == 1.0
        assert coupling_multiplier_from_bus_value(
            1.0,
            coupling_strength=2.0,
        ) == 2.0


class TestRenderTimeModulatorDepthScaling:
    def test_scales_depth_mapping_without_mutating_input(self) -> None:
        nominal_depths = {
            "vib_depth": 0.25,
            "trem_depth": 0.5,
            "spectral_granulation_amount": 0.125,
        }

        scaled = scale_modulator_depths(nominal_depths, multiplier=1.5)

        assert scaled == {
            "vib_depth": 0.375,
            "trem_depth": 0.75,
            "spectral_granulation_amount": 0.1875,
        }
        assert nominal_depths == {
            "vib_depth": 0.25,
            "trem_depth": 0.5,
            "spectral_granulation_amount": 0.125,
        }
        assert scaled is not nominal_depths
        assert scale_modulator_depths({}, multiplier=1.5) == {}
        assert scale_modulator_depths({"vib_depth": 0.25}, multiplier=0.0) == {
            "vib_depth": 0.0,
        }

    def test_note_on_applies_multiplier_to_depth_args_across_timbres(self) -> None:
        nominal_depths = {
            "vib_depth": 0.25,
            "trem_depth": 0.5,
        }

        for timbre, synth in TIMBRE_MAP.items():
            osc = MagicMock()
            voice = SenseweaveVoice(osc=osc, timbre=timbre)

            voice.note_on(
                220.0,
                modulator_depths=nominal_depths,
                coupling_multiplier=1.5,
            )

            sent_args = osc.send_message.call_args[0][1]
            rendered_params = dict(zip(sent_args[4::2], sent_args[5::2], strict=True))
            assert sent_args[0] == synth
            assert rendered_params["vib_depth"] == 0.375
            assert rendered_params["trem_depth"] == 0.75


class TestAffectiveCouplingIntegration:
    def test_flag_on_known_bus_value_scales_depths_across_all_timbres(self) -> None:
        known_bus_value = 0.5
        nominal_depths = {
            "vib_depth": 0.25,
            "trem_depth": 0.5,
            "spectral_granulation_amount": 0.125,
        }
        expected_multiplier = 1.0 + (DEFAULT_COUPLING_STRENGTH * known_bus_value)
        enabled_env = {CYPHERCLAW_V2_COUPLING_ENV: "1"}

        for timbre, synth in TIMBRE_MAP.items():
            reader = _ControlBusReader(known_bus_value)
            osc = MagicMock()
            voice = SenseweaveVoice(osc=osc, timbre=timbre)

            voice.note_on_with_affective_coupling(
                220.0,
                modulator_depths=nominal_depths,
                control_bus_reader=reader,
                env=enabled_env,
            )

            sent_args = osc.send_message.call_args[0][1]
            rendered_params = dict(zip(sent_args[4::2], sent_args[5::2], strict=True))
            assert sent_args[0] == synth
            assert reader.read_indices == [AFFECTIVE_STATE_BUS_INDEX]
            assert rendered_params["vib_depth"] == 0.25 * expected_multiplier
            assert rendered_params["trem_depth"] == 0.5 * expected_multiplier
            assert (
                rendered_params["spectral_granulation_amount"]
                == 0.125 * expected_multiplier
            )

    def test_flag_off_preserves_baseline_depths_across_all_timbres(self) -> None:
        nominal_depths = {
            "vib_depth": 0.25,
            "trem_depth": 0.5,
            "spectral_granulation_amount": 0.125,
        }
        disabled_env = {CYPHERCLAW_V2_COUPLING_ENV: "0"}

        for timbre, synth in TIMBRE_MAP.items():
            reader = _ControlBusReader(0.9)
            osc = MagicMock()
            voice = SenseweaveVoice(osc=osc, timbre=timbre)

            voice.note_on_with_affective_coupling(
                220.0,
                modulator_depths=nominal_depths,
                control_bus_reader=reader,
                env=disabled_env,
            )

            sent_args = osc.send_message.call_args[0][1]
            rendered_params = dict(zip(sent_args[4::2], sent_args[5::2], strict=True))
            assert sent_args[0] == synth
            assert reader.read_indices == []
            assert rendered_params["vib_depth"] == 0.25
            assert rendered_params["trem_depth"] == 0.5
            assert rendered_params["spectral_granulation_amount"] == 0.125


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


class TestFxBusRouting:
    """Voice spawn must carry the per-voice fx_bus_id from VoiceReverbProfile."""

    def test_note_on_routes_each_voice_to_its_assigned_fx_bus_id(self) -> None:
        from cypherclaw.space_reverb import VOICE_REVERB_PROFILES

        for timbre, synth in TIMBRE_MAP.items():
            normalized = synth[3:] if synth.startswith("sw_") else synth
            profile = VOICE_REVERB_PROFILES.get(normalized)
            if profile is None:
                continue
            osc = MagicMock()
            voice = SenseweaveVoice(osc=osc, timbre=timbre)
            voice.note_on(220.0)
            sent_args = osc.send_message.call_args[0][1]
            assert "fx_bus_id" in sent_args, (
                f"voice {timbre}/{synth} missing fx_bus_id in /s_new args"
            )
            idx = sent_args.index("fx_bus_id")
            assert sent_args[idx + 1] == profile.fx_bus_id

    def test_note_on_skips_fx_bus_id_for_voices_without_a_profile(self) -> None:
        from cypherclaw.space_reverb import VOICE_REVERB_PROFILES

        for timbre, synth in TIMBRE_MAP.items():
            normalized = synth[3:] if synth.startswith("sw_") else synth
            if normalized in VOICE_REVERB_PROFILES:
                continue
            osc = MagicMock()
            voice = SenseweaveVoice(osc=osc, timbre=timbre)
            voice.note_on(220.0)
            sent_args = osc.send_message.call_args[0][1]
            assert "fx_bus_id" not in sent_args, (
                f"voice {timbre}/{synth} should not carry fx_bus_id "
                "without a VoiceReverbProfile"
            )

    def test_note_on_rejects_other_voices_fx_bus_ids(self) -> None:
        """No voice may emit on a bus that belongs to a different voice.

        For each profiled timbre, the `/s_new` args must carry the voice's
        own `fx_bus_id` and must NOT match any other voice's profile bus.
        Guards against profile-lookup drift accidentally routing one
        voice's signal through another voice's reverb return.
        """
        from cypherclaw.space_reverb import VOICE_REVERB_PROFILES

        all_bus_ids = {p.fx_bus_id for p in VOICE_REVERB_PROFILES.values()}

        for timbre, synth in TIMBRE_MAP.items():
            normalized = synth[3:] if synth.startswith("sw_") else synth
            own_profile = VOICE_REVERB_PROFILES.get(normalized)
            if own_profile is None:
                continue
            osc = MagicMock()
            voice = SenseweaveVoice(osc=osc, timbre=timbre)
            voice.note_on(220.0)
            sent_args = osc.send_message.call_args[0][1]

            assert sent_args.count("fx_bus_id") == 1, (
                f"voice {timbre}/{synth} must declare exactly one fx_bus_id"
            )
            emitted_bus = sent_args[sent_args.index("fx_bus_id") + 1]
            foreign_buses = all_bus_ids - {own_profile.fx_bus_id}
            assert emitted_bus not in foreign_buses, (
                f"voice {timbre}/{synth} leaked onto another voice's bus "
                f"{emitted_bus} (expected {own_profile.fx_bus_id})"
            )
            assert emitted_bus == own_profile.fx_bus_id

    def test_set_timbre_reroutes_to_the_new_voices_fx_bus_id(self) -> None:
        """Swapping timbre must re-route to the new voice's profile bus.

        A stale bus id from a prior timbre must not be smuggled into the
        next `/s_new` emission — the routing is read from the live
        profile at spawn time.
        """
        from cypherclaw.space_reverb import VOICE_REVERB_PROFILES

        profiled_timbres = [
            (timbre, synth)
            for timbre, synth in TIMBRE_MAP.items()
            if (synth[3:] if synth.startswith("sw_") else synth)
            in VOICE_REVERB_PROFILES
        ]
        assert len(profiled_timbres) >= 2, (
            "need at least two profiled timbres to exercise re-routing"
        )

        first_timbre, first_synth = profiled_timbres[0]
        second_timbre, second_synth = profiled_timbres[1]
        first_bus = VOICE_REVERB_PROFILES[
            first_synth[3:] if first_synth.startswith("sw_") else first_synth
        ].fx_bus_id
        second_bus = VOICE_REVERB_PROFILES[
            second_synth[3:] if second_synth.startswith("sw_") else second_synth
        ].fx_bus_id
        assert first_bus != second_bus

        osc = MagicMock()
        voice = SenseweaveVoice(osc=osc, timbre=first_timbre)
        voice.note_on(220.0)
        first_args = osc.send_message.call_args[0][1]
        assert first_args[first_args.index("fx_bus_id") + 1] == first_bus

        voice.set_timbre(second_timbre)
        voice.note_on(330.0)
        second_args = osc.send_message.call_args[0][1]
        assert second_args[0] == second_synth
        assert second_args[second_args.index("fx_bus_id") + 1] == second_bus
        assert first_bus not in second_args[4:], (
            f"stale fx_bus_id {first_bus} from {first_timbre} leaked into "
            f"{second_timbre} /s_new args"
        )
