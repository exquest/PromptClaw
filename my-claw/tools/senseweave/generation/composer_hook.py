"""Composer-facing helpers for deciding when to queue generated audio."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from typing import Any


MIN_GENERATION_INTERVAL_SECONDS = 30.0 * 60.0
MIN_DAILY_BUDGET_REMAINING_USD = 0.50


def _mode_name(mode: Any) -> str:
    value = getattr(mode, "name", mode)
    return str(value or "")


def _mapping_value(data: Any, *names: str) -> Any:
    if isinstance(data, Mapping):
        for name in names:
            if name in data:
                return data[name]
    for name in names:
        if hasattr(data, name):
            return getattr(data, name)
    return None


def _float_value(data: Any, *names: str, default: float = 0.0) -> float:
    value = _mapping_value(data, *names)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sampler_dominating_reported(learning: Any) -> bool:
    direct = _mapping_value(learning, "sampler_dominating")
    if isinstance(direct, bool):
        return direct

    antipatterns = _mapping_value(learning, "antipatterns") or ()
    for result in antipatterns:
        name = _mapping_value(result, "name")
        failed = _mapping_value(result, "failed")
        if str(name) == "sampler_dominating" and bool(failed):
            return True
    return False


def _should_queue_now(
    mode: Any,
    mood: Mapping[str, float] | None,
    learning: Any,
    *,
    now: float | None = None,
    last_enqueued_at: float | None = None,
    daily_budget_remaining_usd: float | None = None,
) -> bool:
    """Return True when the composer should enqueue one generation request."""
    del mood  # reserved for later homogeneity checks

    arc_payoff = _float_value(learning, "arc_payoff", "arc_payoff_score")
    if _mode_name(mode) == "working_ambience" and arc_payoff < 0.4:
        return False

    if _sampler_dominating_reported(learning):
        return False

    remaining = daily_budget_remaining_usd
    if remaining is None:
        remaining = _float_value(
            learning,
            "daily_budget_remaining_usd",
            "budget_remaining_usd",
            default=1.0,
        )
    if remaining <= MIN_DAILY_BUDGET_REMAINING_USD:
        return False

    if last_enqueued_at is None:
        last_enqueued_at = _last_enqueued_from_learning(learning)
    if last_enqueued_at is None:
        return True

    current = time.time() if now is None else now
    return (current - last_enqueued_at) >= MIN_GENERATION_INTERVAL_SECONDS


def _last_enqueued_from_learning(learning: Any) -> float | None:
    raw = _mapping_value(
        learning,
        "last_generation_enqueued_at",
        "last_enqueued_at",
    )
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def build_generation_request(
    *,
    mode: Any,
    arc_phase: str,
    mood: Mapping[str, float],
    clap_centroid: Any,
    duration_sec: float = 5.0,
    model: str = "musicgen-medium",
    backend: str = "replicate",
) -> dict[str, Any]:
    """Build a deterministic JSON-serializable generation request payload."""
    mode_name = _mode_name(mode)
    mood_items = tuple(sorted((str(k), float(v)) for k, v in mood.items()))
    centroid_bytes = _centroid_bytes(clap_centroid)
    seed_material = json.dumps(
        {
            "mode": mode_name,
            "arc_phase": arc_phase,
            "mood": mood_items,
            "duration_sec": duration_sec,
            "model": model,
        },
        sort_keys=True,
    ).encode("utf-8") + centroid_bytes
    digest = hashlib.sha256(seed_material).hexdigest()
    seed = int(digest[:8], 16)
    prompt = (
        f"{mode_name.replace('_', ' ')}, {arc_phase}, "
        f"{_mood_word(mood)}: short restrained texture for CypherClaw sampler"
    )
    return {
        "request_hash": digest,
        "backend": backend,
        "model": model,
        "prompt": prompt,
        "duration_sec": float(duration_sec),
        "seed": seed,
        "mode_name": mode_name,
        "arc_phase": arc_phase,
        "mood": _mood_scalar(mood),
    }


def _centroid_bytes(value: Any) -> bytes:
    tobytes = getattr(value, "tobytes", None)
    if callable(tobytes):
        return bytes(tobytes())
    return json.dumps(value, sort_keys=True, default=str).encode("utf-8")


def _mood_scalar(mood: Mapping[str, float]) -> float:
    if not mood:
        return 0.0
    return round(sum(float(value) for value in mood.values()) / len(mood), 6)


def _mood_word(mood: Mapping[str, float]) -> str:
    valence = float(mood.get("valence", 0.0))
    arousal = float(mood.get("arousal", mood.get("energy", 0.0)))
    if arousal >= 0.7:
        return "charged"
    if valence >= 0.55:
        return "warm"
    if valence <= 0.25:
        return "shadowed"
    return "balanced"


__all__ = (
    "MIN_DAILY_BUDGET_REMAINING_USD",
    "MIN_GENERATION_INTERVAL_SECONDS",
    "_should_queue_now",
    "build_generation_request",
)
