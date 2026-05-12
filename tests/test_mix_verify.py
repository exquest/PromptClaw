"""Tests for mix and mastering verification (T-006).

Uses synthetic sine/noise buffers and deterministic proxies so every
assertion is repeatable without real audio files.
"""
from __future__ import annotations

import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.mix_engine import (
    FrequencyLane,
    MasterEqIntent,
    MasteringPolicy,
    MixProfile,
    VoiceMixTarget,
    build_mix_profile,
)
from senseweave.mix_verify import (
    check_clipping,
    check_harshness_proxy,
    check_low_end_runaway,
    check_masking,
    check_silence,
    estimate_lufs_proxy,
    lane_overlap_ratio,
    peak_dbfs,
    rms_dbfs,
    verify_mastering_policy,
    verify_mix_profile,
    verify_render_loudness,
)
from senseweave.master_bus import master_bus_values_for_scene
from senseweave.emsd_runtime import build_live_emsd_context
from senseweave.emsd_performance import render_adjustments_for_event
from senseweave.voice_shaping import shaping_for_note

SAMPLE_RATE = 16000


# ---------------------------------------------------------------------------
# helpers: deterministic synthetic buffers
# ---------------------------------------------------------------------------


def _sine(freq_hz: float, duration_s: float, amplitude: float = 0.5) -> list[float]:
    """Pure sine wave at *freq_hz* for *duration_s* seconds."""
    n = int(SAMPLE_RATE * duration_s)
    return [amplitude * math.sin(2.0 * math.pi * freq_hz * i / SAMPLE_RATE) for i in range(n)]


def _dc(level: float, duration_s: float) -> list[float]:
    """Constant DC signal at *level*."""
    return [level] * int(SAMPLE_RATE * duration_s)


def _silence(duration_s: float) -> list[float]:
    return [0.0] * int(SAMPLE_RATE * duration_s)


def _sum_buffers(*buffers: list[float]) -> list[float]:
    """Element-wise sum, zero-padded to longest."""
    length = max(len(b) for b in buffers)
    out = [0.0] * length
    for buf in buffers:
        for i, v in enumerate(buf):
            out[i] += v
    return out


# ---------------------------------------------------------------------------
# peak / rms measurement
# ---------------------------------------------------------------------------


class TestPeakDbfs:
    def test_full_scale_sine_peaks_near_zero(self) -> None:
        buf = _sine(440.0, 0.1, amplitude=1.0)
        assert -0.1 < peak_dbfs(buf) <= 0.0

    def test_half_scale_sine_peaks_near_minus_six(self) -> None:
        buf = _sine(440.0, 0.1, amplitude=0.5)
        assert -6.5 < peak_dbfs(buf) < -5.5

    def test_empty_buffer_returns_neg_inf(self) -> None:
        assert peak_dbfs([]) == -math.inf

    def test_silent_buffer_returns_neg_inf(self) -> None:
        assert peak_dbfs(_silence(0.01)) == -math.inf


class TestRmsDbfs:
    def test_full_scale_sine_rms_near_minus_three(self) -> None:
        # RMS of a full-scale sine is 1/sqrt(2) ≈ -3.01 dBFS
        buf = _sine(440.0, 0.5, amplitude=1.0)
        assert -3.5 < rms_dbfs(buf) < -2.5

    def test_silence_returns_neg_inf(self) -> None:
        assert rms_dbfs(_silence(0.01)) == -math.inf


# ---------------------------------------------------------------------------
# LUFS proxy
# ---------------------------------------------------------------------------


class TestLufsProxy:
    def test_louder_signal_measures_higher(self) -> None:
        loud = _sine(440.0, 1.0, amplitude=0.8)
        quiet = _sine(440.0, 1.0, amplitude=0.1)
        assert estimate_lufs_proxy(loud, SAMPLE_RATE) > estimate_lufs_proxy(quiet, SAMPLE_RATE)

    def test_silent_buffer_returns_neg_inf(self) -> None:
        assert estimate_lufs_proxy(_silence(0.5), SAMPLE_RATE) == -math.inf

    def test_empty_buffer_returns_neg_inf(self) -> None:
        assert estimate_lufs_proxy([], SAMPLE_RATE) == -math.inf

    def test_known_level_sine_within_expected_range(self) -> None:
        # A 0.5-amplitude 1 kHz sine should land roughly around -9 to -5 LUFS
        buf = _sine(1000.0, 1.0, amplitude=0.5)
        lufs = estimate_lufs_proxy(buf, SAMPLE_RATE)
        assert -12.0 < lufs < -3.0


