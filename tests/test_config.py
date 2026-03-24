import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.bootstrap import init_project
from promptclaw.config import load_config, validate_config

class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-config-"))
        init_project(self.temp_dir, "Config Claw")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_load_config(self):
        config = load_config(self.temp_dir)
        self.assertEqual(config.project.name, "Config Claw")
        self.assertIn("codex", config.agents)

    def test_validate_default_config(self):
        config = load_config(self.temp_dir)
        issues = validate_config(config)
        self.assertEqual(issues, [])
