from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import PromptClawConfig

UrlOpener = Callable[..., Any]


class PALClientError(RuntimeError):
    """Raised when the PAL router cannot be reached or returns bad data."""


@dataclass(frozen=True)
class PALQueryResult:
    text: str
    raw: dict[str, Any]


class PALRouterClient:
    def __init__(
        self,
        *,
        base_url: str,
        default_model: str = "",
        timeout_s: float = 300.0,
        health_timeout_s: float = 10.0,
        opener: UrlOpener = urlopen,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout_s = timeout_s
        self.health_timeout_s = health_timeout_s
        self._opener = opener

    @classmethod
    def from_config(cls, config: PromptClawConfig) -> PALRouterClient:
        return cls(
            base_url=config.pal.base_url,
            default_model=config.pal.default_model,
            timeout_s=config.pal.timeout_s,
            health_timeout_s=config.pal.health_timeout_s,
        )

    def health(self) -> dict[str, Any]:
        url = f"{self.base_url}/health"
        return self._request_json("GET", url, timeout=self.health_timeout_s)

    def query(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = 0.7,
    ) -> PALQueryResult:
        url = f"{self.base_url}/query"
        payload: dict[str, Any] = {
            "prompt": prompt,
            "stream": False,
            "temperature": temperature,
        }
        selected_model = model or self.default_model
        if selected_model:
            payload["model"] = selected_model
        if system:
            payload["system"] = system

        raw = self._request_json("POST", url, timeout=self.timeout_s, payload=payload)
        text = str(raw.get("response", ""))
        return PALQueryResult(text=text, raw=raw)

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        timeout: float,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        req = Request(url, data=body, headers=headers, method=method)

        try:
            with self._opener(req, timeout=timeout) as resp:
                status = int(getattr(resp, "status", 200))
                response_body = resp.read()
        except HTTPError as exc:
            detail = _read_error_body(exc)
            raise PALClientError(f"{method} {url} returned HTTP {exc.code}: {detail}") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise PALClientError(f"{method} {url} failed: {exc}") from exc

        if status < 200 or status >= 300:
            raise PALClientError(f"{method} {url} returned HTTP {status}: {response_body[:200]!r}")

        try:
            decoded = json.loads(response_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PALClientError(f"{method} {url} returned invalid JSON") from exc

        if not isinstance(decoded, dict):
            raise PALClientError(f"{method} {url} returned non-object JSON")
        return decoded


def _read_error_body(exc: HTTPError) -> str:
    try:
        return exc.read().decode(errors="replace")[:500]
    except Exception:
        return str(exc)
