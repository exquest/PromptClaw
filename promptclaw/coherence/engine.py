"""Coherence Engine — the main facade consulted by the orchestrator at every hook point."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .constitution import Constitution
from .decision_store import Decision, SqliteDecisionStore
from .event_store import EventStoreBackend, SqliteEventStore
from .graduation import GraduationManager
from .models import (
    CoherenceConfig,
    CoherenceEvent,
    CoherenceVerdict,
    EnforcementMode,
    ViolationSeverity,
)
from .prompt_injection import format_constitutional_context, format_decision_context
from .trust import TrustManager


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class CoherenceEngine:
    """Core coherence engine wired into the orchestrator via 7 hooks.

    Phase 1: Event sourcing only. All hooks return approved verdicts.
    Phase 2+: Decision store, constitution, trust, graduation added incrementally.
    """

    def __init__(self, config: CoherenceConfig, project_root: Path) -> None:
        self.config = config
        self.project_root = project_root
        self.event_store: EventStoreBackend = self._create_event_store(config, project_root)
        self.event_store.migrate()
        self._sequence_counters: dict[str, int] = {}
        # Decision store — uses same db directory as event store
        decision_db_path = project_root / ".promptclaw" / "coherence.db"
        self.decision_store = SqliteDecisionStore(decision_db_path)
        self.decision_store.migrate()
        # Constitution
        constitution_file = project_root / config.constitution_path
        if constitution_file.exists():
            self.constitution = Constitution(constitution_file)
        else:
            self.constitution = Constitution(None)
        # Trust & graduation
        self.trust_manager = TrustManager()
        self.graduation_manager = GraduationManager(config)

    def _create_event_store(self, config: CoherenceConfig, project_root: Path) -> EventStoreBackend:
        if config.database_url and config.database_url.startswith("postgresql"):
            from .event_store import PostgresEventStore
            return PostgresEventStore(config.database_url, config.redis_url)
        # Default: SQLite in .promptclaw/coherence.db
        db_path = project_root / ".promptclaw" / "coherence.db"
        return SqliteEventStore(db_path)

    def _next_seq(self, run_id: str) -> int:
        seq = self._sequence_counters.get(run_id, 0)
        self._sequence_counters[run_id] = seq + 1
        return seq

    # --- Event emission ---

    def emit(self, run_id: str, event_type: str, message: str = "",
             phase: str = "", agent: str = "", role: str = "",
             extra: dict[str, Any] | None = None) -> CoherenceEvent:
        """Append an event to the store."""
        payload = {"message": message}
        if extra:
            payload.update(extra)
        event = CoherenceEvent(
            event_id=str(uuid.uuid4()),
            run_id=run_id,
            timestamp=_utc_now(),
            event_type=event_type,
            phase=phase,
            agent=agent,
            role=role,
            payload=payload,
            sequence_number=self._next_seq(run_id),
        )
        self.event_store.append(event)
        return event

    def replay(self, run_id: str) -> list[CoherenceEvent]:
        """Replay all events for a run."""
        return self.event_store.replay(run_id)

    # --- 7 Hook Methods ---
    # Phase 1: All return approved verdicts (no-ops).
    # Phase 2+: These will query decision store, evaluate constitution, etc.

    def pre_routing(self, run_id: str, task_text: str, memory_text: str) -> CoherenceVerdict:
        """Hook A: Before routing decision. Inject decision + constitutional context."""
        self.emit(run_id, "coherence.pre_routing", phase="routing")
        decisions = self.decision_store.query_relevant(task_text)
        injected = format_decision_context(decisions)
        rules = self.constitution.rules_for_phase("routing")
        constitutional = format_constitutional_context(rules, self.config.mode)
        if constitutional:
            injected = (injected + "\n" + constitutional) if injected else constitutional
        return CoherenceVerdict(approved=True, mode=self.config.mode, injected_context=injected)

    def post_routing(self, run_id: str, decision_data: dict[str, Any]) -> CoherenceVerdict:
        """Hook B: After routing decision. Validate against constitution."""
        self.emit(run_id, "coherence.post_routing", phase="routing",
                  extra={"decision": decision_data})
        # Evaluate routing decision text against constitution
        decision_text = str(decision_data)
        violations = self.constitution.evaluate(decision_text, phase="routing")
        blocked = self.constitution.should_block(violations, self.config.mode)
        # Update trust for the routing agent (use lead_agent if available)
        agent = decision_data.get("lead_agent", "router")
        self._update_trust(agent, violations)
        return CoherenceVerdict(
            approved=not blocked,
            violations=violations,
            mode=self.config.mode,
        )

    def pre_lead(self, run_id: str, agent: str, task_text: str) -> CoherenceVerdict:
        """Hook C: Before lead agent runs. Inject decision + constitutional context."""
        self.emit(run_id, "coherence.pre_lead", phase="lead", agent=agent)
        decisions = self.decision_store.query_relevant(task_text)
        injected = format_decision_context(decisions)
        rules = self.constitution.rules_for_phase("lead")
        constitutional = format_constitutional_context(rules, self.config.mode)
        if constitutional:
            injected = (injected + "\n" + constitutional) if injected else constitutional
        return CoherenceVerdict(approved=True, mode=self.config.mode, injected_context=injected)

    def post_lead(self, run_id: str, agent: str, output_text: str) -> CoherenceVerdict:
        """Hook D: After lead output. Assess against rules and decisions."""
        self.emit(run_id, "coherence.post_lead", phase="lead", agent=agent,
                  extra={"output_length": len(output_text)})
        violations = self.constitution.evaluate(output_text, phase="lead", agent=agent)
        blocked = self.constitution.should_block(violations, self.config.mode)
        trust_delta = self._update_trust(agent, violations)
        return CoherenceVerdict(
            approved=not blocked,
            violations=violations,
            trust_delta=trust_delta,
            mode=self.config.mode,
        )

    def pre_verify(self, run_id: str, agent: str, lead_output: str) -> CoherenceVerdict:
        """Hook E: Before verification. Inject decision + constitutional context."""
        self.emit(run_id, "coherence.pre_verify", phase="verify", agent=agent)
        decisions = self.decision_store.query_relevant(lead_output)
        injected = format_decision_context(decisions)
        rules = self.constitution.rules_for_phase("verify")
        constitutional = format_constitutional_context(rules, self.config.mode)
        if constitutional:
            injected = (injected + "\n" + constitutional) if injected else constitutional
        return CoherenceVerdict(approved=True, mode=self.config.mode, injected_context=injected)

    def post_verify(self, run_id: str, agent: str, verdict: str) -> CoherenceVerdict:
        """Hook F: After verification verdict. Override if constitutional violation."""
        self.emit(run_id, "coherence.post_verify", phase="verify", agent=agent,
                  extra={"verdict": verdict})
        violations = self.constitution.evaluate(verdict, phase="verify", agent=agent)
        blocked = self.constitution.should_block(violations, self.config.mode)
        trust_delta = self._update_trust(agent, violations)
        return CoherenceVerdict(
            approved=not blocked,
            violations=violations,
            trust_delta=trust_delta,
            mode=self.config.mode,
        )

    def finalize(self, run_id: str) -> CoherenceVerdict:
        """Hook G: Final compliance audit of entire run."""
        self.emit(run_id, "coherence.finalize", phase="complete")
        self.graduation_manager.increment_run()
        new_mode = self.graduation_manager.evaluate_promotion()
        if new_mode != self.config.mode:
            self.config.enforcement_mode = new_mode.value
        return CoherenceVerdict(approved=True, mode=self.config.mode)

    # --- Trust helpers ---

    def _update_trust(self, agent: str, violations: list[Any]) -> float:
        """Apply trust updates based on violations and return net delta."""
        if not violations:
            self.trust_manager.apply_compliant_action(agent)
            return self.trust_manager.COMPLIANT_REWARD

        delta = 0.0
        for v in violations:
            if v.severity == ViolationSeverity.HARD:
                self.trust_manager.apply_hard_violation(agent)
                delta += self.trust_manager.HARD_PENALTY
            else:
                self.trust_manager.apply_soft_violation(agent)
                delta += self.trust_manager.SOFT_PENALTY
        return delta

    def record_graduation_observation(self, was_true_positive: bool) -> None:
        """Record whether a detected violation was a true or false positive."""
        self.graduation_manager.record_observation(was_true_positive)

    # --- Decision management ---

    def record_decision(
        self,
        title: str,
        context: str,
        decision_text: str,
        rationale: str,
        tags: list[str] | None = None,
        file_paths: list[str] | None = None,
    ) -> Decision:
        """Record a new architectural decision and return it."""
        decision = Decision(
            decision_id=str(uuid.uuid4()),
            created_at=_utc_now(),
            title=title,
            context=context,
            decision_text=decision_text,
            rationale=rationale,
            status="active",
            superseded_by=None,
            tags=tags or [],
            file_paths=file_paths or [],
        )
        self.decision_store.record(decision)
        return decision


class NullCoherenceEngine:
    """No-op fallback when coherence fails to initialize."""

    def emit(self, *args: Any, **kwargs: Any) -> None:
        pass

    def replay(self, run_id: str) -> list:
        return []

    def pre_routing(self, *args: Any, **kwargs: Any) -> CoherenceVerdict:
        return CoherenceVerdict()

    def post_routing(self, *args: Any, **kwargs: Any) -> CoherenceVerdict:
        return CoherenceVerdict()

    def pre_lead(self, *args: Any, **kwargs: Any) -> CoherenceVerdict:
        return CoherenceVerdict()

    def post_lead(self, *args: Any, **kwargs: Any) -> CoherenceVerdict:
        return CoherenceVerdict()

    def pre_verify(self, *args: Any, **kwargs: Any) -> CoherenceVerdict:
        return CoherenceVerdict()

    def post_verify(self, *args: Any, **kwargs: Any) -> CoherenceVerdict:
        return CoherenceVerdict()

    def finalize(self, *args: Any, **kwargs: Any) -> CoherenceVerdict:
        return CoherenceVerdict()
