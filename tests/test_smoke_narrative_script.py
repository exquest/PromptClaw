"""Regression tests for scripts/smoke_narrative.py."""

from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import ModuleType
from typing import Iterator, NamedTuple

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "smoke_narrative.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("smoke_narrative", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Handler(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, bytes]] = {}
    seen_requests: list["_SeenRequest"] = []

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def _handle(self, method: str) -> None:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        request_body = self.rfile.read(content_length) if content_length else b""
        type(self).seen_requests.append(
            _SeenRequest(
                method=method,
                path=self.path,
                authorization=self.headers.get("Authorization"),
                narrative_auth=self.headers.get("X-Narrative-Auth"),
                body=request_body,
            )
        )
        status, body = self.routes.get((method, self.path), (404, b"not found"))
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _SeenRequest(NamedTuple):
    method: str
    path: str
    authorization: str | None
    narrative_auth: str | None
    body: bytes


@pytest.fixture()
def http_server() -> Iterator[tuple[str, type[_Handler]]]:
    handler_cls = type(
        "Handler",
        (_Handler,),
        {"routes": {}, "seen_requests": []},
    )
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}", handler_cls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def _ok_routes(
    entity_body: bytes | None = None,
) -> dict[tuple[str, str], tuple[int, bytes]]:
    return {
        ("GET", "/health"): (200, b'{"status":"ok"}'),
        ("POST", "/memory/search"): (200, b'{"results":[]}'),
        ("POST", "/beats/next"): (200, b'{"id":"beat-smoke"}'),
        (
            "GET",
            "/world/entities?limit=1",
        ): (
            200,
            entity_body
            or b'{"entities":[{"id":"e1","type":"character","name":"Alice",'
            b'"domain":"shared","properties":{}}]}',
        ),
        ("GET", "/world/entities/e1"): (200, b'{"id":"e1"}'),
        ("GET", "/events?limit=1"): (200, b'{"events":[],"next_event_id":null}'),
    }


def test_main_returns_zero_when_all_endpoints_2xx(
    http_server: tuple[str, type[_Handler]], capsys: pytest.CaptureFixture[str]
) -> None:
    base_url, handler = http_server
    handler.routes = _ok_routes()
    module = _load_script()

    rc = module.main(["--base-url", base_url])

    out = capsys.readouterr().out
    assert rc == 0
    assert "GET /health -> 200" in out
    assert "POST /memory/search -> 200" in out
    assert "POST /beats/next -> 200" in out
    assert "GET /world/entities?limit=1 -> 200" in out
    assert "GET /world/entities/e1 -> 200" in out
    assert "GET /events?limit=1 -> 200" in out


def test_main_returns_nonzero_when_any_endpoint_non_2xx(
    http_server: tuple[str, type[_Handler]], capsys: pytest.CaptureFixture[str]
) -> None:
    base_url, handler = http_server
    handler.routes = _ok_routes()
    handler.routes[("POST", "/beats/next")] = (503, b"down")
    module = _load_script()

    rc = module.main(["--base-url", base_url])

    out = capsys.readouterr().out
    assert rc == 1
    assert "GET /health -> 200" in out
    assert "POST /beats/next -> 503" in out


def test_main_returns_nonzero_when_unreachable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()

    # Port 1 is reserved/unused — connection should fail fast.
    rc = module.main(["--base-url", "http://127.0.0.1:1"])

    out = capsys.readouterr().out
    assert rc == 1
    assert "GET /health -> ERROR" in out
    assert "POST /memory/search -> ERROR" in out


def test_main_sends_auth_headers_when_token_provided(
    http_server: tuple[str, type[_Handler]],
) -> None:
    base_url, handler = http_server
    handler.routes = _ok_routes()
    module = _load_script()

    rc = module.main(["--base-url", base_url, "--token", "secret-123"])

    assert rc == 0
    assert [request.path for request in handler.seen_requests] == [
        "/health",
        "/memory/search",
        "/beats/next",
        "/world/entities?limit=1",
        "/world/entities/e1",
        "/events?limit=1",
    ]
    assert {request.authorization for request in handler.seen_requests} == {
        "Bearer secret-123"
    }
    assert {request.narrative_auth for request in handler.seen_requests} == {
        "secret-123"
    }


def test_main_omits_authorization_header_when_no_token(
    http_server: tuple[str, type[_Handler]],
) -> None:
    base_url, handler = http_server
    handler.routes = _ok_routes()
    module = _load_script()

    rc = module.main(["--base-url", base_url])

    assert rc == 0
    assert {request.authorization for request in handler.seen_requests} == {None}
    assert {request.narrative_auth for request in handler.seen_requests} == {None}


def test_post_endpoints_use_minimal_valid_payloads(
    http_server: tuple[str, type[_Handler]],
) -> None:
    base_url, handler = http_server
    handler.routes = _ok_routes()
    module = _load_script()

    rc = module.main(["--base-url", base_url])

    assert rc == 0
    payloads = {
        request.path: json.loads(request.body)
        for request in handler.seen_requests
        if request.method == "POST"
    }
    assert payloads == {
        "/memory/search": {"query": "smoke", "k": 1, "domain_filter": "shared"},
        "/beats/next": {"cycle_number": 0, "domain_filter": "shared"},
    }


def test_verbose_body_preview_is_truncated(
    http_server: tuple[str, type[_Handler]], capsys: pytest.CaptureFixture[str]
) -> None:
    base_url, handler = http_server
    big_body = b"x" * 1000
    handler.routes = _ok_routes()
    handler.routes[("GET", "/health")] = (200, big_body)
    module = _load_script()

    rc = module.main(["--base-url", base_url, "--verbose"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "..." in out
    health_line = next(
        line for line in out.splitlines() if line.startswith("GET /health")
    )
    assert len(health_line) < 260


def test_empty_entity_list_skips_entity_get_without_failing(
    http_server: tuple[str, type[_Handler]], capsys: pytest.CaptureFixture[str]
) -> None:
    base_url, handler = http_server
    handler.routes = _ok_routes(entity_body=b'{"entities":[]}')
    module = _load_script()

    rc = module.main(["--base-url", base_url])

    out = capsys.readouterr().out
    assert rc == 0
    assert "GET /world/entities/{entity_id} -> SKIP no entity id returned" in out
    assert "/world/entities/e1" not in {
        request.path for request in handler.seen_requests
    }
