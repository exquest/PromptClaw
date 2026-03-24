import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.bootstrap import init_project
from promptclaw.config import load_config
from promptclaw.wizard import StartupWizard, parse_agent_roster, run_startup_wizard


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


if __name__ == "__main__":
    unittest.main()
