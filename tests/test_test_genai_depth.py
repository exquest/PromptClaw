"""Depth-2 tests for root test_genai smoke probe [frac-0053]."""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import test_genai  # noqa: E402

TEST_GENAI_MODULE_PATH = REPO_ROOT / "test_genai.py"


class _FakeModel:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeModels:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    def list(self) -> list[_FakeModel]:
        return [_FakeModel(name) for name in self._names]


class _FakeClient:
    def __init__(self, names: list[str]) -> None:
        self.models = _FakeModels(names)


class _BrokenClient:
    @property
    def models(self) -> _FakeModels:
        raise RuntimeError("default credentials not found")


def test_test_genai_imports_with_probe_surface() -> None:
    for name in (
        "GenAIProbeResult",
        "create_genai_client",
        "list_model_names",
        "probe_genai_client",
        "summarize_probe_result",
        "format_probe_lines",
        "main",
    ):
        assert hasattr(test_genai, name)


def test_create_genai_client_constructs_client(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("google.genai")
    from google import genai

    explicit = test_genai.create_genai_client(api_key="explicit-test-key")
    assert isinstance(explicit, genai.Client)

    monkeypatch.setenv("GOOGLE_API_KEY", "default-test-key")
    default = test_genai.create_genai_client()
    assert isinstance(default, genai.Client)


def test_list_model_names_respects_limit() -> None:
    client = _FakeClient(["models/gemini-1.5-pro", "models/gemini-1.5-flash", "models/embedding-001"])

    names = test_genai.list_model_names(client, limit=2)

    assert names == ("models/gemini-1.5-pro", "models/gemini-1.5-flash")


def test_probe_genai_client_success_path() -> None:
    client = _FakeClient(["models/gemini-1.5-pro", "models/gemini-1.5-flash"])

    result = test_genai.probe_genai_client(max_models=1, client=client)

    assert isinstance(result, test_genai.GenAIProbeResult)
    assert dataclasses.is_dataclass(result)
    assert getattr(result, "__dataclass_params__").frozen
    assert result.ok is True
    assert result.error == ""
    assert result.model_count == 1
    assert result.sampled_models == ("models/gemini-1.5-pro",)


def test_probe_genai_client_error_path() -> None:
    result = test_genai.probe_genai_client(max_models=1, client=_BrokenClient())

    assert result.ok is False
    assert result.error == "default credentials not found"
    assert result.model_count == 0
    assert result.sampled_models == ()


def test_summarize_probe_result_is_json_safe() -> None:
    result = test_genai.GenAIProbeResult(
        ok=True,
        error="",
        model_count=2,
        sampled_models=("models/a", "models/b"),
    )

    summary = test_genai.summarize_probe_result(result)

    assert summary == {
        "ok": True,
        "error": "",
        "model_count": 2,
        "sampled_models": ["models/a", "models/b"],
    }
    json.dumps(summary)


def test_format_probe_lines_matches_canonical_output() -> None:
    success = test_genai.GenAIProbeResult(
        ok=True,
        error="",
        model_count=1,
        sampled_models=("models/gemini-1.5-pro",),
    )

    assert test_genai.format_probe_lines(success) == (
        "Successfully created client without explicit API key.",
        "Model: models/gemini-1.5-pro",
    )

    failure = test_genai.GenAIProbeResult(
        ok=False,
        error="auth boom",
        model_count=0,
        sampled_models=(),
    )

    assert test_genai.format_probe_lines(failure) == ("Error: auth boom",)


def test_main_returns_zero_and_prints_probe_lines(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    canned = test_genai.GenAIProbeResult(
        ok=True,
        error="",
        model_count=1,
        sampled_models=("models/gemini-1.5-pro",),
    )
    monkeypatch.setattr(test_genai, "probe_genai_client", lambda: canned)

    exit_code = test_genai.main()

    assert exit_code == 0
    captured = capsys.readouterr().out.splitlines()
    assert captured == [
        "Successfully created client without explicit API key.",
        "Model: models/gemini-1.5-pro",
    ]


def test_test_genai_module_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(str(TEST_GENAI_MODULE_PATH))
    assert result.depth >= 2, result.reason
