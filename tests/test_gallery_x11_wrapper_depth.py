"""Depth-2 wrapper behavior tests for the X11 gallery launcher shim."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))


@pytest.fixture()
def wrapper(monkeypatch):
    """Reload the wrapper module fresh for each test."""
    if "gallery_x11" in sys.modules:
        del sys.modules["gallery_x11"]
    module = importlib.import_module("gallery_x11")
    yield module
    if "gallery_x11" in sys.modules:
        del sys.modules["gallery_x11"]


def test_parse_args_supports_display_window_pos_and_check(wrapper) -> None:
    args = wrapper.parse_args(["--display", ":0.1", "--window-pos", "50,60", "--check"])
    assert args.display == ":0.1"
    assert args.window_pos == "50,60"
    assert args.check is True


def test_parse_args_defaults_are_none_and_check_false(wrapper) -> None:
    args = wrapper.parse_args([])
    assert args.display is None
    assert args.window_pos is None
    assert args.check is False


def test_runtime_summary_reflects_explicit_environment(wrapper, tmp_path) -> None:
    art_dir = tmp_path / "renders"
    art_dir.mkdir()

    summary = wrapper.runtime_summary({"DISPLAY": ":0.1"})

    assert summary["display"] == ":0.1"
    assert summary["window_pos"] == "0,0"
    assert "x" in summary["resolution"]
    assert summary["duration_seconds"] == wrapper.DURATION
    assert summary["art_dir"] == str(wrapper.ART_DIR)
    assert summary["art_dir_exists"] is wrapper.ART_DIR.exists()


def test_validate_runtime_reports_missing_display_and_art_dir(wrapper, monkeypatch) -> None:
    monkeypatch.setattr(wrapper, "ART_DIR", Path("/definitely/not/a/real/dir"))

    problems = wrapper.validate_runtime({})

    assert "DISPLAY is not set" in problems
    assert any("art directory missing" in p for p in problems)


def test_validate_runtime_returns_empty_when_healthy(wrapper, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wrapper, "ART_DIR", tmp_path)

    problems = wrapper.validate_runtime({"DISPLAY": ":0"})

    assert problems == ()


def test_apply_overrides_sets_env_vars_when_supplied(wrapper) -> None:
    env: dict[str, str] = {}
    args = wrapper.parse_args(["--display", ":1", "--window-pos", "10,20"])

    wrapper.apply_overrides(args, env)

    assert env["DISPLAY"] == ":1"
    assert env["GALLERY_WINDOW_POS"] == "10,20"


def test_apply_overrides_is_noop_when_args_are_default(wrapper) -> None:
    env: dict[str, str] = {"DISPLAY": ":0"}
    args = wrapper.parse_args([])

    wrapper.apply_overrides(args, env)

    assert env == {"DISPLAY": ":0"}


def test_main_check_mode_reports_problems_without_delegating(
    wrapper, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(wrapper, "ART_DIR", Path("/definitely/not/a/real/dir"))
    monkeypatch.delenv("DISPLAY", raising=False)
    called = {"delegate": False}
    monkeypatch.setattr(wrapper, "_delegate_main", lambda: called.__setitem__("delegate", True))

    rc = wrapper.main(["--check"])

    captured = capsys.readouterr()
    assert rc == 1
    assert called["delegate"] is False
    assert "DISPLAY is not set" in captured.err


def test_main_check_mode_returns_zero_when_clean(wrapper, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(wrapper, "ART_DIR", tmp_path)
    monkeypatch.setenv("DISPLAY", ":0")
    called = {"delegate": False}
    monkeypatch.setattr(wrapper, "_delegate_main", lambda: called.__setitem__("delegate", True))

    rc = wrapper.main(["--check"])

    assert rc == 0
    assert called["delegate"] is False


def test_main_runs_delegate_when_runtime_is_clean(wrapper, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(wrapper, "ART_DIR", tmp_path)
    monkeypatch.setenv("DISPLAY", ":0")
    called = {"delegate": False}
    monkeypatch.setattr(wrapper, "_delegate_main", lambda: called.__setitem__("delegate", True))

    rc = wrapper.main([])

    assert rc == 0
    assert called["delegate"] is True


def test_main_aborts_when_runtime_invalid(wrapper, monkeypatch, capsys) -> None:
    monkeypatch.setattr(wrapper, "ART_DIR", Path("/definitely/not/a/real/dir"))
    monkeypatch.delenv("DISPLAY", raising=False)
    called = {"delegate": False}
    monkeypatch.setattr(wrapper, "_delegate_main", lambda: called.__setitem__("delegate", True))

    rc = wrapper.main([])

    captured = capsys.readouterr()
    assert rc == 1
    assert called["delegate"] is False
    assert "DISPLAY is not set" in captured.err
