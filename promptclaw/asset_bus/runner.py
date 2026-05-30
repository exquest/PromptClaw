"""Box-runner abstraction for invoking renderers off-process.

The producer renders an asset by running a CLI (``asset_render_image``,
``asset_render_music``) on the CypherClaw box. The transport — ssh,
local subprocess, federation RPC — is encapsulated behind the
:class:`BoxRunner` protocol so the routing/manifest code does not depend
on it.

Unit tests use :class:`FakeBoxRunner`, which materializes configured
artifact bytes into the caller's ``output_dir`` and returns the
configured exit status without touching a network or a shell. The real
``SSHBoxRunner`` is task T-009.
"""

from __future__ import annotations

import json
import wave
from io import BytesIO
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable
from uuid import uuid4

from .atomic import atomic_write_bytes

__all__ = [
    "BoxRunResult",
    "BoxRunner",
    "FakeBoxRunner",
    "SSHBoxRunner",
]


@dataclass(frozen=True)
class BoxRunResult:
    """Outcome of one :meth:`BoxRunner.run` call."""

    exit_status: int
    artifacts: tuple[Path, ...] = ()
    stdout: str = ""
    stderr: str = ""


@runtime_checkable
class BoxRunner(Protocol):
    """Run an argv on a box and return its produced files.

    Implementations must NOT interpret ``argv`` as a shell string: every
    element reaches the child process as one ``argv[i]`` so shell
    metacharacters in a request-derived value are passed through
    literally. Every produced file must land under ``output_dir`` and
    appear in :attr:`BoxRunResult.artifacts` so the caller can fingerprint
    each artifact without re-scanning the directory.
    """

    def run(
        self,
        argv: Sequence[str],
        *,
        output_dir: Path,
    ) -> BoxRunResult: ...


@dataclass
class FakeBoxRunner:
    """In-process :class:`BoxRunner` for unit tests.

    Configured with ``exit_status`` and a sequence of ``(name, bytes)``
    pairs naming files to materialize in ``output_dir`` on every call.
    Each invocation is recorded in :attr:`calls` as ``(argv, output_dir)``
    so tests can assert on the exact argv handed across the boundary —
    including injection fixtures that must survive as one element.
    """

    exit_status: int = 0
    artifacts: Sequence[tuple[str, bytes]] = ()
    stdout: str = ""
    stderr: str = ""
    calls: list[tuple[tuple[str, ...], Path]] = field(default_factory=list)

    def run(
        self,
        argv: Sequence[str],
        *,
        output_dir: Path,
    ) -> BoxRunResult:
        argv_tuple = tuple(argv)
        output_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for name, data in self.artifacts:
            target = output_dir / name
            atomic_write_bytes(target, data)
            written.append(target)
        if not self.artifacts and self.exit_status == 0:
            music_output = _fake_asset_render_music_output(argv_tuple, output_dir)
            if music_output is not None:
                written.append(music_output)
        self.calls.append((argv_tuple, output_dir))
        return BoxRunResult(
            exit_status=self.exit_status,
            artifacts=tuple(written),
            stdout=self.stdout,
            stderr=self.stderr,
        )


def _argv_option(argv: Sequence[str], option: str) -> str | None:
    try:
        index = argv.index(option)
    except ValueError:
        return None
    value_index = index + 1
    if value_index >= len(argv):
        return None
    return argv[value_index]


def _fake_wav_bytes() -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 16)
    return buffer.getvalue()


def _resolve_fake_output_path(output_dir: Path, output_value: str) -> Path:
    candidate = Path(output_value)
    if not candidate.is_absolute():
        candidate = output_dir / candidate
    resolved_output_dir = output_dir.resolve()
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_output_dir)
    except ValueError as exc:
        raise ValueError(
            "fake asset_render_music output must stay under output_dir"
        ) from exc
    return resolved_candidate