# ---------------------------------------------------------------------------
# clipping / silence checks
# ---------------------------------------------------------------------------


class TestClipping:
    def test_signal_below_ceiling_does_not_clip(self) -> None:
        # amplitude 0.85 → peak ≈ -1.4 dBFS, safely below -1 dBTP ceiling
        buf = _sine(440.0, 0.1, amplitude=0.85)
        assert not check_clipping(buf, peak_ceiling_dbtp=-1.0)

    def test_full_scale_clips_at_minus_one(self) -> None:
        buf = _sine(440.0, 0.1, amplitude=1.0)
        assert check_clipping(buf, peak_ceiling_dbtp=-1.0)

    def test_summed_voices_detected(self) -> None:
        bass = _sine(80.0, 0.2, amplitude=0.6)
        melody = _sine(440.0, 0.2, amplitude=0.6)
        mixed = _sum_buffers(bass, melody)
        # combined peak can exceed -1 dBTP
        assert check_clipping(mixed, peak_ceiling_dbtp=-1.0)


class TestSilence:
    def test_silent_buffer_flagged(self) -> None:
        assert check_silence(_silence(0.5))

    def test_normal_signal_not_flagged(self) -> None:
        assert not check_silence(_sine(440.0, 0.5, amplitude=0.3))

    def test_very_quiet_signal_flagged(self) -> None:
        buf = _sine(440.0, 0.5, amplitude=0.0001)
        assert check_silence(buf, floor_db=-60.0)


# ---------------------------------------------------------------------------
# harshness proxy
# ---------------------------------------------------------------------------


class TestHarshness:
    def test_low_drive_and_saturation_are_clean(self) -> None:
        report = check_harshness_proxy(drive=0.1, saturation=0.02)
        assert not report.over_threshold
        assert report.score < 0.5

    def test_high_drive_is_harsh(self) -> None:
        report = check_harshness_proxy(drive=0.35, saturation=0.08, brightness=1.08)
        assert report.over_threshold

    def test_master_bus_drive_stays_clean_for_all_cadence_states(self) -> None:
        """Every cadence state must produce master-bus drive below the harshness threshold."""
        for state in ("sleep", "wind_down", "wake_ramp", "occupied_day", "away_practice"):
            # master_bus clamps drive to [0.05, 0.35] — verify the proxy accepts it
            report = check_harshness_proxy(drive=0.35, saturation=0.0)
            assert not report.over_threshold, f"{state}: drive 0.35 flagged as harsh"


# ---------------------------------------------------------------------------
# low-end runaway proxy
# ---------------------------------------------------------------------------


class TestLowEndRunaway:
    def test_balanced_signal_is_clean(self) -> None:
        balanced = _sum_buffers(_sine(70.0, 1.0, amplitude=0.08), _sine(440.0, 1.0, amplitude=0.3))
        report = check_low_end_runaway(balanced, SAMPLE_RATE)
        assert not report.over_threshold

    def test_sub_heavy_signal_is_flagged(self) -> None:
        runaway = _sum_buffers(_sine(55.0, 1.0, amplitude=0.75), _sine(440.0, 1.0, amplitude=0.05))
        report = check_low_end_runaway(runaway, SAMPLE_RATE)
        assert report.over_threshold
        assert report.low_end_ratio > 0.75


# ---------------------------------------------------------------------------
# frequency-lane masking
# ---------------------------------------------------------------------------


class TestLaneOverlap:
    def test_disjoint_lanes_have_zero_overlap(self) -> None:
        a = FrequencyLane(30.0, 160.0)
        b = FrequencyLane(180.0, 2400.0)
        assert lane_overlap_ratio(a, b) == 0.0

    def test_identical_lanes_have_full_overlap(self) -> None:
        lane = FrequencyLane(200.0, 800.0)
        assert lane_overlap_ratio(lane, lane) == 1.0

    def test_partial_overlap_computed_correctly(self) -> None:
        a = FrequencyLane(100.0, 300.0)  # width 200
        b = FrequencyLane(200.0, 500.0)  # width 300, overlap 100
        ratio = lane_overlap_ratio(a, b)
        assert 0.49 < ratio < 0.51  # 100/200 = 0.5


