import os
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from promptclaw.agent_runtime import AgentRuntime
from promptclaw.models import AgentConfig
from promptclaw.utils import write_text


class AgentRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir_abs = Path(tempfile.mkdtemp(prefix="promptclaw-runtime-", dir=".")).resolve()
        self.project_root = Path(os.path.relpath(self.temp_dir_abs, Path.cwd()))
        self.prompt_path = self.project_root / ".promptclaw/runs/run-1/prompts/lead-test.md"
        write_text(self.prompt_path, "# Prompt\n\nRead me from disk.\n")

    def tearDown(self):
        shutil.rmtree(self.temp_dir_abs)

    def test_command_agent_receives_readable_prompt_file_path(self):
        agent = AgentConfig(
            name="tester",
            kind="command",
            command=[
                sys.executable,
                "-c",
                "from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text())",
                "{prompt_file}",
            ],
        )
        result = AgentRuntime().run(
            agent=agent,
            prompt_text="",
            prompt_path=self.prompt_path,
            phase="lead",
            role="lead",
            project_root=self.project_root,
        )
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Read me from disk.", result.output_text)

    def test_shell_command_agent_receives_readable_prompt_file_path(self):
        agent = AgentConfig(
            name="tester",
            kind="command",
            shell_command=(
                f"{shlex.quote(sys.executable)} "
                "-c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text())' "
                "{prompt_file}"
            ),
        )
        result = AgentRuntime().run(
            agent=agent,
            prompt_text="",
            prompt_path=self.prompt_path,
            phase="lead",
            role="lead",
            project_root=self.project_root,
        )
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Read me from disk.", result.output_text)
