import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from promptclaw import cli
from promptclaw.bootstrap import bootstrap_task_from_prompts, init_project

class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-test-"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_init_project_creates_expected_files(self):
        created = init_project(self.temp_dir, "Test Claw")
        self.assertTrue((self.temp_dir / "promptclaw.json").exists())
        self.assertTrue((self.temp_dir / "constitution.yaml").exists())
        self.assertTrue((self.temp_dir / "prompts/00-project-vision.md").exists())
        self.assertTrue((self.temp_dir / "prompts/agents/codex.md").exists())
        self.assertGreaterEqual(len(created), 10)

    def test_init_project_coherence_doctor_loads_constitution(self):
        init_project(self.temp_dir, "Test Claw")
        output = StringIO()

        with patch("promptclaw.cli._bootstrap_runtime_identity"), redirect_stdout(output):
            result = cli.main(["coherence", "doctor", str(self.temp_dir)])

        self.assertEqual(result, 0, output.getvalue())
        self.assertIn("PASS: Constitution file (1 rules loaded from constitution.yaml)", output.getvalue())

    def test_bootstrap_task_includes_three_bootstrap_prompts(self):
        init_project(self.temp_dir, "Test Claw")
        task_text = bootstrap_task_from_prompts(self.temp_dir)
        self.assertIn("## Project vision", task_text)
        self.assertIn("## Agent roles", task_text)
        self.assertIn("## Routing rules", task_text)
