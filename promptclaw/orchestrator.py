from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .agent_runtime import AgentRuntime
from .artifacts import ArtifactManager
from .config import load_config
from .control_plane import ControlPlane
from .diagnostics import Diagnosis, diagnose, format_diagnosis
from .memory import MemoryStore
from .models import Event, PromptClawConfig, RouteDecision, RunState
from .paths import ProjectPaths
from .prompt_builder import (
    build_lead_prompt,
    build_retry_prompt,
    build_verify_prompt,
    load_instruction,
)
from .router import heuristic_route, route_markdown
from .coherence.engine import CoherenceEngine, NullCoherenceEngine
from .coherence.models import CoherenceConfig
from .state_store import StateStore
from .utils import parse_verdict, read_text, slugify, truncate, utc_now, write_text

DEFAULT_LEAD_INSTRUCTION = "You are a PromptClaw worker. Produce useful markdown output for the assigned task."
DEFAULT_VERIFY_INSTRUCTION = "You are a PromptClaw verifier. Review the lead output and emit a verdict line."

class PromptClawOrchestrator:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.config: PromptClawConfig = load_config(project_root)
        self.paths = ProjectPaths(project_root=project_root, config=self.config)
        self.runtime = AgentRuntime()
        self.control_plane = ControlPlane(self.config, self.runtime, self.project_root)
        self.artifacts = None
        self.state_store = StateStore(self.paths)
        self.memory_store = MemoryStore(self.paths)
        try:
            coherence_config = self.config.coherence or CoherenceConfig()
            self.coherence = CoherenceEngine(coherence_config, self.project_root)
        except Exception:
            self.coherence = NullCoherenceEngine()

    def run(self, task_text: str, title: str = "PromptClaw Task") -> RunState:
        timestamp = utc_now().replace(":", "").replace("-", "").replace("+00:00", "z")
        run_id = f"{timestamp}-{slugify(title)}"
        self.artifacts = ArtifactManager(self.paths, run_id)
        self.artifacts.create_run_layout()
        task_path = self.artifacts.write_task(task_text)
        memory_text = self.memory_store.read()

        state = RunState(
            run_id=run_id,
            title=title,
            status="running",
            current_phase="routing",
            created_at=utc_now(),
            updated_at=utc_now(),
            task_text=task_text,
        )
        self._log(state, "run_started", f"Run created for '{title}'")

        # --- Hook A: Pre-routing coherence ---
        coherence_a = self.coherence.pre_routing(run_id, task_text, memory_text)

        # Gather trust scores for trust-aware routing
        trust_scores: dict[str, float] | None = None
        if hasattr(self.coherence, 'trust_manager'):
            raw_scores = self.coherence.trust_manager.all_scores()
            if raw_scores:
                trust_scores = {agent: ts.score for agent, ts in raw_scores.items()}

        # --- Phase: Routing ---
        try:
            route_prompt_path = self.paths.run_prompts(run_id) / "control-routing.md"
            decision, routing_mode = self.control_plane.decide(
                task_text, memory_text, route_prompt_path,
                coherence_context=coherence_a.injected_context,
                trust_scores=trust_scores,
            )
        except Exception as exc:
            decision, routing_mode = self._recover_routing(state, exc, task_text)

        state.route_decision = asdict(decision)
        state.lead_agent = decision.lead_agent
        state.verifier_agent = decision.verifier_agent or ""
        state.updated_at = utc_now()
        self.artifacts.write_route_json(asdict(decision))
        self.artifacts.write_route_markdown(route_markdown(decision))
        self._log(state, "route_decided", f"Routing via {routing_mode}: lead={decision.lead_agent}, verifier={decision.verifier_agent or 'none'}", phase="routing")

        # --- Hook B: Post-routing coherence ---
        coherence_b = self.coherence.post_routing(run_id, asdict(decision))

        if decision.ambiguous and self.config.routing.ask_user_on_ambiguity:
            state.status = "awaiting_user"
            state.current_phase = "clarification"
            state.clarification_question = decision.clarification_question
            question_markdown = (
                "# Clarification Needed\n\n"
                "The orchestrator paused because the task is ambiguous.\n\n"
                "## Question\n"
                f"{decision.clarification_question or 'Please clarify the task.'}\n"
            )
            question_path = self.artifacts.write_summary("clarification-request.md", question_markdown)
            state.final_summary_path = str(question_path.relative_to(self.project_root))
            state.updated_at = utc_now()
            self._log(state, "awaiting_user", "Run paused for clarification", phase="clarification")
            self.state_store.save(state)
            self.memory_store.append_run_summary(state, question_markdown)
            return state

        # --- Phase: Lead ---
        try:
            lead_output = self._run_lead(state, decision, memory_text)
        except Exception as exc:
            lead_output = self._recover_lead(state, exc, decision, memory_text)

        # --- Phase: Verification ---
        final_summary = ""
        if self.config.routing.verification_enabled and decision.verifier_agent:
            try:
                final_summary = self._run_verification_cycle(state, decision, lead_output, memory_text)
            except Exception as exc:
                final_summary = self._recover_verification(state, exc, lead_output, decision)
        else:
            final_summary = self._finalize_without_verification(state, lead_output)

        # --- Hook G: Finalization coherence audit ---
        coherence_g = self.coherence.finalize(run_id)
        state.enforcement_mode = coherence_g.mode.value if hasattr(coherence_g.mode, 'value') else str(coherence_g.mode)

        state.status = "complete"
        state.current_phase = "complete"
        state.updated_at = utc_now()
        summary_path = self.artifacts.write_summary("final-summary.md", final_summary)
        state.final_summary_path = str(summary_path.relative_to(self.project_root))
        self._log(state, "run_complete", "Run completed", phase="complete")
        self.state_store.save(state)
        self.memory_store.append_run_summary(state, final_summary)
        return state

    def resume(self, run_id: str, answer: str) -> RunState:
        previous = self.state_store.load(run_id)
        if previous.status != "awaiting_user":
            raise ValueError(f"Run {run_id} is not awaiting user input")
        resumed_task = (
            previous.task_text.strip()
            + "\n\n# Clarification Answer\n"
            + answer.strip()
        )
        return self.run(task_text=resumed_task, title=previous.title + " (resumed)")

    # --- Recovery methods ---

    def _recover_routing(self, state: RunState, exc: Exception, task_text: str) -> tuple[RouteDecision, str]:
        """Recover from a routing failure by falling back to heuristic routing."""
        diag = diagnose(exc, phase="routing")
        self._record_error(state, diag)
        self._log(state, "routing_error", f"Routing failed: {diag.message}. Falling back to heuristic.", phase="routing")
        print(format_diagnosis(diag), file=sys.stderr)
        try:
            decision = heuristic_route(self.config, task_text)
            state.recovery_actions.append("routing: fell back to heuristic routing")
            return decision, "heuristic-recovery"
        except Exception as fallback_exc:
            # Heuristic also failed — create a minimal decision using the first enabled agent
            diag2 = diagnose(fallback_exc, phase="routing")
            self._record_error(state, diag2)
            first_agent = next(
                (name for name, a in self.config.agents.items() if a.enabled),
                next(iter(self.config.agents), "unknown"),
            )
            state.recovery_actions.append(f"routing: emergency fallback to agent '{first_agent}'")
            return RouteDecision(
                ambiguous=False,
                clarification_question=None,
                lead_agent=first_agent,
                verifier_agent=None,
                reason="Emergency fallback — routing failed",
                subtask_brief=task_text[:200],
                task_type="general",
                confidence=0.1,
            ), "emergency-fallback"

    def _recover_lead(self, state: RunState, exc: Exception, decision: RouteDecision, memory_text: str) -> str:
        """Recover from a lead agent failure by trying an alternate agent or mock mode."""
        diag = diagnose(exc, phase="lead", context={"agent_name": decision.lead_agent})
        self._record_error(state, diag)
        self._log(state, "lead_error", f"Lead agent failed: {diag.message}. Attempting recovery.", phase="lead")
        print(format_diagnosis(diag), file=sys.stderr)

        # Try a different enabled agent
        alternate = self._find_alternate_agent(decision.lead_agent)
        if alternate:
            state.recovery_actions.append(f"lead: switched from '{decision.lead_agent}' to '{alternate}'")
            decision.lead_agent = alternate
            state.lead_agent = alternate
            try:
                return self._run_lead(state, decision, memory_text)
            except Exception:
                pass  # Fall through to mock fallback

        # Final fallback: generate mock output
        state.recovery_actions.append(f"lead: fell back to mock output for '{decision.lead_agent}'")
        return (
            f"# Recovery Output (mock fallback)\n\n"
            f"The lead agent '{decision.lead_agent}' encountered an error and could not produce output.\n\n"
            f"**Error:** {diag.message}\n\n"
            f"## Suggestions to fix\n"
            + "\n".join(f"- {s}" for s in diag.suggestions)
            + f"\n\n## Original Task\n{state.task_text[:500]}\n"
        )

    def _recover_verification(self, state: RunState, exc: Exception, lead_output: str, decision: RouteDecision) -> str:
        """Recover from a verification failure by skipping verification."""
        diag = diagnose(exc, phase="verify", context={"agent_name": decision.verifier_agent})
        self._record_error(state, diag)
        self._log(state, "verify_error", f"Verification failed: {diag.message}. Skipping verification.", phase="verify")
        print(format_diagnosis(diag), file=sys.stderr)
        state.recovery_actions.append(f"verify: skipped verification due to error in '{decision.verifier_agent}'")
        return (
            "# Final Summary\n\n"
            f"- Lead agent: {decision.lead_agent}\n"
            f"- Verification: skipped (verifier error — see suggestions below)\n"
            f"- Retries used: {state.retries_used}\n\n"
            f"## Verification Error\n"
            f"{diag.message}\n\n"
            f"## Suggestions\n"
            + "\n".join(f"- {s}" for s in diag.suggestions)
            + f"\n\n## Lead output excerpt\n"
            f"{truncate(lead_output, 5000)}\n"
        )

    def _find_alternate_agent(self, exclude: str) -> str | None:
        """Find another enabled agent to use as a fallback."""
        for name, agent in self.config.agents.items():
            if agent.enabled and name != exclude:
                return name
        return None

    def _record_error(self, state: RunState, diag: Diagnosis) -> None:
        """Record an error diagnosis on the run state."""
        state.errors.append({
            "phase": diag.phase,
            "error_type": diag.error_type,
            "message": diag.message,
            "suggestions": diag.suggestions,
            "auto_recovered": diag.auto_recoverable,
            "recovery_action": diag.recovery_action,
        })

    # --- Original phase methods (unchanged logic) ---

    def _run_lead(self, state: RunState, decision: RouteDecision, memory_text: str) -> str:
        state.current_phase = "lead"
        agent = self.config.agents[decision.lead_agent]
        instruction = load_instruction(self.project_root, agent.instruction_file, DEFAULT_LEAD_INSTRUCTION)
        # --- Hook C: Pre-lead coherence ---
        coherence_c = self.coherence.pre_lead(state.run_id, agent.name, state.task_text)
        prompt_text = build_lead_prompt(
            agent_instruction=instruction,
            task_text=state.task_text,
            decision=decision,
            memory_text=memory_text,
            coherence_context=coherence_c.injected_context,
        )
        prompt_path = self.artifacts.write_prompt(f"lead-{agent.name}.md", prompt_text)
        result = self.runtime.run(
            agent=agent,
            prompt_text=prompt_text,
            prompt_path=prompt_path,
            phase="lead",
            role="lead",
            project_root=self.project_root,
            task_text=state.task_text,
        )
        output_path = self.artifacts.write_output(f"lead-{agent.name}.md", result.output_text)
        self._log(state, "lead_complete", f"Lead output written by {agent.name}", phase="lead", agent=agent.name, role="lead")

        # --- Hook D: Post-lead coherence assessment ---
        coherence_d = self.coherence.post_lead(state.run_id, agent.name, result.output_text)
        if not coherence_d.approved:
            violation_summary = "; ".join(
                v.rule_id for v in coherence_d.violations
            ) if coherence_d.violations else "constitutional violation"
            state.coherence_violations.extend(
                {"phase": "lead", "rule": v.rule_id, "severity": v.severity.value}
                for v in (coherence_d.violations or [])
            )
            self._log(state, "coherence_blocked_lead", f"Lead output blocked: {violation_summary}", phase="lead", agent=agent.name)

        return result.output_text

    def _run_verification_cycle(self, state: RunState, decision: RouteDecision, lead_output: str, memory_text: str) -> str:
        verifier = self.config.agents[decision.verifier_agent]  # type: ignore[index]
        instruction = load_instruction(self.project_root, verifier.instruction_file, DEFAULT_VERIFY_INSTRUCTION)
        # --- Hook E: Pre-verify coherence ---
        coherence_e = self.coherence.pre_verify(state.run_id, verifier.name, lead_output)
        verify_prompt = build_verify_prompt(
            agent_instruction=instruction,
            task_text=state.task_text,
            decision=decision,
            lead_output=lead_output,
            memory_text=memory_text,
            coherence_context=coherence_e.injected_context,
        )
        self.artifacts.write_handoff(
            "lead-to-verify.md",
            "# Handoff\n\n"
            f"Lead agent: {decision.lead_agent}\n\n"
            f"Verifier agent: {decision.verifier_agent}\n\n"
            "## Brief\n"
            f"{decision.subtask_brief}\n",
        )
        verify_prompt_path = self.artifacts.write_prompt(f"verify-{verifier.name}.md", verify_prompt)
        verify_result = self.runtime.run(
            agent=verifier,
            prompt_text=verify_prompt,
            prompt_path=verify_prompt_path,
            phase="verify",
            role="verify",
            project_root=self.project_root,
            task_text=state.task_text,
        )
        self.artifacts.write_output(f"verify-{verifier.name}.md", verify_result.output_text)
        verdict = parse_verdict(verify_result.output_text) or "PASS_WITH_NOTES"
        self._log(state, "verify_complete", f"Verifier {verifier.name} returned {verdict}", phase="verify", agent=verifier.name, role="verify")

        # --- Hook F: Post-verify coherence override ---
        coherence_f = self.coherence.post_verify(state.run_id, verifier.name, verify_result.output_text)
        if not coherence_f.approved:
            violation_summary = "; ".join(
                v.rule_id for v in coherence_f.violations
            ) if coherence_f.violations else "constitutional violation"
            state.coherence_violations.extend(
                {"phase": "verify", "rule": v.rule_id, "severity": v.severity.value}
                for v in (coherence_f.violations or [])
            )
            self._log(state, "coherence_override_verdict", f"Verdict overridden to FAIL: {violation_summary}", phase="verify", agent=verifier.name)
            verdict = "FAIL"

        if verdict == "FAIL" and state.retries_used < self.config.routing.max_retries:
            state.retries_used += 1
            retry_agent = self.config.agents[decision.lead_agent]
            retry_instruction = load_instruction(self.project_root, retry_agent.instruction_file, DEFAULT_LEAD_INSTRUCTION)
            retry_prompt = build_retry_prompt(
                agent_instruction=retry_instruction,
                task_text=state.task_text,
                verifier_output=verify_result.output_text,
                prior_output=lead_output,
                decision=decision,
            )
            retry_prompt_path = self.artifacts.write_prompt(f"retry-{retry_agent.name}.md", retry_prompt)
            retry_result = self.runtime.run(
                agent=retry_agent,
                prompt_text=retry_prompt,
                prompt_path=retry_prompt_path,
                phase="retry",
                role="lead",
                project_root=self.project_root,
                task_text=state.task_text,
            )
            retry_output_path = self.artifacts.write_output(f"retry-{retry_agent.name}.md", retry_result.output_text)
            self._log(state, "retry_complete", f"Retry completed by {retry_agent.name}", phase="retry", agent=retry_agent.name, role="lead")
            summary = (
                "# Final Summary\n\n"
                f"- Lead agent: {decision.lead_agent}\n"
                f"- Verifier agent: {decision.verifier_agent}\n"
                f"- Verification verdict: {verdict} (after retry)\n"
                f"- Retries used: {state.retries_used}\n\n"
                "## Final output\n"
                f"{truncate(retry_result.output_text, 8000)}\n"
            )
            return summary

        summary = (
            "# Final Summary\n\n"
            f"- Lead agent: {decision.lead_agent}\n"
            f"- Verifier agent: {decision.verifier_agent}\n"
            f"- Verification verdict: {verdict}\n"
            f"- Retries used: {state.retries_used}\n\n"
            "## Lead output excerpt\n"
            f"{truncate(lead_output, 5000)}\n\n"
            "## Verification excerpt\n"
            f"{truncate(verify_result.output_text, 5000)}\n"
        )
        return summary

    def _finalize_without_verification(self, state: RunState, lead_output: str) -> str:
        return (
            "# Final Summary\n\n"
            f"- Lead agent: {state.lead_agent}\n"
            "- Verification: disabled or no verifier available\n\n"
            "## Output\n"
            f"{truncate(lead_output, 8000)}\n"
        )

    def _log(
        self,
        state: RunState,
        event_type: str,
        message: str,
        phase: str = "",
        agent: str = "",
        role: str = "",
    ) -> None:
        event = Event(
            timestamp=utc_now(),
            event_type=event_type,
            message=message,
            phase=phase,
            agent=agent,
            role=role,
        )
        state.events.append(event)
        if self.artifacts:
            self.artifacts.append_event(event)
        # Emit to coherence event store
        self.coherence.emit(
            run_id=state.run_id,
            event_type=event_type,
            message=message,
            phase=phase,
            agent=agent,
            role=role,
        )
