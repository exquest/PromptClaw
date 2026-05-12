"""Pure helpers for note-by-note playback shaping."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceShape:
    """Small playback adjustments for a note's register."""

    pitch_multiplier: float = 1.0
    amp_multiplier: float = 1.0
    release_multiplier: float = 1.0
    brightness_multiplier: float = 1.0
    detune_add: float = 0.0
    verb_add: float = 0.0
    dly_add: float = 0.0
    highpass_hz: float = 0.0
    saturation_mix: float = 0.0
    position_center: float | None = None


def shaping_for_note(voice_name: str, freq_hz: float) -> VoiceShape:
    """Return gentle top-end shaping for sharp high notes.

    The current Senseweave synth surface does not expose a uniform filter/drive
    interface across every SynthDef, so the shaping returns both best-effort
    control intents (`highpass_hz`, `saturation_mix`) and the existing softer
    saturation-style behavior: slightly lower gain, shorter release, less
    brightness, a bit more detune, and a touch more space. The highest octave
    is also folded down one octave at playback so the live ensemble stops
    landing in an ear-splitting top register.
    """

    if freq_hz < 880.0:
        return VoiceShape()

    if freq_hz < 1046.5:
        if voice_name == "pluck":
            return VoiceShape(
                amp_multiplier=0.94,
                release_multiplier=0.96,
                brightness_multiplier=0.78,
                detune_add=0.0015,
                verb_add=0.015,
                dly_add=0.003,
                highpass_hz=180.0,
                saturation_mix=0.08,
                position_center=0.1,
            )
        return VoiceShape(
            amp_multiplier=0.95,
            release_multiplier=0.97,
            verb_add=0.015,
            dly_add=0.003,
            highpass_hz=220.0,
            saturation_mix=0.06,
        )

    if freq_hz < 1568.0:
        if voice_name == "pluck":
            return VoiceShape(
                pitch_multiplier=0.5,
                amp_multiplier=0.9,
                release_multiplier=0.93,
                brightness_multiplier=0.68,
                detune_add=0.0025,
                verb_add=0.028,
                dly_add=0.006,
                highpass_hz=280.0,
                saturation_mix=0.12,
                position_center=0.11,
            )
        return VoiceShape(
            pitch_multiplier=0.5,
            amp_multiplier=0.91,
            release_multiplier=0.94,
            verb_add=0.022,
            dly_add=0.004,
            highpass_hz=260.0,
            saturation_mix=0.09,
        )

    if voice_name == "pluck":
        return VoiceShape(
            pitch_multiplier=0.25,
            amp_multiplier=0.82,
            release_multiplier=0.88,
            brightness_multiplier=0.52,
            detune_add=0.0045,
            verb_add=0.04,
            dly_add=0.008,
            highpass_hz=340.0,
            saturation_mix=0.16,
            position_center=0.125,
        )
    return VoiceShape(
        pitch_multiplier=0.25,
        amp_multiplier=0.84,
        release_multiplier=0.9,
        verb_add=0.03,
        dly_add=0.006,
        highpass_hz=320.0,
        saturation_mix=0.12,
    )