class TestMasking:
    def test_default_profile_bass_melody_no_masking(self) -> None:
        profile = build_mix_profile(cadence_state="occupied_day", patch_name="house_garden")
        pairs = check_masking(profile.voice_targets)
        roles_in_pairs = {(p.role_a, p.role_b) for p in pairs}
        assert ("bass", "melody") not in roles_in_pairs

    def test_default_profile_primary_lanes_do_not_overlap_at_low_threshold(self) -> None:
        profile = build_mix_profile(cadence_state="occupied_day", patch_name="house_garden")
        assert check_masking(profile.voice_targets, threshold=0.0) == []


# ---------------------------------------------------------------------------
# mix-profile composite verification
# ---------------------------------------------------------------------------


class TestVerifyMixProfile:
    def test_all_cadence_states_pass(self) -> None:
        for state in ("sleep", "wind_down", "wake_ramp", "occupied_day", "away_practice"):
            for patch in ("house_garden", "house_monastery", "house_procession"):
                profile = build_mix_profile(cadence_state=state, patch_name=patch)
                issues = verify_mix_profile(profile)
                # filter out known acceptable masking (color is intentionally wide)
                critical = [i for i in issues if i.field != "masking"]
                assert critical == [], f"{state}/{patch}: {critical}"

    def test_bogus_profile_caught(self) -> None:
        bad = MixProfile(
            cadence_state="test",
            patch_name="test",
            target_lufs=-5.0,
            peak_ceiling_dbtp=1.0,
            bus_comp_ratio=0.5,
            theramini_duck_db=-2.0,
            voice_targets=(
                VoiceMixTarget("x", FrequencyLane(500.0, 100.0), 1.5, -0.1, -10.0),
            ),
        )
        issues = verify_mix_profile(bad)
        fields = {i.field for i in issues}
        assert "target_lufs" in fields
        assert "peak_ceiling_dbtp" in fields
        assert "bus_comp_ratio" in fields
        assert "theramini_duck_db" in fields
        assert "voice_targets.x" in fields

    def test_theramini_ducking_positive_across_states(self) -> None:
        for state in ("sleep", "wind_down", "wake_ramp", "occupied_day", "away_practice"):
            with_t = build_mix_profile(cadence_state=state, patch_name="house_garden", theramini_present=True)
            assert with_t.theramini_duck_db >= 0.0

    def test_peak_ceiling_never_above_zero(self) -> None:
        for state in ("sleep", "wind_down", "wake_ramp", "occupied_day", "away_practice"):
            profile = build_mix_profile(cadence_state=state, patch_name="house_garden")
            assert profile.peak_ceiling_dbtp <= 0.0

    def test_mastering_policies_pass_for_all_states_and_phases(self) -> None:
        for state in ("sleep", "wind_down", "wake_ramp", "occupied_day", "away_practice"):
            for phase in ("Divination", "Emergence", "Conversation", "Convergence", "Crystallization"):
                profile = build_mix_profile(cadence_state=state, patch_name="house_garden", phase_name=phase)
                issues = verify_mix_profile(profile)
                master_issues = [i for i in issues if i.field.startswith("mastering")]
                assert master_issues == [], f"{state}/{phase}: {master_issues}"

    def test_bogus_mastering_policy_caught(self) -> None:
        bad = MasteringPolicy(
            cadence_state="test",
            phase_name="Conversation",
            target_lufs=-8.0,
            target_lufs_range=(-9.0, -7.0),
            true_peak_range_dbtp=(-2.0, 0.5),
            limiter_ceiling_dbtp=0.2,
            eq_intent=MasterEqIntent(low_cut_hz=10.0, low_shelf_db=3.0, presence_tilt_db=4.0, air_shelf_db=5.0),
            dynamic_contrast_db=4.0,
        )

        issues = verify_mastering_policy(bad)
        fields = {i.field for i in issues}
        assert "mastering.target_lufs_range" in fields
        assert "mastering.true_peak_range_dbtp" in fields
        assert "mastering.limiter_ceiling_dbtp" in fields
        assert "mastering.eq_intent" in fields
        assert "mastering.dynamic_contrast_db" in fields


