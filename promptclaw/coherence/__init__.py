"""PromptClaw Coherence Engine — event-sourced state, decision memory, constitutional enforcement."""

from __future__ import annotations

__all__ = [
    "CoherenceEngine",
    "NullCoherenceEngine",
    "open_session",
    "CoherenceSession",
    "NullCoherenceSession",
    "Verdict",
]

# Lazy exports keep `import promptclaw.coherence` cheap: the engine is pulled only when an
# engine symbol is touched, and session.py itself imports the engine lazily inside open_session.
_ENGINE_NAMES = {"CoherenceEngine", "NullCoherenceEngine"}
_SESSION_NAMES = {"open_session", "CoherenceSession", "NullCoherenceSession", "Verdict"}


def __getattr__(name: str):
    if name in _ENGINE_NAMES:
        from . import engine
        return getattr(engine, name)
    if name in _SESSION_NAMES:
        from . import session
        return getattr(session, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
