from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any

from .utils import render_string_template

@dataclass
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int

def run_command(
    command: list[str] | None = None,
    shell_command: str | None = None,
    values: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> CommandResult:
    values = values or {}
    merged_env = os.environ.copy()
    merged_env.update(env or {})
    if shell_command:
        rendered = render_string_template(shell_command, values)
        completed = subprocess.run(
            rendered,
            shell=True,
            text=True,
            capture_output=True,
            cwd=cwd,
            env=merged_env,
        )
        return CommandResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
        )
    if command:
        rendered_args = [render_string_template(str(arg), values) for arg in command]
        completed = subprocess.run(
            rendered_args,
            text=True,
            capture_output=True,
            cwd=cwd,
            env=merged_env,
        )
        return CommandResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
        )
    return CommandResult(stdout="", stderr="No command configured", exit_code=2)