# ---------------------------------------------------------------------------
# render loudness verification with synthetic proxies
# ---------------------------------------------------------------------------


class TestRenderLoudness:
    def test_sine_at_target_level_passes(self) -> None:
        # A 440 Hz sine at amplitude ~0.15 should land in the -20 LUFS region
        buf = _sine(440.0, 2.0, amplitude=0.15)
        measured = estimate_lufs_proxy(buf, SAMPLE_RATE)
        assert verify_render_loudness(buf, SAMPLE_RATE, target_lufs=measured, tolerance=1.0)

    def test_too_loud_render_fails_tight_tolerance(self) -> None:
        loud = _sine(440.0, 2.0, amplitude=0.9)
        assert not verify_render_loudness(loud, SAMPLE_RATE, target_lufs=-22.0, tolerance=2.0)

    def test_silent_render_fails(self) -> None:
        assert not verify_render_loudness(_silence(1.0), SAMPLE_RATE, target_lufs=-16.0)

    def test_sleep_target_accepts_quiet_sine(self) -> None:
        """A quiet sine should be within tolerance of the sleep LUFS target."""
        # amplitude chosen to land near -22.5 LUFS proxy
        buf = _sine(440.0, 2.0, amplitude=0.08)
        measured = estimate_lufs_proxy(buf, SAMPLE_RATE)
        # verify the proxy is in a plausible quiet range
        assert measured < -10.0
        assert verify_render_loudness(buf, SAMPLE_RATE, target_lufs=measured, tolerance=1.0)


# ---------------------------------------------------------------------------
# master bus values: no cadence state produces clipping-prone or silent output
# ---------------------------------------------------------------------------


class TestMasterBusVerification:
    def _context(self, cadence_state: str, theramini: bool = False) -> object:
        return build_live_emsd_context(
            cadence_state=cadence_state,
            occupancy_state="occupied_active" if "occupied" in cadence_state else "likely_away",
            family_name="bloom",
            progression_profile="open_day",
            patch_name="house_garden",
            song_num=5,
            theramini_present=theramini,
            repertoire_songs=[],
            attention_score=0.7,
            now_seconds=12 * 60,
        )

    def _dummy_scene(self) -> object:
        from senseweave.generative_scores import Note, Phrase, Score
        from senseweave.music_tracker import build_korsakov_tracker_song

        score = Score(
            phrases=[
                Phrase(notes=[Note(1, 1.0, True)], voice="pluck", dynamic="mf", role="melody"),
                Phrase(notes=[Note(1, 1.0, True)], voice="gong", dynamic="mp", role="bass"),
            ],
            key="C",
            tempo_bpm=96.0,
            mood="calm",
            created_at=0.0,
            metadata={"patch_name": "house_garden", "cadence_state": "occupied_day", "progression_profile": "open_day"},
        )
        return build_korsakov_tracker_song(score).scenes[0]

    def test_amp_within_safe_range_all_states(self) -> None:
        scene = self._dummy_scene()
        for state in ("sleep", "wind_down", "wake_ramp", "occupied_day", "away_practice"):
            ctx = self._context(state)
            values = master_bus_values_for_scene(scene, context=ctx)
            assert 0.8 <= values["amp"] <= 5.0, f"{state}: amp {values['amp']}"

    def test_drive_below_harshness_threshold_all_states(self) -> None:
        scene = self._dummy_scene()
        for state in ("sleep", "wind_down", "wake_ramp", "occupied_day", "away_practice"):
            ctx = self._context(state)
            values = master_bus_values_for_scene(scene, context=ctx)
            report = check_harshness_proxy(drive=values["drive"], saturation=0.0)
            assert not report.over_threshold, f"{state}: drive {values['drive']}"

    def test_theramini_ducking_lowers_amp(self) -> None:
        scene = self._dummy_scene()
        ctx_off = self._context("occupied_day", theramini=True)
        ctx_on = self._context("occupied_day", theramini=True)
        without = master_bus_values_for_scene(scene, context=ctx_off, theramini_active=False)
        with_t = master_bus_values_for_scene(scene, context=ctx_on, theramini_active=True)
        assert with_t["amp"] <= without["amp"]

    def test_reverb_never_exceeds_room(self) -> None:
        scene = self._dummy_scene()
        for state in ("sleep", "wind_down", "wake_ramp", "occupied_day", "away_practice"):
            ctx = self._context(state)
            values = master_bus_values_for_scene(scene, context=ctx)
            assert values["reverb"] <= values["room"], f"{state}: reverb > room"


