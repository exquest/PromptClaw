"""Tests for the Gemini image generation helper."""

from __future__ import annotations

import base64
import importlib.util
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_gemini_image_module() -> object:
    candidates = [
        Path(__file__).parent.parent / "my-claw" / "tools" / "gemini_image.py",
        Path(__file__).parent.parent / "tools" / "gemini_image.py",
    ]
    module_path = next((path for path in candidates if path.exists()), candidates[0])
    spec = importlib.util.spec_from_file_location("gemini_image_test_module", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_image_saves_binary_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_gemini_image_module()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(module, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(module, "MODEL", "gemini-test")

    image_bytes = b"fake-image-bytes"

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            assert api_key == "test-key"
            self.models = self

        def generate_content(self, *, model: str, contents: str, config: object) -> SimpleNamespace:
            assert model == "gemini-test"
            assert contents == "draw a crab"
            return SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=SimpleNamespace(
                            parts=[
                                SimpleNamespace(
                                    inline_data=SimpleNamespace(
                                        mime_type="image/png",
                                        data=base64.b64encode(image_bytes).decode(),
                                    ),
                                    text=None,
                                ),
                                SimpleNamespace(inline_data=None, text="generated caption"),
                            ]
                        )
                    )
                ]
            )

    fake_types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)
    monkeypatch.setattr(module, "genai", SimpleNamespace(Client=FakeClient))
    monkeypatch.setattr(module, "types", fake_types)

    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)

    image_path = module.generate_image("draw a crab")

    assert image_path.exists()
    assert image_path.read_bytes() == image_bytes
    output = stdout.getvalue()
    assert "image_path:" in output
    assert "caption: generated caption" in output


def test_main_reads_prompt_from_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_gemini_image_module()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("paint stars")
    called: list[str] = []

    monkeypatch.setattr(module, "generate_image", lambda prompt: called.append(prompt) or Path("/tmp/out.png"))
    monkeypatch.setattr(sys, "argv", ["gemini_image.py", str(prompt_file)])

    module.main()

    assert called == ["paint stars"]


def test_generate_image_exits_cleanly_when_no_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_gemini_image_module()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(module, "OUTPUT_DIR", tmp_path)

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            assert api_key == "test-key"
            self.models = self

        def generate_content(self, *, model: str, contents: str, config: object) -> SimpleNamespace:
            return SimpleNamespace(candidates=[])

    stderr = io.StringIO()
    monkeypatch.setattr(module, "genai", SimpleNamespace(Client=FakeClient))
    monkeypatch.setattr(module, "types", SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs))
    monkeypatch.setattr(sys, "stderr", stderr)

    with pytest.raises(SystemExit):
        module.generate_image("draw a lighthouse")

    assert "WARNING: No image returned by the model." in stderr.getvalue()
