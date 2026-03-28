from __future__ import annotations

from pathlib import Path

from .agent_runtime import AgentRuntime
from .models import PromptClawConfig, RouteDecision
from .prompt_builder import build_routing_prompt, load_instruction
from .router import agent_catalog_markdown, heuristic_route, parse_route_decision

DEFAULT_CONTROL_PROMPT = """You are the PromptClaw control plane.
Route tasks to the best available agent.
Ask a clarification question only if execution is blocked by ambiguity.
Prefer a different verifier than the lead when one is available.
Return only the requested JSON shape."""

class ControlPlane:
    def __init__(self, config: PromptClawConfig, runtime: AgentRuntime, project_root: Path) -> None:
        self.config = config
        self.runtime = runtime
        self.project_root = project_root

    def decide(self, task_text: str, memory_text: str, prompt_path: Path, coherence_context: str = "") -> tuple[RouteDecision, str]:
        if self.config.control_plane.mode != "agent":
            decision = heuristic_route(self.config, task_text)
            return decision, "heuristic"
        agent_name = self.config.control_plane.agent
        if not agent_name or agent_name not in self.config.agents:
            if self.config.control_plane.allow_fallback:
                decision = heuristic_route(self.config, task_text)
                return decision, "heuristic-fallback"
            raise ValueError("control_plane.agent is not configured correctly")
        agent = self.config.agents[agent_name]
        instruction = load_instruction(
            self.project_root,
            "prompts/control/routing.md",
            DEFAULT_CONTROL_PROMPT,
        )
        catalog = agent_catalog_markdown(self.config)
        prompt_text = build_routing_prompt(
            control_instruction=instruction,
            task_text=task_text,
            memory_text=memory_text,
            agent_catalog=catalog,
            coherence_context=coherence_context,
        )
        prompt_path.write_text(prompt_text, encoding="utf-8")
        result = self.runtime.run(
            agent=agent,
            prompt_text=prompt_text,
            prompt_path=prompt_path,
            phase="routing",
            role="control",
            project_root=self.project_root,
            task_text=task_text,
        )
        decision = parse_route_decision(result.output_text)
        if decision is not None:
            return decision, agent_name
        if self.config.control_plane.allow_fallback:
            fallback = heuristic_route(self.config, task_text)
            return fallback, f"{agent_name}-fallback"
        raise ValueError("control plane returned malformed routing JSON")
