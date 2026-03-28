"""PromptClaw Coherence Engine — event-sourced state, decision memory, constitutional enforcement."""

from __future__ import annotations

__all__ = ["CoherenceEngine", "NullCoherenceEngine"]


def __getattr__(name: str):
    if name == "CoherenceEngine":
        from .engine import CoherenceEngine
        return CoherenceEngine
    if name == "NullCoherenceEngine":
        from .engine import NullCoherenceEngine
        return NullCoherenceEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