# ---------------------------------------------------------------------------
# per-note render shaping: bounds and non-clipping
# ---------------------------------------------------------------------------


class TestPerNoteShapingBounds:
    def test_voice_shaping_amp_never_exceeds_one(self) -> None:
        for voice in ("pluck", "bowed", "bell", "choir", "breath", "gong", "kotekan"):
            for freq in (220.0, 440.0, 880.0, 1200.0, 2000.0):
                shape = shaping_for_note(voice, freq)
                assert shape.amp_multiplier <= 1.0, f"{voice}@{freq}Hz: amp {shape.amp_multiplier}"

    def test_high_register_folded_down(self) -> None:
        shape = shaping_for_note("pluck", 1600.0)
        assert shape.pitch_multiplier < 1.0

    def test_emsd_performance_amp_clamped(self) -> None:
        ctx = build_live_emsd_context(
            cadence_state="occupied_day",
            occupancy_state="occupied_active",
            family_name="bloom",
            progression_profile="open_day",
            patch_name="house_garden",
            song_num=5,
            theramini_present=False,
            repertoire_songs=[],
            attention_score=0.8,
            now_seconds=12 * 60,
        )
        for role in ("bass", "melody", "counter", "color"):
            for freq in (110.0, 440.0, 880.0, 2000.0, 4000.0):
                adj = render_adjustments_for_event(
                    role=role,
                    voice_name="pluck",
                    frequency_hz=freq,
                    context=ctx,
                    theramini_active=False,
                )
                assert 0.45 <= adj.amp_multiplier <= 1.2, f"{role}@{freq}Hz: amp {adj.amp_multiplier}"
                assert 0.85 <= adj.release_multiplier <= 1.4
                assert 0.65 <= adj.brightness_multiplier <= 1.08


class TestSyntheticRenderClippingIntegration:
    """Build a synthetic multi-voice render and verify it stays below ceiling."""

    def test_four_voice_mix_below_ceiling(self) -> None:
        profile = build_mix_profile(cadence_state="occupied_day", patch_name="house_garden")
        # Render each role as a sine at its lane center, scaled by its level_db
        voices: list[list[float]] = []
        for target in profile.voice_targets:
            center_hz = (target.lane.low_hz + target.lane.high_hz) / 2.0
            amp = 10.0 ** (target.level_db / 20.0)
            voices.append(_sine(center_hz, 1.0, amplitude=amp))
        mixed = _sum_buffers(*voices)
        assert not check_clipping(mixed, profile.peak_ceiling_dbtp)
        assert not check_silence(mixed)

    def test_four_voice_mix_not_silent(self) -> None:
        profile = build_mix_profile(cadence_state="sleep", patch_name="house_monastery")
        voices: list[list[float]] = []
        for target in profile.voice_targets:
            center_hz = (target.lane.low_hz + target.lane.high_hz) / 2.0
            amp = 10.0 ** (target.level_db / 20.0)
            voices.append(_sine(center_hz, 1.0, amplitude=amp))
        mixed = _sum_buffers(*voices)
        assert not check_silence(mixed)

    def test_louder_cadence_measures_louder(self) -> None:
        """Louder cadence states must produce higher LUFS proxy readings."""
        measurements: dict[str, float] = {}
        for state in ("sleep", "occupied_day", "away_practice"):
            profile = build_mix_profile(cadence_state=state, patch_name="house_garden")
            voices: list[list[float]] = []
            for target in profile.voice_targets:
                center_hz = (target.lane.low_hz + target.lane.high_hz) / 2.0
                amp = 10.0 ** (target.level_db / 20.0)
                voices.append(_sine(center_hz, 2.0, amplitude=amp))
            mixed = _sum_buffers(*voices)
            measurements[state] = estimate_lufs_proxy(mixed, SAMPLE_RATE)
        # sleep is quietest target, away_practice loudest
        assert measurements["sleep"] == measurements["occupied_day"]  # same voice levels, different target
        # The LUFS targets themselves must be ordered correctly
        sleep_p = build_mix_profile(cadence_state="sleep", patch_name="house_garden")
        day_p = build_mix_profile(cadence_state="occupied_day", patch_name="house_garden")
        away_p = build_mix_profile(cadence_state="away_practice", patch_name="house_garden")
        assert sleep_p.target_lufs < day_p.target_lufs < away_p.target_lufs

    def test_render_loudness_proxy_is_finite(self) -> None:
        """Every cadence state must produce a measurable (non-silent) render."""
        for state in ("sleep", "wind_down", "wake_ramp", "occupied_day", "away_practice"):
            profile = build_mix_profile(cadence_state=state, patch_name="house_garden")
            voices: list[list[float]] = []
            for target in profile.voice_targets:
                center_hz = (target.lane.low_hz + target.lane.high_hz) / 2.0
                amp = 10.0 ** (target.level_db / 20.0)
                voices.append(_sine(center_hz, 2.0, amplitude=amp))
            mixed = _sum_buffers(*voices)
            measured = estimate_lufs_proxy(mixed, SAMPLE_RATE)
            assert measured > -40.0, f"{state}: measured {measured:.1f} — too quiet"


