"""Creative DSP and cross-modal mapping helpers for EMSD work."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

DSPBlock = Literal[
    "spectral_freeze",
    "spectral_smear",
    "spectral_morph",
    "convolution",
    "delay",
    "physical_model",
    "long_convolution",
    "freeze_tail",
    "grain_window",
    "cross_synthesis",
    "bin_shift",
    "parallel_delay",
    "diffuse_feedback",
    "comb_resonance",
    "lowpass_bloom",
]

@dataclass(frozen=True)
class AudioFeatureFrame:
    amplitude: float
    spectral_centroid_hz: float
    spectral_flatness: float
    onset_rate_hz: float


@dataclass(frozen=True)
class DSPGesture:
    """A parameterized DSP effect derived from audio features."""

    block: DSPBlock
    intensity: float
    time_scale: float
    params: dict[str, float]


@dataclass(frozen=True)
class DSPScene:
    phase_name: str
    blocks: tuple[DSPBlock, ...]
    source_focus: str
    visual_bias: dict[str, float]


def scene_for_phase(phase_name: str, *, cadence_state: str) -> DSPScene:
    if phase_name == "Divination":
        return DSPScene(phase_name, ("spectral_smear", "long_convolution"), "room_mic", {"motion": 0.2, "density": 0.18})
    if phase_name == "Emergence":
        return DSPScene(phase_name, ("freeze_tail", "grain_window"), "room_mic", {"motion": 0.45, "density": 0.42})
    if phase_name == "Conversation":
        blocks: tuple[DSPBlock, ...] = ("cross_synthesis", "bin_shift", "parallel_delay")
        if cadence_state == "away_practice":
            blocks += ("diffuse_feedback",)
        return DSPScene(phase_name, blocks, "theramini_in", {"motion": 0.78, "density": 0.76})
    if phase_name == "Convergence":
        source_focus = "self_bus" if cadence_state == "away_practice" else "room_mic"
        return DSPScene(phase_name, ("spectral_morph", "comb_resonance"), source_focus, {"motion": 0.52, "density": 0.48})
    source_focus = "self_bus" if cadence_state == "away_practice" else "room_mic"
    return DSPScene(phase_name, ("freeze_tail", "lowpass_bloom"), source_focus, {"motion": 0.24, "density": 0.2})


_CORE_GESTURE_BLOCKS: tuple[DSPBlock, ...] = (
    "spectral_freeze",
    "spectral_smear",
    "spectral_morph",
    "convolution",
    "delay",
    "physical_model",
)


def _gesture_for_block(block: DSPBlock, frame: AudioFeatureFrame) -> DSPGesture:
    """Map audio features to gesture parameters for one block type."""
    brightness = min(1.0, frame.spectral_centroid_hz / 4000.0)
    density = min(1.0, frame.onset_rate_hz / 10.0)
    amp = frame.amplitude

    if block == "spectral_freeze":
        return DSPGesture(
            block,
            intensity=max(0.1, 1.0 - amp),
            time_scale=1.0 + brightness,
            params={
                "hold_time": 0.5 + (1.0 - density) * 2.0,
                "crossfade": 0.1 + brightness * 0.3,
            },
        )
    if block == "spectral_smear":
        return DSPGesture(
            block,
            intensity=min(1.0, brightness * 0.8 + 0.2),
            time_scale=1.0,
            params={
                "spread": brightness * 0.7,
                "decay": 0.3 + (1.0 - density) * 0.5,
            },
        )
    if block == "spectral_morph":
        return DSPGesture(
            block,
            intensity=min(1.0, amp * 0.6 + 0.3),
            time_scale=0.5 + density,
            params={
                "morph_rate": density * 2.0,
                "target_brightness": brightness,
            },
        )
    if block == "convolution":
        return DSPGesture(
            block,
            intensity=max(0.2, amp * 0.5 + 0.3),
            time_scale=1.0,
            params={
                "wet_mix": 0.3 + brightness * 0.4,
                "ir_scale": 0.5 + (1.0 - density) * 0.5,
            },
        )
    if block == "delay":
        return DSPGesture(
            block,
            intensity=min(1.0, density * 0.6 + 0.2),
            time_scale=1.0 / max(0.1, density + 0.3),
            params={
                "time_ms": 100.0 + (1.0 - density) * 400.0,
                "feedback": min(0.85, density * 0.4 + 0.3),
            },
        )
    if block == "physical_model":
        return DSPGesture(
            block,
            intensity=min(1.0, amp * 0.7 + 0.2),
            time_scale=1.0,
            params={
                "resonance": min(0.95, brightness * 0.5 + 0.3),
                "damping": max(0.1, 1.0 - brightness * 0.6),
            },
        )
    return DSPGesture(block, intensity=amp, time_scale=1.0, params={})


def gestures_from_frame(
    frame: AudioFeatureFrame,
    scene: DSPScene | None = None,
) -> list[DSPGesture]:
    """Derive parameterized DSP gestures from audio features and scene context.

    When a scene is provided, gestures are generated for the scene's blocks.
    Otherwise, the six core gesture types are used.
    """
    blocks = scene.blocks if scene else _CORE_GESTURE_BLOCKS
    return [_gesture_for_block(block, frame) for block in blocks]


def glyph_features_from_audio(
    frame: AudioFeatureFrame,
    scene: DSPScene | None = None,
) -> dict[str, Any]:
    brightness = min(1.0, frame.spectral_centroid_hz / 4000.0)
    motion = min(1.0, frame.onset_rate_hz / 8.0 + frame.amplitude * 0.35)
    texture = min(1.0, 0.25 + frame.spectral_flatness * 0.75)
    density = min(1.0, frame.onset_rate_hz / 10.0)
    salience = min(1.0, frame.amplitude * 0.6 + motion * 0.4)

    blocks = list(scene.blocks) if scene else []
    mapping_hints: dict[str, Any] = {"focus": scene.source_focus} if scene else {}

    gestures = gestures_from_frame(frame, scene)
    if gestures:
        mapping_hints["gesture_count"] = len(gestures)
        mapping_hints["dominant_intensity"] = round(
            max(g.intensity for g in gestures), 3
        )

    return {
        "brightness": round(brightness, 3),
        "motion": round(motion, 3),
        "texture": round(texture, 3),
        "density": round(density, 3),
        "salience": round(salience, 3),
        "dsp_blocks": blocks,
        "mapping_hints": mapping_hints,
        "gestures": [
            {
                "block": g.block,
                "intensity": round(g.intensity, 3),
                "time_scale": round(g.time_scale, 3),
                "params": {k: round(v, 3) for k, v in g.params.items()},
            }
            for g in gestures
        ],
    }
