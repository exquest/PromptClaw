import json
import unittest

from promptclaw.config import default_project_config
from promptclaw.router import (
    agent_catalog_markdown,
    detect_ambiguity,
    heuristic_route,
    infer_task_type,
    parse_route_decision,
    route_markdown,
)

class RouterTests(unittest.TestCase):
    def setUp(self):
        self.config = default_project_config("Router Test")

    def test_infer_task_type_code(self):
        task_type = infer_task_type("Implement a Python function and write tests.")
        self.assertEqual(task_type, "code")

    def test_infer_task_type_architecture(self):
        task_type = infer_task_type("Design the orchestrator state machine and handoff flow.")
        self.assertEqual(task_type, "architecture")

    def test_detect_ambiguity(self):
        ambiguous, question = detect_ambiguity("Make something good somehow")
        self.assertTrue(ambiguous)
        self.assertTrue(question)

    def test_heuristic_route_prefers_codex_for_code(self):
        decision = heuristic_route(self.config, "Implement a Python feature and fix failing tests.")
        self.assertEqual(decision.lead_agent, "codex")

    def test_heuristic_route_prefers_claude_for_architecture(self):
        decision = heuristic_route(self.config, "Design the orchestrator architecture and verification protocol.")
        self.assertEqual(decision.lead_agent, "claude")


class RouterEndToEndTests(unittest.TestCase):
    """End-to-end coverage for the heuristic router public surface."""

    def test_route_lifecycle_renders_markdown_and_round_trips_decision(self) -> None:
        config = default_project_config("Router E2E")

        catalog = agent_catalog_markdown(config)
        for agent_name in ("codex", "claude", "gemini"):
            assert f"- {agent_name}: enabled" in catalog
        assert "implementation" in catalog
        assert "verification" in catalog

        primary_query = (
            "Implement a Python module with tests and refactor the failing function."
        )
        primary = heuristic_route(config, primary_query)

        assert primary.ambiguous is False
        assert primary.clarification_question is None
        assert primary.task_type == "code"
        assert primary.lead_agent == "codex"
        assert primary.verifier_agent is not None
        assert primary.verifier_agent != primary.lead_agent
        assert primary.verifier_agent in config.agents
        assert config.agents[primary.verifier_agent].enabled is True
        assert primary.confidence > 0.5
        assert "codex" in primary.reason
        assert "code" in primary.subtask_brief

        trust_scores = {"codex": 0.0, "claude": 1.0, "gemini": 1.0}
        trust_shifted = heuristic_route(config, primary_query, trust_scores=trust_scores)
        assert trust_shifted.lead_agent != "codex"
        assert trust_shifted.lead_agent in config.agents
        assert trust_shifted.task_type == "code"

        ambiguous_query = "Make something good somehow"
        ambiguous = heuristic_route(config, ambiguous_query)
        assert ambiguous.ambiguous is True
        assert ambiguous.clarification_question
        assert ambiguous.confidence < primary.confidence

        rendered = route_markdown(primary)
        assert "# Route Decision" in rendered
        assert "- Ambiguous: no" in rendered
        assert f"- Lead agent: {primary.lead_agent}" in rendered
        assert f"- Verifier agent: {primary.verifier_agent}" in rendered
        assert f"- Task type: {primary.task_type}" in rendered
        assert f"- Confidence: {primary.confidence:.2f}" in rendered
        assert "## Reason" in rendered
        assert primary.reason in rendered
        assert "## Handoff brief" in rendered
        assert primary.subtask_brief in rendered
        assert "## Clarification question" not in rendered

        ambiguous_rendered = route_markdown(ambiguous)
        assert "- Ambiguous: yes" in ambiguous_rendered
        assert "## Clarification question" in ambiguous_rendered
        assert ambiguous.clarification_question in ambiguous_rendered

        decision_payload = {
            "ambiguous": primary.ambiguous,
            "clarification_question": primary.clarification_question,
            "lead_agent": primary.lead_agent,
            "verifier_agent": primary.verifier_agent,
            "reason": primary.reason,
            "subtask_brief": primary.subtask_brief,
            "task_type": primary.task_type,
            "confidence": primary.confidence,
        }
        round_tripped = parse_route_decision(json.dumps(decision_payload))
        assert round_tripped is not None
        assert round_tripped.lead_agent == primary.lead_agent
        assert round_tripped.verifier_agent == primary.verifier_agent
        assert round_tripped.task_type == primary.task_type
        assert round_tripped.ambiguous is primary.ambiguous
        assert round_tripped.reason == primary.reason
        assert round_tripped.subtask_brief == primary.subtask_brief
        assert round_tripped.confidence == primary.confidence

        diagnostic = {
            "catalog": catalog,
            "primary": decision_payload,
            "trust_shifted": {
                "lead_agent": trust_shifted.lead_agent,
                "task_type": trust_shifted.task_type,
                "ambiguous": trust_shifted.ambiguous,
            },
            "ambiguous": {
                "lead_agent": ambiguous.lead_agent,
                "task_type": ambiguous.task_type,
                "ambiguous": ambiguous.ambiguous,
                "clarification_question": ambiguous.clarification_question,
                "confidence": ambiguous.confidence,
            },
            "round_tripped": {
                "lead_agent": round_tripped.lead_agent,
                "verifier_agent": round_tripped.verifier_agent,
                "task_type": round_tripped.task_type,
            },
        }
        replayed = json.loads(json.dumps(diagnostic, sort_keys=True))
        assert replayed["primary"]["lead_agent"] == primary.lead_agent
        assert replayed["trust_shifted"]["lead_agent"] != "codex"
        assert replayed["ambiguous"]["ambiguous"] is True
        assert replayed["round_tripped"]["task_type"] == primary.task_type
