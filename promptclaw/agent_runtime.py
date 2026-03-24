from __future__ import annotations

from pathlib import Path

from .command_runner import run_command
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
        result = run_command(
            command=agent.command or None,
            shell_command=agent.shell_command or None,
            values={
                "prompt_file": str(prompt_path),
                "project_root": str(project_root),
                "agent_name": agent.name,
            },
            env=agent.env,
            cwd=str(project_root),
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
