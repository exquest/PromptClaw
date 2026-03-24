import unittest

from promptclaw.config import default_project_config
from promptclaw.router import detect_ambiguity, heuristic_route, infer_task_type

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
