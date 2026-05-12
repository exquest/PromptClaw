"""Verify the sample-capture systemd runtime contract."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable


DEFAULT_SERVICE = "cypherclaw-sample-capture.service"
DEFAULT_DEPENDENCY = "cypherclaw-jack.service"


class VerificationError(RuntimeError):
    """Raised when the runtime contract check fails."""


@dataclass(frozen=True)
class UnitState:
    """Minimal `systemctl show` snapshot for a unit."""

    active_state: str
    sub_state: str
    main_pid: int = 0
    exec_main_pid: int = 0
    after: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerificationResult:
    """Successful runtime verification details."""

    service: str
    dependency: str
    service_state: UnitState
    dependency_state: UnitState
    recovered_state: UnitState
    original_pid: int
    restarted_pid: int


@dataclass
class CommandRunner:
    """Run commands either locally or through a fixed SSH target."""

    host: str | None = None

    def run(self, command: list[str]) -> str:
        full_command = list(command)
        if self.host:
            full_command = ["ssh", "-o", "BatchMode=yes", self.host, *command]
        try:
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise VerificationError(f"command not found: {full_command[0]}") from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise VerificationError(f"command failed: {' '.join(full_command)}: {detail}")
        return result.stdout.strip()


def build_runner(host: str | None) -> CommandRunner:
    """Build the local or remote command runner."""
    return CommandRunner(host=host)


def parse_systemctl_show(output: str) -> dict[str, str]:
    """Parse `systemctl show` key/value output into a dict."""
    parsed: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key] = value.strip()
    return parsed


def _parse_pid(raw: str | None) -> int:
    if raw is None:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def _split_units(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    return tuple(part for part in raw.split() if part)


def read_service_state(runner: CommandRunner, service: str) -> UnitState:
    """Read the full service state needed for dependency and restart checks."""
    output = runner.run(
        [
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
            service,
        ]
    )
    payload = parse_systemctl_show(output)
    return UnitState(
        active_state=payload.get("ActiveState", ""),
        sub_state=payload.get("SubState", ""),
        main_pid=_parse_pid(payload.get("MainPID")),
        exec_main_pid=_parse_pid(payload.get("ExecMainPID")),
        after=_split_units(payload.get("After")),
        requires=_split_units(payload.get("Requires")),
    )


def read_dependency_state(runner: CommandRunner, dependency: str) -> UnitState:
    """Read only the dependency activity state."""
    output = runner.run(
        [
            "systemctl",
            "show",
            "-p",
            "ActiveState",
            "-p",
            "SubState",
            dependency,
        ]
    )
    payload = parse_systemctl_show(output)
    return UnitState(
        active_state=payload.get("ActiveState", ""),
        sub_state=payload.get("SubState", ""),
    )


def _assert_active_running(state: UnitState, unit: str) -> None:
    if state.active_state != "active" or state.sub_state != "running":
        raise VerificationError(
            f"{unit} is not active/running: {state.active_state}/{state.sub_state}"
        )


def _assert_dependency_present(service_state: UnitState, dependency: str) -> None:
    if dependency in service_state.after or dependency in service_state.requires:
        return
    raise VerificationError(f"{dependency} missing from After/Requires for {DEFAULT_SERVICE}")


def _wait_for_restart(
    runner: CommandRunner,
    *,
    service: str,
    original_pid: int,
    timeout_sec: float,
    poll_interval_sec: float,
    sleep_fn: Callable[[float], None],
    monotonic_fn: Callable[[], float],
) -> UnitState:
    deadline = monotonic_fn() + timeout_sec
    while True:
        state = read_service_state(runner, service)
        if (
            state.active_state == "active"
            and state.sub_state == "running"
            and state.main_pid > 0
            and state.main_pid != original_pid
        ):
            return state
        if monotonic_fn() >= deadline:
            raise VerificationError(
                f"{service} did not recover with a new PID within {timeout_sec:.1f}s"
            )
        sleep_fn(poll_interval_sec)


def verify_service(
    runner: CommandRunner,
    *,
    service: str = DEFAULT_SERVICE,
    dependency: str = DEFAULT_DEPENDENCY,
    timeout_sec: float = 30.0,
    poll_interval_sec: float = 1.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> VerificationResult:
    """Verify active state, dependency wiring, and restart recovery."""
    service_state = read_service_state(runner, service)
    _assert_active_running(service_state, service)
    _assert_dependency_present(service_state, dependency)

    dependency_state = read_dependency_state(runner, dependency)
    _assert_active_running(dependency_state, dependency)

    original_pid = service_state.main_pid
    if original_pid <= 0:
        raise VerificationError(f"{service} has no live MainPID to kill")

    runner.run(["kill", "-9", str(original_pid)])
    recovered_state = _wait_for_restart(
        runner,
        service=service,
        original_pid=original_pid,
        timeout_sec=timeout_sec,
        poll_interval_sec=poll_interval_sec,
        sleep_fn=sleep_fn,
        monotonic_fn=monotonic_fn,
    )
    return VerificationResult(
        service=service,
        dependency=dependency,
        service_state=service_state,
        dependency_state=dependency_state,
        recovered_state=recovered_state,
        original_pid=original_pid,
        restarted_pid=recovered_state.main_pid,
    )


def main(
    argv: list[str] | None = None,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=None, help="optional SSH host target")
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--dependency", default=DEFAULT_DEPENDENCY)
    parser.add_argument("--timeout-sec", type=float, default=30.0)
    parser.add_argument("--poll-interval-sec", type=float, default=1.0)
    args = parser.parse_args(argv)

    runner = build_runner(args.host)
    try:
        result = verify_service(
            runner,
            service=args.service,
            dependency=args.dependency,
            timeout_sec=args.timeout_sec,
            poll_interval_sec=args.poll_interval_sec,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )
    except VerificationError as exc:
        print(f"VERIFICATION_FAILED {exc}", file=sys.stderr)
        return 1

    print(
        "SERVICE_ACTIVE "
        f"service={result.service} "
        f"state={result.service_state.active_state}/{result.service_state.sub_state} "
        f"pid={result.original_pid}"
    )
    print(
        "JACK_DEPENDENCY_OK "
        f"service={result.service} "
        f"dependency={result.dependency} "
        f"state={result.dependency_state.active_state}/{result.dependency_state.sub_state}"
    )
    print(
        "RESTART_OK "
        f"service={result.service} "
        f"original_pid={result.original_pid} "
        f"restarted_pid={result.restarted_pid}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