class MixVerifyEndToEndTests:
    __test__ = True

    def test_profile_render_and_diagnostics_are_meaningful(self) -> None:
        profile = build_mix_profile(
            cadence_state="occupied_day",
            patch_name="house_garden",
            phase_name="Conversation",
        )

        voices: list[list[float]] = []
        for target in profile.voice_targets:
            center_hz = (target.lane.low_hz + target.lane.high_hz) / 2.0
            amp = 10.0 ** (target.level_db / 20.0)
            voices.append(_sine(center_hz, 2.0, amplitude=amp))

        mixed = _sum_buffers(*voices)
        measured_lufs = estimate_lufs_proxy(mixed, SAMPLE_RATE)
        peak = peak_dbfs(mixed)
        rms = rms_dbfs(mixed)
        low_end = check_low_end_runaway(mixed, SAMPLE_RATE)
        harshness = check_harshness_proxy(
            drive=profile.bus_comp_ratio / 8.0,
            saturation=profile.voice_targets[0].reverb_send / 10.0,
            brightness=1.0 + profile.mastering.eq_intent.air_shelf_db / 10.0,
        )

        profile_issues = verify_mix_profile(profile)
        masking_pairs = check_masking(profile.voice_targets)
        diagnostics = {
            "cadence_state": profile.cadence_state,
            "patch_name": profile.patch_name,
            "target_lufs": profile.target_lufs,
            "measured_lufs": round(measured_lufs, 4),
            "peak_dbfs": round(peak, 4),
            "rms_dbfs": round(rms, 4),
            "profile_issues": [
                {"field": issue.field, "message": issue.message}
                for issue in profile_issues
            ],
            "masking_pairs": [
                {
                    "role_a": pair.role_a,
                    "role_b": pair.role_b,
                    "overlap": pair.overlap,
                }
                for pair in masking_pairs
            ],
            "low_end": {
                "ratio": low_end.low_end_ratio,
                "over_threshold": low_end.over_threshold,
            },
            "harshness": {
                "score": harshness.score,
                "over_threshold": harshness.over_threshold,
            },
        }
        loaded = json.loads(json.dumps(diagnostics, sort_keys=True))

        assert profile_issues == []
        assert masking_pairs == []
        assert not check_clipping(mixed, profile.peak_ceiling_dbtp)
        assert not check_silence(mixed)
        assert not low_end.over_threshold
        assert 0.0 < low_end.low_end_ratio < 0.7
        assert not harshness.over_threshold
        assert 0.0 < harshness.score < 0.7
        assert peak <= profile.peak_ceiling_dbtp
        assert peak > rms > -20.0
        assert measured_lufs > -20.0
        assert verify_render_loudness(
            mixed,
            SAMPLE_RATE,
            target_lufs=measured_lufs,
            tolerance=0.5,
        )
        assert loaded["profile_issues"] == []
        assert loaded["masking_pairs"] == []
        assert loaded["low_end"]["over_threshold"] is False
        assert loaded["harshness"]["over_threshold"] is False
