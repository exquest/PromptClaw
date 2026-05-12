"""Tests for the sample-capture systemd verifier."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from types import SimpleNamespace

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from sample_capture_service_verify import (  # noqa: E402
    VerificationError,
    build_runner,
    main,
    verify_service,
)


SERVICE = "cypherclaw-sample-capture.service"
DEPENDENCY = "cypherclaw-jack.service"


def _service_show(
    *,
    active_state: str,
    sub_state: str,
    main_pid: int,
    exec_main_pid: int | None = None,
    after: str = DEPENDENCY,
    requires: str = DEPENDENCY,
) -> str:
    if exec_main_pid is None:
        exec_main_pid = main_pid
    return "\n".join(
        (
            f"ActiveState={active_state}",
            f"SubState={sub_state}",
            f"MainPID={main_pid}",
            f"ExecMainPID={exec_main_pid}",
            f"After={after}",
            f"Requires={requires}",
        )
    )


def _dependency_show(*, active_state: str = "active", sub_state: str = "running") -> str:
    return "\n".join((f"ActiveState={active_state}", f"SubState={sub_state}"))


@dataclass
class _FakeRunner:
    outputs: list[tuple[tuple[str, ...], str]]
    calls: list[tuple[str, ...]]

    def __init__(self, outputs: list[tuple[tuple[str, ...], str]]) -> None:
        self.outputs = list(outputs)
        self.calls = []

    def run(self, command: list[str]) -> str:
        key = tuple(command)
        self.calls.append(key)
        if not self.outputs:
            raise AssertionError(f"unexpected command with no outputs left: {command!r}")
        expected, output = self.outputs.pop(0)
        assert expected == key
        return output


def test_verify_service_returns_restart_summary_after_pid_changes() -> None:
    runner = _FakeRunner(
        [
            (
                (
                    "systemctl",
                    "show",
                    "-p",
                    "ActiveState",
                    "-p",
                    "SubState",
                    "-p",
                    "MainPID",
                    "-p",
                    "ExecMainPID",
                    "-p",
                    "After",
                    "-p",
                    "Requires",
                    SERVICE,
                ),
                _service_show(active_state="active", sub_state="running", main_pid=101),
            ),
            (
                (
                    "systemctl",
                    "show",
                    "-p",
                    "ActiveState",
                    "-p",
                    "SubState",
                    DEPENDENCY,
                ),
                _dependency_show(),
            ),
            (("kill", "-9", "101"), ""),
            (
                (
                    "systemctl",
                    "show",
                    "-p",
                    "ActiveState",
                    "-p",
                    "SubState",
                    "-p",
                    "MainPID",
                    "-p",
                    "ExecMainPID",
                    "-p",
                    "After",
                    "-p",
                    "Requires",
                    SERVICE,
                ),
                _service_show(active_state="activating", sub_state="auto-restart", main_pid=0),
            ),
            (
                (
                    "systemctl",
                    "show",
                    "-p",
                    "ActiveState",
                    "-p",
                    "SubState",
                    "-p",
                    "MainPID",
                    "-p",
                    "ExecMainPID",
                    "-p",
                    "After",
                    "-p",
                    "Requires",
                    SERVICE,
                ),
                _service_show(active_state="active", sub_state="running", main_pid=202),
            ),
        ]
    )

    ticks = iter((0.0, 0.0, 1.0, 2.0))
    result = verify_service(
        runner,
        service=SERVICE,
        dependency=DEPENDENCY,
        timeout_sec=10.0,
        poll_interval_sec=0.0,
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: next(ticks),
    )

    assert result.service == SERVICE
    assert result.dependency == DEPENDENCY
    assert result.original_pid == 101
    assert result.restarted_pid == 202
    assert result.dependency_state.active_state == "active"
    assert result.dependency_state.sub_state == "running"


def test_verify_service_rejects_missing_dependency() -> None:
    runner = _FakeRunner(
        [
            (
                (
                    "systemctl",
                    "show",
                    "-p",
                    "ActiveState",
                    "-p",
                    "SubState",
                    "-p",
                    "MainPID",
                    "-p",
                    "ExecMainPID",
                    "-p",
                    "After",
                    "-p",
                    "Requires",
                    SERVICE,
                ),
                _service_show(
                    active_state="active",
                    sub_state="running",
                    main_pid=101,
                    after="basic.target",
                    requires="sysinit.target",
                ),
            )
        ]
    )

    with pytest.raises(VerificationError, match="missing from After/Requires"):
        verify_service(
            runner,
            service=SERVICE,
            dependency=DEPENDENCY,
            timeout_sec=1.0,
            poll_interval_sec=0.0,
            sleep_fn=lambda _seconds: None,
            monotonic_fn=lambda: 0.0,
        )


def test_main_reports_success_after_pid_changes(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    runner = _FakeRunner(
        [
            (
                (
                    "systemctl",
                    "show",
                    "-p",
                    "ActiveState",
                    "-p",
                    "SubState",
                    "-p",
                    "MainPID",
                    "-p",
                    "ExecMainPID",
                    "-p",
                    "After",
                    "-p",
                    "Requires",
                    SERVICE,
                ),
                _service_show(active_state="active", sub_state="running", main_pid=333),
            ),
            (
                (
                    "systemctl",
                    "show",
                    "-p",
                    "ActiveState",
                    "-p",
                    "SubState",
                    DEPENDENCY,
                ),
                _dependency_show(),
            ),
            (("kill", "-9", "333"), ""),
            (
                (
                    "systemctl",
                    "show",
                    "-p",
                    "ActiveState",
                    "-p",
                    "SubState",
                    "-p",
                    "MainPID",
                    "-p",
                    "ExecMainPID",
                    "-p",
                    "After",
                    "-p",
                    "Requires",
                    SERVICE,
                ),
                _service_show(active_state="active", sub_state="running", main_pid=444),
            ),
        ]
    )
    ticks = iter((0.0, 0.0, 1.0))

    monkeypatch.setattr(
        "sample_capture_service_verify.build_runner",
        lambda host: runner,
    )

    rc = main(
        [
            "--host",
            "cypherclaw",
            "--timeout-sec",
            "10",
            "--poll-interval-sec",
            "0",
        ],
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: next(ticks),
    )

    assert rc == 0
    captured = capsys.readouterr().out
    assert "SERVICE_ACTIVE" in captured
    assert "JACK_DEPENDENCY_OK" in captured
    assert "RESTART_OK" in captured
    assert "original_pid=333" in captured
    assert "restarted_pid=444" in captured


def test_build_runner_wraps_remote_commands_with_ssh(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        recorded.append(command)
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("sample_capture_service_verify.subprocess.run", fake_run)

    runner = build_runner("cypherclaw")
    output = runner.run(["true"])

    assert output == "ok"
    assert recorded == [["ssh", "-o", "BatchMode=yes", "cypherclaw", "true"]]
