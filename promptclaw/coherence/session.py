"""CoherenceSession — the import-light, never-raises facade external hosts use (Phase 2).

A host (e.g. sdp-cli) calls ``open_session(project_root, run_id)`` and drives the coherence
engine through a small, JSON-friendly API instead of reaching into engine internals or
replaying the 7-hook dance. Guarantees:

1. **Import-light** — this module imports no engine/cli/orchestrator code at module load; the
   engine is imported lazily inside ``open_session``. So ``import promptclaw.coherence`` stays cheap.
2. **Never raises into the host** — every method is guarded; failures degrade to a safe default.
   When coherence is disabled or init fails, ``open_session`` returns a ``NullCoherenceSession``
   with identical signatures.
3. **JSON-friendly returns** — ``Verdict`` and the read helpers are plain dicts / dataclasses with
   string enums, so a host (or a subprocess/JSON shim) can consume them without importing engine types.

See docs/Shadowland2/promptclaw-integration-proposal.md (P2) and docs/coherence-api.md.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Verdict:
    """JSON-friendly result of a lead/verify hook."""

    approved: bool = True
    violations: list[dict] = field(default_factory=list)  # [{rule_id, severity, message}]
    trust_delta: float = 0.0
    mode: str = "monitor"


def _enum_value(value: Any, default: str = "") -> str:
    return value.value if hasattr(value, "value") else (str(value) if value is not None else default)


def _to_verdict(cv: Any) -> Verdict:
    violations = [
        {"rule_id": v.rule_id, "severity": _enum_value(v.severity), "message": v.message}
        for v in (getattr(cv, "violations", None) or [])
    ]
    return Verdict(
        approved=getattr(cv, "approved", True),
        violations=violations,
        trust_delta=getattr(cv, "trust_delta", 0.0),
        mode=_enum_value(getattr(cv, "mode", None), "monitor"),
    )


class CoherenceSession:
    """Ergonomic per-run wrapper over the engine's hooks. Every method is best-effort."""

    def __init__(self, engine: Any, run_id: str) -> None:
        self._engine = engine
        self.run_id = run_id

    # --- lead / verify lifecycle ---

    def before_lead(self, task_text: str, agent: str = "lead") -> str:
        """Context to prepend to the lead prompt (active decisions, held tensions, rules)."""
        try:
            return self._engine.pre_lead(self.run_id, agent, task_text).injected_context or ""
        except Exception:
            return ""

    def after_lead(self, agent: str, output_text: str) -> Verdict:
        """Capture declared blocks, evaluate the constitution, update trust."""
        try:
            return _to_verdict(self._engine.post_lead(self.run_id, agent, output_text))
        except Exception:
            return Verdict()

    def before_verify(self, lead_output: str, agent: str = "verify") -> str:
        try:
            return self._engine.pre_verify(self.run_id, agent, lead_output).injected_context or ""
        except Exception:
            return ""

    def after_verify(self, agent: str, verdict_text: str) -> Verdict:
        """Evaluate the verifier's output; SEC-001 etc. surface here as violations."""
        try:
            return _to_verdict(self._engine.post_verify(self.run_id, agent, verdict_text))
        except Exception:
            return Verdict()

    def shared_shadow(self, **kwargs: Any) -> str:
        """Render the SHARED SHADOW lead->verify handoff (purpose/deliverable/... kwargs)."""
        try:
            return self._engine.shared_shadow_handoff(**kwargs)
        except Exception:
            return ""

    def assess_triangulation(self, verdicts: list[dict]) -> dict:
        """Independence-of-angle scoring of multiple verifier verdicts (for the review loop)."""
        try:
            from .triangulation import assess_triangulation
            return asdict(assess_triangulation(verdicts))
        except Exception:
            return {}

    def record_observation(self, was_true_positive: bool) -> None:
        """Feed graduation with an operator-confirmed true/false positive (the high-quality signal)."""
        try:
            self._engine.record_graduation_observation(was_true_positive)
        except Exception:
            pass

    def note_override_outcome(self, violations: list, retry_output: str, agent: str = "") -> None:
        try:
            self._engine.note_override_outcome(violations, retry_output, agent=agent)
        except Exception:
            pass

    def finish(self) -> dict:
        """Finalize the run: graduation tick + write the re-entry digest. Returns {mode, reentry_path}."""
        try:
            verdict = self._engine.finalize(self.run_id)
            path = self._engine.write_reentry_digest(run_id=self.run_id)
            return {"mode": _enum_value(getattr(verdict, "mode", None), "monitor"),
                    "reentry_path": str(path)}
        except Exception:
            return {}

    # --- read helpers (JSON-friendly) ---

    def active_decisions(self) -> list[dict]:
        try:
            return [
                {"title": d.title, "decision": d.decision_text,
                 "constrains": d.constrains, "unlocks": d.unlocks}
                for d in self._engine.decision_store.list_active()
            ]
        except Exception:
            return []

    def open_tensions(self) -> list[dict]:
        try:
            return [
                {"statement": t.statement, "state": t.dialectic_state}
                for t in self._engine.tension_store.list_open()
            ]
        except Exception:
            return []

    def reentry_text(self) -> str:
        try:
            return self._engine.build_reentry_digest_text(run_id=self.run_id)
        except Exception:
            return ""

    def trust_summary(self) -> dict:
        try:
            return self._engine.trust_manager.fleet_summary()
        except Exception:
            return {}


class NullCoherenceSession:
    """No-op session with identical signatures (returned when coherence is disabled or init fails)."""

    run_id = ""

    def before_lead(self, *a: Any, **k: Any) -> str:
        return ""

    def after_lead(self, *a: Any, **k: Any) -> Verdict:
        return Verdict()

    def before_verify(self, *a: Any, **k: Any) -> str:
        return ""

    def after_verify(self, *a: Any, **k: Any) -> Verdict:
        return Verdict()

    def shared_shadow(self, *a: Any, **k: Any) -> str:
        return ""

    def assess_triangulation(self, *a: Any, **k: Any) -> dict:
        return {}

    def record_observation(self, *a: Any, **k: Any) -> None:
        return None

    def note_override_outcome(self, *a: Any, **k: Any) -> None:
        return None

    def finish(self, *a: Any, **k: Any) -> dict:
        return {}

    def active_decisions(self, *a: Any, **k: Any) -> list:
        return []

    def open_tensions(self, *a: Any, **k: Any) -> list:
        return []

    def reentry_text(self, *a: Any, **k: Any) -> str:
        return ""

    def trust_summary(self, *a: Any, **k: Any) -> dict:
        return {}


def open_session(
    project_root: Any,
    run_id: str | None = None,
    config: Any = None,
) -> CoherenceSession | NullCoherenceSession:
    """Open a coherence session for a run.

    ``config`` may be a CoherenceConfig, a plain dict, or None (defaults). Returns a
    NullCoherenceSession when coherence is disabled or initialization fails — the host can call
    the same methods regardless.
    """
    try:
        from .models import CoherenceConfig
        if config is None:
            config = CoherenceConfig()
        elif isinstance(config, dict):
            config = CoherenceConfig(**config)
        if not getattr(config, "enabled", True):
            return NullCoherenceSession()
        from .engine import CoherenceEngine
        engine = CoherenceEngine(config, Path(project_root))
        return CoherenceSession(engine, run_id or str(uuid.uuid4()))
    except Exception:
        return NullCoherenceSession()
