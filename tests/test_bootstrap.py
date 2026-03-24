import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.bootstrap import bootstrap_task_from_prompts, init_project

class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-test-"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_init_project_creates_expected_files(self):
        created = init_project(self.temp_dir, "Test Claw")
        self.assertTrue((self.temp_dir / "promptclaw.json").exists())
        self.assertTrue((self.temp_dir / "prompts/00-project-vision.md").exists())
        self.assertTrue((self.temp_dir / "prompts/agents/codex.md").exists())
        self.assertGreaterEqual(len(created), 10)

    def test_bootstrap_task_includes_three_bootstrap_prompts(self):
        init_project(self.temp_dir, "Test Claw")
        task_text = bootstrap_task_from_prompts(self.temp_dir)
        self.assertIn("## Project vision", task_text)
        self.assertIn("## Agent roles", task_text)
        self.assertIn("## Routing rules", task_text)
