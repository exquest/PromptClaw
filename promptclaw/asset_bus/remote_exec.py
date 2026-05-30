"""Remote argv execution helper for :class:`SSHBoxRunner`.

This module is intended to run on the CypherClaw box through a fixed SSH
entrypoint. The request-derived renderer argv arrives as JSON stdin, then the
renderer is launched as an argv list with ``shell=False``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Callable

__all__ = [
    "RemoteExecError",
    "main",
    "run_remote_payload",
]


class RemoteExecError(ValueError):
    """Raised when the SSHBoxRunner payload cannot be executed safely."""


def _payload_argv(payload_json: str) -> tuple[str, ...]:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise RemoteExecError(f"invalid JSON payload: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise RemoteExecError("payload must be a JSON object")

    raw_argv = payload.get("argv")
    if not isinstance(raw_argv, list) or not raw_argv:
        raise RemoteExecError("payload argv must be a non-empty list")

    argv: list[str] = []
    for index, value in enumerate(raw_argv):
        if not isinstance(value, str):
            raise RemoteExecError(
                f"payload argv[{index}] must be str, got {type(value).__name__}"
            )
        if "\x00" in value:
            raise RemoteExecError(f"payload argv[{index}] contains NUL byte")
        argv.append(value)
    return tuple(argv)


def run_remote_payload(
    payload_json: str,
    *,
    output_dir: Path,
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    """Execute the renderer argv from ``payload_json`` without a shell."""

    argv = _payload_argv(payload_json)
    output_dir.mkdir(parents=True, exist_ok=True)
    child_argv = [*argv, "--output-dir", str(output_dir)]
    env = os.environ.copy()
    env["DENIABLE_ASSET_OUTPUT_DIR"] = str(output_dir)
    return subprocess_run(
        child_argv,
        cwd=output_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute asset renderer argv from JSON stdin.")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        completed = run_remote_payload(sys.stdin.read(), output_dir=args.output_dir)
    except RemoteExecError as exc:
        print(f"asset-bus remote exec error: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(completed.stdout or "")
    sys.stderr.write(completed.stderr or "")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
