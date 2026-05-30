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

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from .atomic import atomic_write_bytes

__all__ = [
    "BoxRunResult",
    "BoxRunner",
    "FakeBoxRunner",
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
        self.calls.append((argv_tuple, output_dir))
        return BoxRunResult(
            exit_status=self.exit_status,
            artifacts=tuple(written),
            stdout=self.stdout,
            stderr=self.stderr,
        )
