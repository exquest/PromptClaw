"""Pure conditioning from listening state to generation requests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

import numpy as np

from senseweave.generation.request import CLAP_CENTROID_DIM, GenerationRequest


_MODE_FRAGMENTS: Final[dict[str, tuple[str, ...]]] = {
    "solitary": (
        "intimate",
        "sparse",
        "single voice",
        "long held tones",
        "lots of silence",
    ),
    "companion": (
        "warm",
        "harmonic",
        "supportive",
        "two-three voices",
    ),
    "working_ambience": (
        "pulse-based",
        "predictable",
        "no melody",
        "minimal",
    ),
    "evening_reflection": (
        "longer phrases",
        "harmonic tension",
        "tender",
        "lyrical",
    ),
    "storm": (
        "turbulent",
        "dense grains",
        "modal shifts",
        "fast articulation",
    ),
}

_ARC_FRAGMENTS: Final[dict[str, str]] = {
    "Emergence": "opening into new material",
    "Crystallization": "settling into clear form",
    "Divination": "searching through uncertain signals",
    "Convergence": "gathering threads into focus",
    "Conversation": "responsive call and answer",
    "Reflection": "returning to memory",
}

_MODE_BPM_TARGETS: Final[dict[str, float]] = {
    "solitary": 61.0,
    "companion": 72.0,
    "working_ambience": 81.0,
    "evening_reflection": 64.0,
    "storm": 93.0,
}

_DEFAULT_ARC_FRAGMENT: Final[str] = "in-progress"
_CONSTRAINT_FRAGMENT: Final[str] = (
    "short loopable sampler material, no vocals, no named artists"
)
_UINT32_MODULUS: Final[int] = 2**32

_DEPARTURE_FRAGMENTS: Final[tuple[str, ...]] = (
    "unexpected",
    "distant",
    "novel",
    "uncharted",
    "foreign",
)
_SELF_DISTANCE_THRESHOLD: Final[float] = 0.3


class GenerationConditioner:
    """Build deterministic generation requests from composer/listener state."""

    def build_request(
        self,
        mode: Any,
        arc_phase: str,
        mood: Mapping[str, float],
        clap_centroid: object,
        duration_sec: float,
        recent_generated_centroid: object | None = None,
    ) -> GenerationRequest | None:
        """Return a deterministic request for the given musical state.

        When ``recent_generated_centroid`` is provided and the cosine distance
        between the new request's CLAP centroid and that recent centroid is
        below ``_SELF_DISTANCE_THRESHOLD``, the prompt is perturbed with a
        seeded "departure" adjective. If the prompt is already perturbed,
        returns ``None`` so the caller skips the enqueue.
        """
        mode_name = _mode_name(mode)
        if mode_name not in _MODE_FRAGMENTS:
            raise ValueError(
                f"mode must be one of {sorted(_MODE_FRAGMENTS)}, got {mode_name!r}"
            )

        normalized_centroid = _normalized_centroid(clap_centroid)
        prompt = _prompt(mode_name, arc_phase, mood)
        seed = _seed(
            mode_name=mode_name,
            arc_phase=arc_phase,
            mood=mood,
            normalized_centroid=normalized_centroid,
        )

        if recent_generated_centroid is not None:
            recent_normalized = _normalized_centroid(recent_generated_centroid)
            distance = _cosine_distance(normalized_centroid, recent_normalized)
            if distance < _SELF_DISTANCE_THRESHOLD:
                perturbed = _perturbed_prompt(prompt, seed)
                if perturbed is None:
                    return None
                prompt = perturbed

        return GenerationRequest(
            prompt=prompt,
            clap_centroid=normalized_centroid,
            duration_sec=float(duration_sec),
            seed=seed,
            bpm_target=_bpm_target(mode, mode_name),
            mode_name=mode_name,
            arc_phase=str(arc_phase),
        )


def _mode_name(mode: Any) -> str:
    value = getattr(mode, "name", mode)
    return str(value)


def _prompt(mode_name: str, arc_phase: str, mood: Mapping[str, float]) -> str:
    mode_fragment = " ".join(_MODE_FRAGMENTS[mode_name])
    arc_fragment = _ARC_FRAGMENTS.get(str(arc_phase), _DEFAULT_ARC_FRAGMENT)
    return (
        f"{mode_fragment}, {arc_fragment}, "
        f"{_mood_adjective(mood)}: {_CONSTRAINT_FRAGMENT}"
    )


def _mood_adjective(mood: Mapping[str, float]) -> str:
    energy = _mood_value(mood, "energy")
    valence = _mood_value(mood, "valence")
    arousal = _mood_value(mood, "arousal")

    if arousal >= 0.75 or energy >= 0.8:
        return "charged"
    if valence >= 0.65:
        return "warm"
    if valence <= 0.3:
        return "shadowed"
    if energy <= 0.25 and arousal <= 0.3:
        return "hushed"
    return "balanced"


def _mood_value(mood: Mapping[str, float], key: str) -> float:
    try:
        return float(mood.get(key, 0.5))
    except (TypeError, ValueError):
        return 0.5


def _normalized_centroid(clap_centroid: object) -> np.ndarray:
    centroid = np.asarray(clap_centroid, dtype=np.float32)
    if centroid.shape != (CLAP_CENTROID_DIM,):
        raise ValueError(
            f"clap_centroid must have shape ({CLAP_CENTROID_DIM},), "
            f"got {centroid.shape}"
        )

    centroid = np.ascontiguousarray(centroid)
    if not np.isfinite(centroid).all():
        raise ValueError("clap_centroid must contain only finite values")

    norm = float(np.linalg.norm(centroid.astype(np.float64)))
    if norm <= 0.0:
        raise ValueError("clap_centroid must be non-zero")

    return np.ascontiguousarray((centroid / norm).astype(np.float32))


def _seed(
    *,
    mode_name: str,
    arc_phase: str,
    mood: Mapping[str, float],
    normalized_centroid: np.ndarray,
) -> int:
    mood_tuple = tuple(sorted((str(key), float(value)) for key, value in mood.items()))
    hasher = hashlib.sha256()
    for text in (mode_name, str(arc_phase)):
        encoded = text.encode("utf-8")
        hasher.update(len(encoded).to_bytes(4, "big"))
        hasher.update(encoded)

    mood_blob = json.dumps(mood_tuple, separators=(",", ":")).encode("utf-8")
    hasher.update(len(mood_blob).to_bytes(4, "big"))
    hasher.update(mood_blob)
    hasher.update(np.ascontiguousarray(normalized_centroid, dtype=np.float32).tobytes())
    return int.from_bytes(hasher.digest(), "big") % _UINT32_MODULUS


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    similarity = float(np.dot(a.astype(np.float64), b.astype(np.float64)))
    similarity = max(-1.0, min(1.0, similarity))
    return 1.0 - similarity


def _perturbed_prompt(prompt: str, seed: int) -> str | None:
    for fragment in _DEPARTURE_FRAGMENTS:
        if prompt.startswith(f"{fragment} "):
            return None
    index = seed % len(_DEPARTURE_FRAGMENTS)
    return f"{_DEPARTURE_FRAGMENTS[index]} {prompt}"


def _bpm_target(mode: Any, mode_name: str) -> float:
    tempo_band = getattr(mode, "tempo_band", None)
    if isinstance(tempo_band, tuple) and len(tempo_band) == 2:
        try:
            low, high = tempo_band
            return round((float(low) + float(high)) / 2.0, 1)
        except (TypeError, ValueError):
            pass
    return _MODE_BPM_TARGETS[mode_name]


__all__ = ("GenerationConditioner",)
