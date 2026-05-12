"""Tests for the PromptClaw startup wizard.

depth: 2
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.bootstrap import init_project
from promptclaw.config import load_config
from promptclaw.wizard import (
    DEFAULT_AGENT_STRENGTHS,
    StartupWizard,
    infer_capabilities,
    lead_lane_text,
    looks_vague,
    mentions_any,
    parse_agent_roster,
    run_startup_wizard,
    sentence_or_list,
    verification_fit_text,
)


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-wizard-"))
        init_project(self.temp_dir, "Wizard Claw")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_parse_agent_roster_defaults(self):
        self.assertEqual(parse_agent_roster(""), ["codex", "claude", "gemini"])

    def test_wizard_writes_profile_and_updates_config(self):
        answers = iter([
            "A claw for software planning and docs.",
            "software planning, documentation",
            "implementation plans, code + tests, and docs with citations",
            "",  # default roster
            "implementation, bug fixes, and tests",
            "architecture, specs, and verification",
            "documentation, synthesis, and write-ups",
            "route software planning to claude and docs to gemini",
            "always verify",
            "fully autonomous except ambiguity",
            "production deploys and destructive edits",
            "ask when goal or format is unclear",
            "never invent sources or delete files",
        ])
        outputs: list[str] = []

        run_startup_wizard(
            project_root=self.temp_dir,
            project_name="Wizard Claw",
            input_func=lambda prompt: next(answers),
            output_func=outputs.append,
        )

        self.assertTrue((self.temp_dir / "docs/STARTUP_PROFILE.md").exists())
        self.assertTrue((self.temp_dir / "docs/STARTUP_TRANSCRIPT.md").exists())
        self.assertTrue((self.temp_dir / ".promptclaw/onboarding/startup-session.md").exists())

        vision_text = (self.temp_dir / "prompts/00-project-vision.md").read_text(encoding="utf-8")
        self.assertIn("A claw for software planning and docs.", vision_text)

        config = load_config(self.temp_dir)
        self.assertTrue(config.routing.verification_enabled)
        self.assertEqual(config.project.description, "A claw for software planning and docs.")
        self.assertEqual(config.agents["codex"].capabilities, ["coding", "implementation", "testing"])
        self.assertTrue(any("Startup Wizard" in block for block in outputs))

    def test_follow_up_detection_for_vague_inputs(self):
        wizard = StartupWizard(
            project_root=self.temp_dir,
            project_name="Wizard Claw",
            input_func=lambda prompt: "",
            output_func=lambda text: None,
        )
        wizard.profile.agent_roster = ["codex", "claude", "gemini"]

        task_follow_ups = wizard._follow_up_questions("task_families", "anything")
        self.assertEqual(task_follow_ups[0].key, "task_families_priority")

        autonomy_follow_ups = wizard._follow_up_questions("autonomy", "fully autonomous")
        self.assertEqual(autonomy_follow_ups[0].key, "permission_boundaries")

        boundary_follow_ups = wizard._follow_up_questions("boundaries", "be good")
        self.assertEqual(boundary_follow_ups[0].key, "hard_boundaries")

        routing_follow_ups = wizard._follow_up_questions("routing_examples", "just pick whoever")
        self.assertEqual(routing_follow_ups[0].key, "routing_examples_detail")


class WizardEndToEndTests(unittest.TestCase):
    """End-to-end diagnostic coverage for the startup wizard lifecycle."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-wizard-e2e-"))
        init_project(self.temp_dir, "Lifecycle Claw")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_startup_wizard_lifecycle_round_trips_json_diagnostic(self) -> None:
        project_pitch = "A focused claw for software planning, docs, and verification."
        answers = iter([
            project_pitch,
            "code changes, architecture, documentation",
            "implementation plans, code + tests, and docs with citations",
            "",  # default roster -> codex, claude, gemini
            "implementation, bug fixes, and tests",
            "architecture, specs, and verification",
            "documentation, synthesis, and write-ups",
            "route software planning to claude and docs to gemini",
            "always verify",
            "fully autonomous except ambiguity",
            "production deploys and destructive edits",
            "ask when goal or format is unclear",
            "never invent sources or delete files",
        ])
        outputs: list[str] = []

        profile = run_startup_wizard(
            project_root=self.temp_dir,
            project_name="Lifecycle Claw",
            input_func=lambda prompt: next(answers),
            output_func=outputs.append,
        )

        expected_files = {
            "prompts/00-project-vision.md",
            "prompts/01-agent-roles.md",
            "prompts/02-routing-rules.md",
            "prompts/agents/codex.md",
            "prompts/agents/claude.md",
            "prompts/agents/gemini.md",
            "docs/STARTUP_PROFILE.md",
            "docs/STARTUP_TRANSCRIPT.md",
            ".promptclaw/onboarding/startup-session.md",
            "promptclaw.json",
        }
        for relative in expected_files:
            self.assertTrue(
                (self.temp_dir / relative).exists(),
                msg=f"missing expected file {relative}",
            )

        vision_text = (
            self.temp_dir / "prompts/00-project-vision.md"
        ).read_text(encoding="utf-8")
        self.assertIn(project_pitch, vision_text)
        self.assertIn("production deploys and destructive edits", vision_text)

        config = load_config(self.temp_dir)
        self.assertEqual(config.project.description, project_pitch)
        self.assertTrue(config.routing.verification_enabled)
        self.assertTrue(config.routing.ask_user_on_ambiguity)
        self.assertEqual(profile.agent_roster, ["codex", "claude", "gemini"])

        expected_capabilities = {
            "codex": ["coding", "implementation", "testing"],
            "claude": ["architecture", "specification", "verification"],
            "gemini": ["docs", "synthesis", "writing"],
        }
        for agent_name, expected_caps in expected_capabilities.items():
            self.assertIn(agent_name, config.agents)
            agent = config.agents[agent_name]
            self.assertTrue(agent.enabled)
            self.assertEqual(agent.capabilities, expected_caps)
            self.assertEqual(
                agent.instruction_file,
                f"prompts/agents/{agent_name}.md",
            )

        self.assertEqual(
            parse_agent_roster("codex, claude, gemini"),
            ["codex", "claude", "gemini"],
        )
        self.assertEqual(parse_agent_roster(""), ["codex", "claude", "gemini"])
        self.assertTrue(looks_vague("anything"))
        self.assertFalse(looks_vague("a focused mission with concrete outputs"))
        self.assertTrue(mentions_any("this is verification work", ["verify", "verification"]))
        self.assertFalse(mentions_any("nothing relevant here", ["xyz"]))
        self.assertEqual(
            infer_capabilities(DEFAULT_AGENT_STRENGTHS["codex"], "codex"),
            ["coding", "implementation", "refactoring", "testing"],
        )
        self.assertEqual(
            lead_lane_text("coding, implementation"),
            "code-heavy execution and implementation",
        )
        self.assertEqual(
            verification_fit_text("verification, analysis"),
            "strong verifier candidate",
        )
        self.assertEqual(sentence_or_list("only one item"), "only one item")
        self.assertEqual(sentence_or_list("a, b, c"), "- a\n- b\n- c")

        self.assertTrue(any("Startup Wizard" in block for block in outputs))
        self.assertTrue(any("Ready" in block for block in outputs))

        diagnostic = {
            "project_name": profile.project_name,
            "agent_roster": list(profile.agent_roster),
            "config_description": config.project.description,
            "routing": {
                "verification_enabled": config.routing.verification_enabled,
                "ask_user_on_ambiguity": config.routing.ask_user_on_ambiguity,
            },
            "agents": {
                name: {
                    "enabled": config.agents[name].enabled,
                    "capabilities": list(config.agents[name].capabilities),
                    "instruction_file": config.agents[name].instruction_file,
                }
                for name in expected_capabilities
            },
            "files_written": sorted(
                str(path.relative_to(self.temp_dir)).replace("\\", "/")
                for path in profile.files_written
            ),
            "helpers": {
                "parse_default_roster": parse_agent_roster(""),
                "looks_vague_anything": looks_vague("anything"),
                "looks_vague_focused": looks_vague(
                    "a focused mission with concrete outputs"
                ),
                "lead_lane_coding": lead_lane_text("coding, implementation"),
                "verification_fit_strong": verification_fit_text(
                    "verification, analysis"
                ),
                "sentence_or_list_single": sentence_or_list("only one item"),
                "sentence_or_list_many": sentence_or_list("a, b, c"),
            },
        }

        round_trip = json.loads(json.dumps(diagnostic, sort_keys=True))
        self.assertEqual(round_trip, diagnostic)
        self.assertEqual(round_trip["agent_roster"], ["codex", "claude", "gemini"])
        self.assertEqual(
            round_trip["agents"]["codex"]["capabilities"],
            ["coding", "implementation", "testing"],
        )
        self.assertIn("promptclaw.json", round_trip["files_written"])
        self.assertIn(
            ".promptclaw/onboarding/startup-session.md",
            round_trip["files_written"],
        )


if __name__ == "__main__":
    unittest.main()
