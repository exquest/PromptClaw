from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.artist_identity import EVENING_REFLECTION, MODES_BY_NAME  # noqa: E402
from senseweave.generation.conditioner import (  # noqa: E402
    _ARC_FRAGMENTS,
    _DEPARTURE_FRAGMENTS,
    _MODE_FRAGMENTS,
    _SELF_DISTANCE_THRESHOLD,
    GenerationConditioner,
)
from senseweave.generation.request import CLAP_CENTROID_DIM  # noqa: E402
from senseweave.procedural_arc import ARC_PHASES  # noqa: E402


CANONICAL_MODE_FRAGMENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "solitary",
        ("intimate", "sparse", "single voice", "long held tones", "lots of silence"),
    ),
    ("companion", ("warm", "harmonic", "supportive", "two-three voices")),
    ("working_ambience", ("pulse-based", "predictable", "no melody", "minimal")),
    (
        "evening_reflection",
        ("longer phrases", "harmonic tension", "tender", "lyrical"),
    ),
    ("storm", ("turbulent", "dense grains", "modal shifts", "fast articulation")),
)


EXPECTED_MODE_FRAGMENTS = {
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

EXPECTED_ARC_FRAGMENTS = {
    "Divination": "searching through uncertain signals",
    "Emergence": "opening into new material",
    "Conversation": "responsive call and answer",
    "Convergence": "gathering threads into focus",
    "Crystallization": "settling into clear form",
    "Reflection": "returning to memory",
}


def _centroid() -> np.ndarray:
    values = np.arange(1, CLAP_CENTROID_DIM + 1, dtype=np.float32)
    return values * 0.25


def _expected_seed(
    *,
    mode_name: str,
    arc_phase: str,
    mood: dict[str, float],
    normalized_centroid: np.ndarray,
) -> int:
    mood_tuple = tuple(sorted((str(key), float(value)) for key, value in mood.items()))
    hasher = hashlib.sha256()
    for text in (mode_name, arc_phase):
        encoded = text.encode("utf-8")
        hasher.update(len(encoded).to_bytes(4, "big"))
        hasher.update(encoded)

    mood_blob = json.dumps(mood_tuple, separators=(",", ":")).encode("utf-8")
    hasher.update(len(mood_blob).to_bytes(4, "big"))
    hasher.update(mood_blob)
    hasher.update(np.ascontiguousarray(normalized_centroid, dtype=np.float32).tobytes())
    return int.from_bytes(hasher.digest(), "big") % (2**32)


def test_mode_fragments_match_artist_mode_table() -> None:
    assert _MODE_FRAGMENTS == EXPECTED_MODE_FRAGMENTS
    assert set(_MODE_FRAGMENTS) == set(MODES_BY_NAME)


@pytest.mark.parametrize(("mode_name", "canonical_fragments"), CANONICAL_MODE_FRAGMENTS)
def test_mode_fragment_table_includes_canonical_fragments(
    mode_name: str, canonical_fragments: tuple[str, ...]
) -> None:
    fragments = _MODE_FRAGMENTS[mode_name]
    assert isinstance(fragments, tuple)
    assert all(isinstance(fragment, str) for fragment in fragments)
    for fragment in canonical_fragments:
        assert fragment in fragments, (
            f"{mode_name} fragments must include {fragment!r}; got {fragments!r}"
        )


def test_arc_fragments_cover_procedural_arc_phase_names() -> None:
    assert _ARC_FRAGMENTS == EXPECTED_ARC_FRAGMENTS
    assert {phase.name for phase in ARC_PHASES} <= set(_ARC_FRAGMENTS)


@pytest.mark.parametrize(("arc_phase", "canonical_fragment"), EXPECTED_ARC_FRAGMENTS.items())
def test_arc_fragment_table_contributes_canonical_fragment_to_prompt(
    arc_phase: str, canonical_fragment: str
) -> None:
    req = GenerationConditioner().build_request(
        EVENING_REFLECTION,
        arc_phase,
        {"energy": 0.6, "valence": 0.7, "arousal": 0.4},
        _centroid(),
        10.0,
    )

    assert f", {canonical_fragment}, " in req.prompt


def test_unknown_arc_phase_uses_in_progress_prompt_fragment() -> None:
    req = GenerationConditioner().build_request(
        EVENING_REFLECTION,
        "UnknownArc",
        {"energy": 0.6, "valence": 0.7, "arousal": 0.4},
        _centroid(),
        10.0,
    )

    assert ", in-progress, " in req.prompt


def test_build_request_uses_static_prompt_template() -> None:
    req = GenerationConditioner().build_request(
        EVENING_REFLECTION,
        "Emergence",
        {"energy": 0.6, "valence": 0.7, "arousal": 0.4},
        _centroid(),
        10.0,
    )

    assert req.prompt == (
        "longer phrases harmonic tension tender lyrical, "
        "opening into new material, warm: "
        "short loopable sampler material, no vocals, no named artists"
    )
    assert req.mode_name == "evening_reflection"
    assert req.arc_phase == "Emergence"
    assert req.bpm_target == 64.0


def test_build_request_is_pure_and_sorts_mood_for_seed() -> None:
    conditioner = GenerationConditioner()
    centroid = _centroid()

    first = conditioner.build_request(
        "evening_reflection",
        "Emergence",
        {"energy": 0.6, "valence": 0.7, "arousal": 0.4},
        centroid,
        10.0,
    )
    second = conditioner.build_request(
        "evening_reflection",
        "Emergence",
        {"valence": 0.7, "arousal": 0.4, "energy": 0.6},
        centroid.copy(),
        10.0,
    )

    assert first == second
    assert hash(first) == hash(second)
    np.testing.assert_array_equal(first.clap_centroid, second.clap_centroid)


def test_seed_is_sha256_folded_to_32_bits_from_normalized_centroid_bytes() -> None:
    mood = {"energy": 0.6, "valence": 0.7, "arousal": 0.4}
    req = GenerationConditioner().build_request(
        EVENING_REFLECTION,
        "Emergence",
        mood,
        _centroid(),
        10.0,
    )

    expected = _expected_seed(
        mode_name="evening_reflection",
        arc_phase="Emergence",
        mood=mood,
        normalized_centroid=req.clap_centroid,
    )
    assert req.seed == expected
    assert 0 <= req.seed <= 0xFFFFFFFF


def test_clap_centroid_is_unit_normalized_before_storage() -> None:
    req = GenerationConditioner().build_request(
        EVENING_REFLECTION,
        "Reflection",
        {"energy": 0.2, "valence": 0.5, "arousal": 0.2},
        _centroid(),
        10.0,
    )

    assert req.clap_centroid.dtype == np.float32
    assert req.clap_centroid.shape == (CLAP_CENTROID_DIM,)
    assert np.isclose(float(np.linalg.norm(req.clap_centroid)), 1.0)


def _unit_vector(values: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(values.astype(np.float64)))
    return (values / norm).astype(np.float32)


def test_recent_centroid_far_returns_unperturbed_request() -> None:
    centroid = _centroid()
    far = np.zeros(CLAP_CENTROID_DIM, dtype=np.float32)
    far[0] = 1.0  # nearly orthogonal to a uniform-ish centroid

    baseline = GenerationConditioner().build_request(
        EVENING_REFLECTION,
        "Emergence",
        {"energy": 0.6, "valence": 0.7, "arousal": 0.4},
        centroid,
        10.0,
    )
    with_recent = GenerationConditioner().build_request(
        EVENING_REFLECTION,
        "Emergence",
        {"energy": 0.6, "valence": 0.7, "arousal": 0.4},
        centroid,
        10.0,
        recent_generated_centroid=far,
    )

    assert with_recent is not None
    assert with_recent.prompt == baseline.prompt
    assert not any(
        with_recent.prompt.startswith(f"{frag} ") for frag in _DEPARTURE_FRAGMENTS
    )


def test_recent_centroid_too_close_perturbs_prompt_deterministically() -> None:
    centroid = _centroid()
    normalized = _unit_vector(centroid)

    baseline = GenerationConditioner().build_request(
        EVENING_REFLECTION,
        "Emergence",
        {"energy": 0.6, "valence": 0.7, "arousal": 0.4},
        centroid,
        10.0,
    )

    first = GenerationConditioner().build_request(
        EVENING_REFLECTION,
        "Emergence",
        {"energy": 0.6, "valence": 0.7, "arousal": 0.4},
        centroid,
        10.0,
        recent_generated_centroid=normalized,
    )
    second = GenerationConditioner().build_request(
        EVENING_REFLECTION,
        "Emergence",
        {"energy": 0.6, "valence": 0.7, "arousal": 0.4},
        centroid.copy(),
        10.0,
        recent_generated_centroid=normalized.copy(),
    )

    assert first is not None and second is not None
    expected_fragment = _DEPARTURE_FRAGMENTS[baseline.seed % len(_DEPARTURE_FRAGMENTS)]
    assert first.prompt == f"{expected_fragment} {baseline.prompt}"
    assert first.prompt == second.prompt
    assert first.seed == baseline.seed


def test_recent_centroid_at_threshold_does_not_perturb() -> None:
    centroid = _centroid()
    normalized = _unit_vector(centroid)
    # Construct a recent vector with cosine similarity exactly 1 - threshold.
    target_similarity = 1.0 - _SELF_DISTANCE_THRESHOLD
    perpendicular = np.zeros(CLAP_CENTROID_DIM, dtype=np.float32)
    perpendicular[0] = 1.0
    perpendicular -= float(np.dot(perpendicular, normalized)) * normalized
    perpendicular = _unit_vector(perpendicular)
    recent = (
        target_similarity * normalized
        + np.sqrt(1.0 - target_similarity**2) * perpendicular
    ).astype(np.float32)
    recent = _unit_vector(recent)

    req = GenerationConditioner().build_request(
        EVENING_REFLECTION,
        "Emergence",
        {"energy": 0.6, "valence": 0.7, "arousal": 0.4},
        centroid,
        10.0,
        recent_generated_centroid=recent,
    )

    assert req is not None
    assert not any(req.prompt.startswith(f"{frag} ") for frag in _DEPARTURE_FRAGMENTS)


def test_already_perturbed_prompt_returns_none_when_too_close() -> None:
    """A second build with a centroid still too close cannot re-perturb."""
    centroid = _centroid()
    normalized = _unit_vector(centroid)

    first = GenerationConditioner().build_request(
        EVENING_REFLECTION,
        "Emergence",
        {"energy": 0.6, "valence": 0.7, "arousal": 0.4},
        centroid,
        10.0,
        recent_generated_centroid=normalized,
    )
    assert first is not None
    perturbing_fragment = first.prompt.split(" ", 1)[0]
    assert perturbing_fragment in _DEPARTURE_FRAGMENTS

    # Simulate caller retrying with the already-perturbed prompt baked in by
    # exercising the helper directly: re-running through the conditioner with
    # a centroid that produces the same prompt structure should yield None.
    from senseweave.generation.conditioner import _perturbed_prompt

    assert _perturbed_prompt(first.prompt, first.seed) is None


def test_conditioner_module_has_no_llm_provider_imports_or_calls() -> None:
    source = Path("my-claw/tools/senseweave/generation/conditioner.py").read_text()

    for forbidden in ("import openai", "import anthropic", "ollama"):
        assert forbidden not in source
