"""Tests for the coherence standing-instruction text (Phase 1a)."""

from __future__ import annotations

import unittest

from promptclaw.coherence.protocol import (
    BLOCK_CONTRACT,
    WORKING_PROTOCOL,
    coherence_instructions,
)


class TestProtocol(unittest.TestCase):
    def test_working_protocol_anchors(self):
        self.assertIn("SHADOWLAND WORKING PROTOCOL", WORKING_PROTOCOL)
        self.assertIn("READING THE SHAPE", WORKING_PROTOCOL)
        self.assertIn("Ask one question", WORKING_PROTOCOL)

    def test_block_contract_decision_schema(self):
        self.assertIn("```decision", BLOCK_CONTRACT)
        self.assertIn("title:", BLOCK_CONTRACT)
        self.assertIn("constrains:", BLOCK_CONTRACT)

    def test_block_contract_tension_schema(self):
        self.assertIn("```tension", BLOCK_CONTRACT)
        self.assertIn("statement:", BLOCK_CONTRACT)
        self.assertIn("between:", BLOCK_CONTRACT)

    def test_coherence_instructions_composes_both(self):
        text = coherence_instructions()
        self.assertIn("SHADOWLAND WORKING PROTOCOL", text)
        self.assertIn("```decision", text)
        self.assertIn("```tension", text)


class TestProtocolWiring(unittest.TestCase):
    def test_scaffolded_agents_carry_protocol(self):
        from promptclaw.templates import project_scaffold

        files = project_scaffold("DemoClaw")
        for path in ("prompts/agents/codex.md", "prompts/agents/claude.md", "prompts/agents/gemini.md"):
            self.assertIn(path, files)
            self.assertIn("SHADOWLAND WORKING PROTOCOL", files[path])
            self.assertIn("```decision", files[path])

    def test_default_instructions_carry_protocol(self):
        from promptclaw.orchestrator import DEFAULT_LEAD_INSTRUCTION, DEFAULT_VERIFY_INSTRUCTION

        self.assertIn("```decision", DEFAULT_LEAD_INSTRUCTION)
        self.assertIn("SHADOWLAND WORKING PROTOCOL", DEFAULT_VERIFY_INSTRUCTION)


if __name__ == "__main__":
    unittest.main()
