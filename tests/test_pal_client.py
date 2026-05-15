from __future__ import annotations

import argparse
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest

from promptclaw.cli import cmd_pal_health, cmd_pal_query
from promptclaw.config import default_project_config, load_config, save_config, validate_config
from promptclaw.models import PALConfig
from promptclaw.pal_client import PALClientError, PALRouterClient


class _FakeResponse:
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status = status
        self._body = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def test_pal_client_reads_health_from_configured_router() -> None:
    calls: list[dict[str, Any]] = []

    def fake_urlopen(req: Any, *, timeout: float) -> _FakeResponse:
        calls.append({"url": req.full_url, "method": req.get_method(), "timeout": timeout})
        return _FakeResponse(
            200,
            {
                "status": "green",
                "ollama_available": True,
                "loaded_models": ["llama3.3:70b-instruct-q4_K_M"],
            },
        )

    client = PALRouterClient(
        base_url="http://pal-cloud-a6000:8000/",
        default_model="llama3.3:70b-instruct-q4_K_M",
        health_timeout_s=7.5,
        opener=fake_urlopen,
    )

    health = client.health()

    assert health["status"] == "green"
    assert health["ollama_available"] is True
    assert calls == [
        {
            "url": "http://pal-cloud-a6000:8000/health",
            "method": "GET",
            "timeout": 7.5,
        }
    ]


def test_pal_client_query_posts_prompt_payload_and_returns_text() -> None:
    calls: list[dict[str, Any]] = []

    def fake_urlopen(req: Any, *, timeout: float) -> _FakeResponse:
        calls.append(
            {
                "url": req.full_url,
                "method": req.get_method(),
                "timeout": timeout,
                "payload": json.loads(req.data.decode()),
            }
        )
        return _FakeResponse(
            200,
            {
                "model": "llama3.3:70b-instruct-q4_K_M",
                "response": "PAL is reachable.",
                "done": True,
            },
        )

    client = PALRouterClient(
        base_url="http://pal-cloud-a6000:8000",
        default_model="llama3.3:70b-instruct-q4_K_M",
        timeout_s=123.0,
        opener=fake_urlopen,
    )

    result = client.query(
        "Confirm reachability.",
        system="You are PAL.",
        temperature=0.3,
    )

    assert result.text == "PAL is reachable."
    assert result.raw["done"] is True
    assert calls == [
        {
            "url": "http://pal-cloud-a6000:8000/query",
            "method": "POST",
            "timeout": 123.0,
            "payload": {
                "prompt": "Confirm reachability.",
                "model": "llama3.3:70b-instruct-q4_K_M",
                "system": "You are PAL.",
                "stream": False,
                "temperature": 0.3,
            },
        }
    ]


def test_pal_client_wraps_network_failures() -> None:
    def fake_urlopen(req: Any, *, timeout: float) -> _FakeResponse:
        raise URLError("connection refused")

    client = PALRouterClient(base_url="http://pal-cloud-a6000:8000", opener=fake_urlopen)

    with pytest.raises(PALClientError) as excinfo:
        client.health()

    assert "GET http://pal-cloud-a6000:8000/health failed" in str(excinfo.value)
    assert "connection refused" in str(excinfo.value)


class PALConfigTests(unittest.TestCase):
    def test_pal_config_round_trips_through_project_config(self) -> None:
        project_root = Path(tempfile.mkdtemp(prefix="promptclaw-pal-config-"))
        self.addCleanup(shutil.rmtree, project_root)
        config = default_project_config("PAL Config Claw")
        config.pal = PALConfig(
            base_url="http://pal-cloud-a6000:8000",
            default_model="llama3.3:70b-instruct-q4_K_M",
            timeout_s=250.0,
            health_timeout_s=8.0,
        )

        save_config(project_root, config)
        loaded = load_config(project_root)

        self.assertEqual(loaded.pal.base_url, "http://pal-cloud-a6000:8000")
        self.assertEqual(loaded.pal.default_model, "llama3.3:70b-instruct-q4_K_M")
        self.assertEqual(loaded.pal.timeout_s, 250.0)
        self.assertEqual(loaded.pal.health_timeout_s, 8.0)
        self.assertEqual(validate_config(loaded), [])

    def test_pal_config_validation_reports_bad_timeouts(self) -> None:
        config = default_project_config("Broken PAL Config")
        config.pal.base_url = " "
        config.pal.timeout_s = 0
        config.pal.health_timeout_s = -1

        issues = validate_config(config)

        self.assertIn("pal.base_url must not be empty", issues)
        self.assertIn("pal.timeout_s must be > 0", issues)
        self.assertIn("pal.health_timeout_s must be > 0", issues)


def test_pal_cli_health_prints_router_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = default_project_config("PAL CLI Claw")
    save_config(tmp_path, config)

    class FakeClient:
        @classmethod
        def from_config(cls, loaded_config: Any) -> FakeClient:
            assert loaded_config.pal.base_url == "http://pal-cloud-a6000:8000"
            return cls()

        def health(self) -> dict[str, Any]:
            return {"status": "green", "phase": "phase-1-a6000"}

    monkeypatch.setattr("promptclaw.cli.PALRouterClient", FakeClient)

    output = io.StringIO()
    with redirect_stdout(output):
        rc = cmd_pal_health(argparse.Namespace(project_root=tmp_path))

    assert rc == 0
    assert json.loads(output.getvalue()) == {"status": "green", "phase": "phase-1-a6000"}


def test_pal_cli_query_can_print_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = default_project_config("PAL CLI Query Claw")
    save_config(tmp_path, config)
    observed: dict[str, Any] = {}

    class FakeResult:
        text = "PAL query response."
        raw = {"response": text, "done": True}

    class FakeClient:
        @classmethod
        def from_config(cls, loaded_config: Any) -> FakeClient:
            return cls()

        def query(self, **kwargs: Any) -> FakeResult:
            observed.update(kwargs)
            return FakeResult()

    monkeypatch.setattr("promptclaw.cli.PALRouterClient", FakeClient)

    output = io.StringIO()
    args = argparse.Namespace(
        project_root=tmp_path,
        prompt="Reachability?",
        system="You are PAL.",
        model="custom-model",
        temperature=0.2,
        text=True,
    )
    with redirect_stdout(output):
        rc = cmd_pal_query(args)

    assert rc == 0
    assert output.getvalue() == "PAL query response.\n"
    assert observed == {
        "prompt": "Reachability?",
        "system": "You are PAL.",
        "model": "custom-model",
        "temperature": 0.2,
    }
