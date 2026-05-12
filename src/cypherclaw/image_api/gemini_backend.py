"""Thin wrapper around the google-genai SDK for image generation.

Lazy SDK import: tests inject a fake `client` and never trigger the
real `google.genai` import. Network calls happen only inside
`generate_image`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Protocol

from .config import Settings, settings as default_settings
from .schemas import InternalSpec


class _ModelsProtocol(Protocol):
    def generate_content(self, **kwargs): ...


class _GenAIClientProtocol(Protocol):
    @property
    def models(self) -> _ModelsProtocol: ...


@dataclass(frozen=True)
class GenerationResult:
    image_bytes: bytes
    content_type: str
    cost_usd: float
    model_used: str


class GeminiBackendError(RuntimeError):
    """Raised on any non-recoverable Gemini error (invalid key, refusal,
    safety block, network failure surfaced as terminal)."""


def _build_client(s: Settings) -> _GenAIClientProtocol:
    api_key = os.environ.get(s.gemini_api_key_env)
    if not api_key:
        raise GeminiBackendError(
            f"missing {s.gemini_api_key_env} in environment"
        )
    from google import genai  # noqa: WPS433
    client: _GenAIClientProtocol = genai.Client(api_key=api_key)  # type: ignore[assignment]
    return client


# Per-model rough cost estimate (USD per image). Overridden by API
# response when provider includes cost in metadata.
_COST_PER_IMAGE: dict[str, float] = {
    "gemini-3-pro-image-preview": 0.134,
    "gemini-3.1-flash-image-preview": 0.04,
    "gemini-2.5-flash-image": 0.04,
}


def _resolve_model(spec: InternalSpec, s: Settings) -> str:
    return spec.model_override or s.gemini_default_model


def _extract_image_bytes(response) -> tuple[bytes, str]:
    """Pull image bytes + mime type out of a google-genai response.

    The SDK returns image data on `candidates[0].content.parts[].inline_data`.
    """
    candidates = getattr(response, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is None:
                continue
            data = getattr(inline, "data", None)
            mime = getattr(inline, "mime_type", None) or "image/png"
            if data:
                return bytes(data), mime
    raise GeminiBackendError("Gemini response had no inline_data image part")


def generate_image(
    spec: InternalSpec,
    *,
    s: Optional[Settings] = None,
    client: Optional[_GenAIClientProtocol] = None,
) -> GenerationResult:
    """Render `spec` into image bytes via Gemini.

    The `client` arg is for tests; when None we build a real one (which
    requires GEMINI_API_KEY)."""
    s = s or default_settings
    cli = client or _build_client(s)
    model = _resolve_model(spec, s)

    # Build a single-part text prompt. Gemini-3-pro-image-preview accepts
    # plain string content; size hints are injected into the prompt
    # itself since `dimensions` isn't a first-class API arg yet.
    contents = (
        f"{spec.prompt}\n\n"
        f"Render at approximately {spec.width}x{spec.height} pixels. "
        f"{('Style: ' + spec.style) if spec.style else ''}"
    ).strip()

    try:
        response = cli.models.generate_content(
            model=model,
            contents=contents,
        )
    except GeminiBackendError:
        raise
    except Exception as exc:  # network / SDK level
        raise GeminiBackendError(f"Gemini call failed: {exc}") from exc

    image_bytes, mime = _extract_image_bytes(response)

    # Prefer cost from response metadata when provider exposes it,
    # otherwise fall back to per-model table.
    cost = _cost_from_response(response)
    if cost is None:
        cost = _COST_PER_IMAGE.get(model, 0.0)

    return GenerationResult(
        image_bytes=image_bytes,
        content_type=mime,
        cost_usd=cost,
        model_used=model,
    )


def _cost_from_response(response) -> Optional[float]:
    """Pull `usage_metadata.total_cost_usd` if present."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None
    cost = getattr(usage, "total_cost_usd", None)
    if cost is None:
        return None
    try:
        return float(cost)
    except (TypeError, ValueError):
        return None
