"""Coherence Engine — the main facade consulted by the orchestrator at every hook point."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .constitution import Constitution
from .decision_capture import parse_decision_blocks
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
from .prompt_injection import (
    format_constitutional_context,
    format_decision_context,
    format_tension_context,
)
from .reentry import build_reentry_digest
from .tension_capture import parse_tension_blocks
from .tension_store import SqliteTensionStore, Tension
from .trust import TrustManager


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    """Normalize text for dedup: case-folded, whitespace-collapsed."""
    return " ".join(text.split()).casefold()


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
        self._last_run_id: str | None = None  # most recently touched run, for digest defaulting
        # Decision store — uses same db directory as event store
        decision_db_path = project_root / ".promptclaw" / "coherence.db"
        self.decision_store = SqliteDecisionStore(decision_db_path)
        self.decision_store.migrate()
        # Tension store (held contradictions) — same db file as decisions/events
        self.tension_store = SqliteTensionStore(decision_db_path)
        self.tension_store.migrate()
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
        self._last_run_id = run_id
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

    def _emit_safe(self, run_id: str, event_type: str, **kwargs: Any) -> None:
        """Emit an event, swallowing any failure — for use inside best-effort guards."""
        try:
            self.emit(run_id, event_type, **kwargs)
        except Exception:
            pass

    def replay(self, run_id: str) -> list[CoherenceEvent]:
        """Replay all events for a run."""
        return self.event_store.replay(run_id)

    # --- 7 Hook Methods ---
    # Phase 1: All return approved verdicts (no-ops).
    # Phase 2+: These will query decision store, evaluate constitution, etc.

    def _build_injection(self, query_text: str, phase: str) -> str:
        """Assemble pre-hook context: relevant decisions + held tensions + constitutional rules."""
        parts: list[str] = []
        decision_ctx = format_decision_context(self.decision_store.query_relevant(query_text))
        if decision_ctx:
            parts.append(decision_ctx)
        tension_ctx = format_tension_context(self.tension_store.list_open())
        if tension_ctx:
            parts.append(tension_ctx)
        constitutional = format_constitutional_context(
            self.constitution.rules_for_phase(phase), self.config.mode
        )
        if constitutional:
            parts.append(constitutional)
        return "\n".join(parts)

    def pre_routing(self, run_id: str, task_text: str, memory_text: str) -> CoherenceVerdict:
        """Hook A: Before routing decision. Inject decision + tension + constitutional context."""
        self.emit(run_id, "coherence.pre_routing", phase="routing")
        injected = self._build_injection(task_text, "routing")
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
        """Hook C: Before lead agent runs. Inject decision + tension + constitutional context."""
        self.emit(run_id, "coherence.pre_lead", phase="lead", agent=agent)
        injected = self._build_injection(task_text, "lead")
        return CoherenceVerdict(approved=True, mode=self.config.mode, injected_context=injected)

    def post_lead(self, run_id: str, agent: str, output_text: str) -> CoherenceVerdict:
        """Hook D: After lead output. Assess against rules and decisions."""
        self.emit(run_id, "coherence.post_lead", phase="lead", agent=agent,
                  extra={"output_length": len(output_text)})
        # Capture any decisions the agent declared in ```decision blocks. Best-effort:
        # a capture failure must never affect the verdict, but it must leave a trace.
        try:
            self._capture_decisions(run_id, output_text)
        except Exception as exc:
            self._emit_safe(run_id, "coherence.decision_capture_failed", phase="lead",
                            agent=agent, extra={"error": str(exc)})
        try:
            self._capture_tensions(run_id, output_text)
        except Exception as exc:
            self._emit_safe(run_id, "coherence.tension_capture_failed", phase="lead",
                            agent=agent, extra={"error": str(exc)})
        violations = self.constitution.evaluate(output_text, phase="lead", agent=agent)
        blocked = self.constitution.should_block(violations, self.config.mode)
        trust_delta = self._update_trust(agent, violations)
        return CoherenceVerdict(
            approved=not blocked,
            violations=violations,
            trust_delta=trust_delta,
            mode=self.config.mode,
        )

    def _capture_decisions(self, run_id: str, output_text: str) -> list[Decision]:
        """Record decisions declared in ```decision blocks, skipping duplicate titles.

        Dedup is by normalized title (case-folded, whitespace-collapsed) against active
        decisions, so a re-emitted block (e.g. on retry) does not create duplicates.
        """
        blocks = parse_decision_blocks(output_text)
        if not blocks:
            return []  # common case: avoid querying/deserializing the store on every lead turn
        existing_titles = {_normalize(d.title) for d in self.decision_store.list_active()}
        captured: list[Decision] = []
        for block in blocks:
            title = block["title"]
            norm = _normalize(title)
            if norm in existing_titles:
                continue
            decision = self.record_decision(
                title=title,
                context=block.get("context", ""),
                decision_text=block.get("decision_text", title),
                rationale=block.get("rationale", ""),
                tags=block.get("tags") or [],
                file_paths=block.get("file_paths") or [],
                unlocks=block.get("unlocks") or [],
                constrains=block.get("constrains") or [],
            )
            existing_titles.add(norm)
            captured.append(decision)
            self.emit(run_id, "coherence.decision_captured", phase="lead",
                      extra={"decision_id": decision.decision_id, "title": title})
        return captured

    def _capture_tensions(self, run_id: str, output_text: str) -> list[Tension]:
        """Record tensions declared in ```tension blocks, skipping duplicate statements.

        Dedup is by normalized statement against open tensions, so a re-emitted block does
        not create duplicates.
        """
        blocks = parse_tension_blocks(output_text)
        if not blocks:
            return []  # common case: avoid querying the store on every lead turn
        existing = {_normalize(t.statement) for t in self.tension_store.list_open()}
        captured: list[Tension] = []
        for block in blocks:
            statement = block["statement"]
            norm = _normalize(statement)
            if norm in existing:
                continue
            tension = self.record_tension(
                statement=statement,
                dialectic_state=block.get("dialectic_state", ""),
                resolution_criterion=block.get("resolution_criterion", ""),
                between=block.get("between") or [],
            )
            existing.add(norm)
            captured.append(tension)
            self.emit(run_id, "coherence.tension_captured", phase="lead",
                      extra={"tension_id": tension.tension_id, "statement": statement})
        return captured

    def pre_verify(self, run_id: str, agent: str, lead_output: str) -> CoherenceVerdict:
        """Hook E: Before verification. Inject decision + tension + constitutional context."""
        self.emit(run_id, "coherence.pre_verify", phase="verify", agent=agent)
        injected = self._build_injection(lead_output, "verify")
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
        # Best-effort: refresh the re-entry digest so resuming is fast. Never let a
        # failed write break finalize, but record the failure so it isn't invisible.
        try:
            self.write_reentry_digest(run_id=run_id)
        except Exception as exc:
            self._emit_safe(run_id, "coherence.reentry_digest_failed", phase="complete",
                            extra={"error": str(exc)})
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
        unlocks: list[str] | None = None,
        constrains: list[str] | None = None,
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
            unlocks=unlocks or [],
            constrains=constrains or [],
        )
        self.decision_store.record(decision)
        return decision

    # --- Tension management (held contradictions; surfaced, not blocked) ---

    def record_tension(
        self,
        statement: str,
        dialectic_state: str = "",
        resolution_criterion: str = "",
        between: list[str] | None = None,
    ) -> Tension:
        """Record a new open tension and return it."""
        tension = Tension(
            tension_id=str(uuid.uuid4()),
            created_at=_utc_now(),
            statement=statement,
            dialectic_state=dialectic_state,
            resolution_criterion=resolution_criterion,
            between=between or [],
            status="open",
            resolved_by=None,
        )
        self.tension_store.record(tension)
        return tension

    def resolve_tension(self, tension_id: str, resolved_by: str | None = None) -> None:
        """Mark a tension resolved (settled); it stops being surfaced."""
        self.tension_store.update_status(tension_id, "resolved", resolved_by=resolved_by)

    def dissolve_tension(self, tension_id: str) -> None:
        """Mark a tension dissolved (it was not a real contradiction); it stops being surfaced."""
        self.tension_store.update_status(tension_id, "dissolved")

    # --- Re-entry digest (the "Prints" artifact) ---

    def build_reentry_digest_text(self, run_id: str | None = None) -> str:
        """Render the re-entry digest for a run.

        Defaults to the run this engine instance most recently touched; if this is a fresh
        process with no emits yet, falls back to the globally latest event's run.
        """
        if run_id is None:
            run_id = self._last_run_id
        if run_id is None:
            all_events = self.event_store.replay_all()
            run_id = all_events[-1].run_id if all_events else None
        events = self.event_store.replay(run_id) if run_id else []
        decisions = self.decision_store.list_active()
        tensions = [
            {"statement": t.statement, "dialectic_state": t.dialectic_state}
            for t in self.tension_store.list_open()
        ]
        return build_reentry_digest(
            events, decisions, generated_at=_utc_now(), run_id=run_id, tensions=tensions
        )

    def write_reentry_digest(
        self, path: Path | None = None, run_id: str | None = None
    ) -> Path:
        """Write the re-entry digest to disk and return its path.

        Defaults to ``<project_root>/.promptclaw/reentry.md`` — always the current
        re-entry point, overwritten each run.
        """
        if path is None:
            path = self.project_root / ".promptclaw" / "reentry.md"
        text = self.build_reentry_digest_text(run_id=run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


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

    def build_reentry_digest_text(self, *args: Any, **kwargs: Any) -> str:
        return ""

    def write_reentry_digest(self, *args: Any, **kwargs: Any) -> None:
        return None

    def record_tension(self, *args: Any, **kwargs: Any) -> None:
        return None

    def resolve_tension(self, *args: Any, **kwargs: Any) -> None:
        return None

    def dissolve_tension(self, *args: Any, **kwargs: Any) -> None:
        return None
