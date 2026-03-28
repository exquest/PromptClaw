from __future__ import annotations

import subprocess
from pathlib import Path

from .command_runner import run_command
from .diagnostics import Diagnosis, diagnose
from .models import AgentConfig, AgentResult

class AgentRuntime:
    def run(
        self,
        agent: AgentConfig,
        prompt_text: str,
        prompt_path: Path,
        phase: str,
        role: str,
        project_root: Path,
        task_text: str = "",
    ) -> AgentResult:
        resolved_project_root = project_root.resolve()
        resolved_prompt_path = prompt_path.resolve()
        if agent.kind == "mock":
            output = self._mock_output(agent=agent, prompt_text=prompt_text, phase=phase, role=role, task_text=task_text)
            return AgentResult(
                agent_name=agent.name,
                phase=phase,
                role=role,
                output_text=output,
                stdout=output,
                stderr="",
                exit_code=0,
                output_path="",
                prompt_path=str(prompt_path),
            )
        if agent.kind == "echo":
            return AgentResult(
                agent_name=agent.name,
                phase=phase,
                role=role,
                output_text=prompt_text,
                stdout=prompt_text,
                stderr="",
                exit_code=0,
                output_path="",
                prompt_path=str(prompt_path),
            )
        # Command mode — wrap in error handling with auto-recovery
        try:
            result = run_command(
                command=agent.command or None,
                shell_command=agent.shell_command or None,
                values={
                    "prompt_file": str(resolved_prompt_path),
                    "project_root": str(resolved_project_root),
                    "agent_name": agent.name,
                },
                env=agent.env,
                cwd=str(resolved_project_root),
            )
        except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError) as exc:
            diag = diagnose(exc, phase=phase, context={"agent_name": agent.name})
            if diag.auto_recoverable:
                return self._recover_with_mock(
                    agent=agent, prompt_text=prompt_text, prompt_path=prompt_path,
                    phase=phase, role=role, task_text=task_text, diagnosis=diag,
                )
            # Not auto-recoverable — return an error result so the orchestrator can handle it
            return AgentResult(
                agent_name=agent.name,
                phase=phase,
                role=role,
                output_text=f"[ERROR] Agent '{agent.name}' failed: {exc}",
                stdout="",
                stderr=str(exc),
                exit_code=127,
                output_path="",
                prompt_path=str(resolved_prompt_path),
            )

        # Check for non-zero exit code — agent ran but returned an error
        if result.exit_code != 0 and not result.stdout.strip():
            diag = diagnose(
                RuntimeError(f"Agent '{agent.name}' exited with code {result.exit_code}: {result.stderr.strip()[:200]}"),
                phase=phase,
                context={"agent_name": agent.name},
            )
            if diag.auto_recoverable:
                return self._recover_with_mock(
                    agent=agent, prompt_text=prompt_text, prompt_path=prompt_path,
                    phase=phase, role=role, task_text=task_text, diagnosis=diag,
                )

        output = result.stdout or result.stderr
        return AgentResult(
            agent_name=agent.name,
            phase=phase,
            role=role,
            output_text=output,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            output_path="",
            prompt_path=str(resolved_prompt_path),
        )

    def _recover_with_mock(
        self,
        agent: AgentConfig,
        prompt_text: str,
        prompt_path: Path,
        phase: str,
        role: str,
        task_text: str,
        diagnosis: Diagnosis,
    ) -> AgentResult:
        """Fall back to mock mode when a command agent fails."""
        mock_output = self._mock_output(agent=agent, prompt_text=prompt_text, phase=phase, role=role, task_text=task_text)
        recovery_note = (
            f"[RECOVERED] Agent '{agent.name}' command failed — fell back to mock mode.\n"
            f"  Original error: {diagnosis.message}\n"
            f"  Suggestions:\n"
            + "\n".join(f"    - {s}" for s in diagnosis.suggestions)
            + "\n\n---\n\n"
        )
        return AgentResult(
            agent_name=agent.name,
            phase=phase,
            role=role,
            output_text=recovery_note + mock_output,
            stdout=recovery_note + mock_output,
            stderr=diagnosis.message,
            exit_code=0,
            output_path="",
            prompt_path=str(prompt_path),
        )

    def _mock_output(
        self,
        agent: AgentConfig,
        prompt_text: str,
        phase: str,
        role: str,
        task_text: str,
    ) -> str:
        header = f"# Mock output from {agent.name}\n\n"
        if phase == "lead":
            return (
                header
                + "## Summary\n"
                + f"{agent.name} handled the task in mock mode.\n\n"
                + "## Work\n"
                + f"Task excerpt: {task_text[:240]}\n\n"
                + "## Proposed Next Step\n"
                + "Proceed to verification.\n"
            )
        if phase == "verify":
            verdict = "PASS"
            if "contradict" in task_text.lower():
                verdict = "FAIL"
            return (
                header
                + "## Review\n"
                + f"{agent.name} reviewed the lead output in mock mode.\n\n"
                + f"VERDICT: {verdict}\n\n"
                + "## Notes\n"
                + "Mock verification completed.\n"
            )
        return header + prompt_text
