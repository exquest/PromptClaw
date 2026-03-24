import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.bootstrap import init_project
from promptclaw.orchestrator import PromptClawOrchestrator

class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-orchestrator-"))
        init_project(self.temp_dir, "Test Claw")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_run_completes_for_clear_task(self):
        orchestrator = PromptClawOrchestrator(self.temp_dir)
        state = orchestrator.run("Implement a small Python module and provide a concise plan.", title="Clear Task")
        self.assertEqual(state.status, "complete")
        self.assertTrue((self.temp_dir / state.final_summary_path).exists())

    def test_run_pauses_for_ambiguous_task(self):
        orchestrator = PromptClawOrchestrator(self.temp_dir)
        state = orchestrator.run("Make something good somehow.", title="Ambiguous Task")
        self.assertEqual(state.status, "awaiting_user")
        self.assertTrue(state.clarification_question)

    def test_resume_creates_new_completed_run(self):
        orchestrator = PromptClawOrchestrator(self.temp_dir)
        paused = orchestrator.run("Make something good somehow.", title="Needs Answer")
        resumed = orchestrator.resume(paused.run_id, "Produce a markdown implementation plan.")
        self.assertEqual(resumed.status, "complete")
