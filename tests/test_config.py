import argparse
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from promptclaw.bootstrap import init_project
from promptclaw.cli import cmd_show_config
from promptclaw.config import (
    CONFIG_FILENAME,
    config_path,
    config_status_report,
    default_project_config,
    enabled_agents,
    load_config,
    load_or_default,
    save_config,
    summarize_config,
    validate_config,
)
from promptclaw.models import AgentConfig

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


class ConfigEndToEndTests(unittest.TestCase):
    def test_init_project_loads_valid_config_and_json_safe_summary(self) -> None:
        project_root = Path(tempfile.mkdtemp(prefix="promptclaw-config-e2e-"))
        self.addCleanup(shutil.rmtree, project_root)
        created = init_project(project_root, "End To End Claw")
        created_paths = {
            path.relative_to(project_root).as_posix(): path for path in created
        }

        for required_path in (
            CONFIG_FILENAME,
            "prompts/00-project-vision.md",
            "prompts/agents/codex.md",
            "docs/PROJECT_GUIDE.md",
        ):
            self.assertIn(required_path, created_paths)
            self.assertTrue(created_paths[required_path].exists())

        config = load_config(project_root)
        report = config_status_report(config)
        summary = summarize_config(config)
        rendered_summary = json.dumps(summary, sort_keys=True)

        self.assertIn("End To End Claw", rendered_summary)
        self.assertEqual(validate_config(config), [])
        self.assertEqual(report.project_name, "End To End Claw")
        self.assertEqual(report.enabled_agent_names, ("claude", "codex", "gemini"))
        self.assertTrue(report.is_valid)
        for agent_name in report.enabled_agent_names:
            self.assertIn(agent_name, config.agents)
            self.assertTrue(config.agents[agent_name].enabled)

    def test_save_load_validate_and_report_mixed_agents(self) -> None:
        project_root = Path(tempfile.mkdtemp(prefix="promptclaw-config-roundtrip-"))
        self.addCleanup(shutil.rmtree, project_root)
        config = default_project_config("Round Trip Claw")
        config.control_plane.mode = "agent"
        config.control_plane.agent = "codex"
        config.routing.max_retries = 2
        config.agents["omega"] = AgentConfig(
            name="omega",
            enabled=False,
            kind="mock",
            capabilities=["docs"],
        )
        config.agents["runner"] = AgentConfig(
            name="runner",
            enabled=True,
            kind="command",
            command=["python", "-m", "promptclaw.cli"],
            env={"PROMPTCLAW_TEST_MODE": "1"},
            capabilities=["ops"],
            instruction_file="prompts/agents/runner.md",
        )

        save_config(project_root, config)
        loaded = load_config(project_root)
        report = config_status_report(loaded)

        self.assertTrue(config_path(project_root).exists())
        self.assertEqual(validate_config(loaded), [])
        self.assertEqual(loaded.control_plane.agent, "codex")
        self.assertEqual(loaded.routing.max_retries, 2)
        self.assertEqual(enabled_agents(loaded), ("claude", "codex", "gemini", "runner"))
        self.assertEqual(report.disabled_agent_names, ("omega",))
        for name, expected_kind in (("runner", "command"), ("omega", "mock")):
            self.assertIn(name, loaded.agents)
            self.assertEqual(loaded.agents[name].kind, expected_kind)

    def test_validate_config_reports_actionable_issue_set(self) -> None:
        config = default_project_config("Broken Claw")
        config.project.name = "   "
        config.control_plane.mode = "agent"
        config.control_plane.agent = "missing-agent"
        config.routing.max_retries = -1
        for agent in config.agents.values():
            agent.enabled = False
        config.agents["bad-command"] = AgentConfig(
            name="bad-command",
            enabled=False,
            kind="command",
        )

        issues = validate_config(config)
        report = config_status_report(config)
        summary = summarize_config(config)

        expected_issues = (
            "project.name must not be empty",
            "routing.max_retries must be >= 0",
            "at least one agent must be enabled",
            "control_plane.agent must refer to a defined agent",
            "agent 'bad-command' is command mode but has no command",
        )
        for expected in expected_issues:
            self.assertIn(expected, issues)

        self.assertFalse(report.is_valid)
        self.assertEqual(report.issues, tuple(issues))
        self.assertEqual(summary["issues"], issues)
        self.assertEqual(summary["disabled_agent_names"], ["bad-command", "claude", "codex", "gemini"])

    def test_load_or_default_falls_back_then_loads_saved_config(self) -> None:
        project_root = Path(tempfile.mkdtemp(prefix="promptclaw-config-default-"))
        self.addCleanup(shutil.rmtree, project_root)
        config_file = config_path(project_root)

        defaulted = load_or_default(project_root, project_name="Fresh Claw")
        self.assertFalse(config_file.exists())
        self.assertEqual(defaulted.project.name, "Fresh Claw")

        defaulted.project.description = "Saved after first config load."
        save_config(project_root, defaulted)
        loaded = load_or_default(project_root, project_name="Ignored Claw")

        self.assertTrue(config_file.exists())
        self.assertEqual(loaded.project.name, "Fresh Claw")
        self.assertEqual(loaded.project.description, "Saved after first config load.")
        for agent_name in ("claude", "codex", "gemini"):
            self.assertIn(agent_name, loaded.agents)

    def test_show_config_payload_matches_saved_configuration(self) -> None:
        project_root = Path(tempfile.mkdtemp(prefix="promptclaw-config-cli-"))
        self.addCleanup(shutil.rmtree, project_root)
        config = default_project_config("CLI Claw")
        config.agents["writer"] = AgentConfig(
            name="writer",
            enabled=True,
            kind="command",
            command=["python", "-m", "writer"],
            env={"PROMPTCLAW_TEST_MODE": "1"},
            capabilities=["writing", "docs"],
            instruction_file="prompts/agents/writer.md",
        )
        save_config(project_root, config)

        output = io.StringIO()
        with redirect_stdout(output):
            rc = cmd_show_config(argparse.Namespace(project_root=project_root))
        payload = json.loads(output.getvalue())

        self.assertEqual(rc, 0)
        for section in ("project", "artifacts", "control_plane", "routing", "agents"):
            self.assertIn(section, payload)
        self.assertEqual(payload["project"]["name"], "CLI Claw")
        self.assertEqual(payload["agents"]["writer"]["kind"], "command")
        self.assertEqual(payload["agents"]["writer"]["command"], ["python", "-m", "writer"])
        self.assertEqual(payload["agents"]["writer"]["capabilities"], ["writing", "docs"])