def _fake_asset_render_music_output(
    argv: Sequence[str],
    output_dir: Path,
) -> Path | None:
    if not argv or Path(argv[0]).name != "asset_render_music":
        return None
    output_value = _argv_option(argv, "--output")
    if output_value is None:
        output_value = _argv_option(argv, "--output-path")
    if output_value is None:
        return None

    target = _resolve_fake_output_path(output_dir, output_value)
    atomic_write_bytes(target, _fake_wav_bytes())
    return target


def _default_run_id() -> str:
    return uuid4().hex


def _coerce_argv(argv: Sequence[str]) -> tuple[str, ...]:
    if not argv:
        raise ValueError("argv must not be empty")
    coerced: list[str] = []
    for index, value in enumerate(argv):
        if not isinstance(value, str):
            raise ValueError(f"argv[{index}] must be str, got {type(value).__name__}")
        if "\x00" in value:
            raise ValueError(f"argv[{index}] contains NUL byte")
        coerced.append(value)
    return tuple(coerced)


def _list_artifacts(output_dir: Path) -> tuple[Path, ...]:
    return tuple(sorted((path for path in output_dir.rglob("*") if path.is_file())))


@dataclass
class SSHBoxRunner:
    """SSH-backed :class:`BoxRunner` that keeps request argv out of shell strings.

    The local SSH command invokes a fixed remote helper. Request-derived argv is
    JSON on stdin, and the helper executes the renderer with ``shell=False``.
    ``rsync`` then pulls every file from the remote run directory into the local
    ``output_dir``.
    """

    host: str
    remote_output_root: str
    ssh_executable: str = "ssh"
    rsync_executable: str = "rsync"
    ssh_options: Sequence[str] = ("-o", "BatchMode=yes")
    remote_python: str = "python3"
    remote_module: str = "promptclaw.asset_bus.remote_exec"
    command_timeout_s: float | None = None
    transfer_timeout_s: float | None = None
    run_id_factory: Callable[[], str] = _default_run_id
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run

    def run(
        self,
        argv: Sequence[str],
        *,
        output_dir: Path,
    ) -> BoxRunResult:
        argv_tuple = _coerce_argv(argv)
        output_dir.mkdir(parents=True, exist_ok=True)
        remote_run_dir = self._remote_run_dir()
        payload = json.dumps(
            {"argv": list(argv_tuple)},
            ensure_ascii=True,
            separators=(",", ":"),
        )

        ssh_cmd = [
            self.ssh_executable,
            *self.ssh_options,
            self.host,
            self.remote_python,
            "-m",
            self.remote_module,
            "--output-dir",
            remote_run_dir,
        ]
        remote = self.subprocess_run(
            ssh_cmd,
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=self.command_timeout_s,
        )

        transfer = self._transfer_back(remote_run_dir, output_dir)
        exit_status = remote.returncode
        if remote.returncode == 0 and transfer.returncode != 0:
            exit_status = transfer.returncode

        stderr_parts = [part for part in (remote.stderr, transfer.stderr) if part]
        return BoxRunResult(
            exit_status=exit_status,
            artifacts=_list_artifacts(output_dir),
            stdout=remote.stdout or "",
            stderr="\n".join(stderr_parts),
        )

    def _remote_run_dir(self) -> str:
        root = self.remote_output_root.rstrip("/")
        if not root:
            raise ValueError("remote_output_root must not be empty")
        if "\x00" in root:
            raise ValueError("remote_output_root contains NUL byte")

        run_id = self.run_id_factory()
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id_factory must return a non-empty str")
        if "/" in run_id or "\x00" in run_id:
            raise ValueError("run id must not contain slash or NUL byte")
        return f"{root}/{run_id}"

    def _transfer_back(
        self,
        remote_run_dir: str,
        output_dir: Path,
    ) -> subprocess.CompletedProcess[str]:
        transfer_cmd = [
            self.rsync_executable,
            "-a",
            "--",
            f"{self.host}:{remote_run_dir}/",
            f"{output_dir}/",
        ]
        return self.subprocess_run(
            transfer_cmd,
            input=None,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=self.transfer_timeout_s,
        )
