"""Per-request resource ceilings for the Deniable Asset Bus.

Requests are written by an untrusted requester and imply bounded work:
generating ``count`` images, rendering ``duration_seconds`` of music. Without
explicit ceilings, a request can ask for unbounded work (10_000 images, an
hour of music) and pin the box or fill the bus disk. This module is the
single source of truth for those ceilings.

:func:`check_request_within_ceilings` raises :class:`CeilingExceededError` on
the first ceiling a request would breach; :func:`error_manifest_for_ceiling`
turns that exception into the v0.1 ``error`` manifest the producer writes
back to the bus.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "CeilingExceededError",
    "MAX_IMAGES_PER_REQUEST",
    "MAX_MUSIC_DURATION_SECONDS",
    "MAX_TOTAL_OUTPUT_BYTES",
    "check_request_within_ceilings",
    "error_manifest_for_ceiling",
]


MAX_IMAGES_PER_REQUEST: int = 8
MAX_MUSIC_DURATION_SECONDS: int = 600
MAX_TOTAL_OUTPUT_BYTES: int = 256 * 1024 * 1024

_WAV_BYTES_PER_SECOND: int = 44_100 * 2 * 2
_IMAGE_BYTES_PER_PIXEL: int = 4
_DEFAULT_IMAGE_W: int = 512
_DEFAULT_IMAGE_H: int = 512

_SCHEMA: str = "deniable-asset-bus/v0.1"


class CeilingExceededError(ValueError):
    """Raised when a request would exceed one of the per-request ceilings."""

    def __init__(self, ceiling: str, limit: int, requested: int) -> None:
        self.ceiling = ceiling
        self.limit = limit
        self.requested = requested
        super().__init__(
            f"{ceiling} ceiling exceeded: requested {requested}, limit {limit}"
        )


def _spec(request: Mapping[str, Any]) -> Mapping[str, Any]:
    spec = request.get("spec")
    return spec if isinstance(spec, Mapping) else {}


def _int_field(spec: Mapping[str, Any], key: str, default: int) -> int:
    value = spec.get(key, default)
    if value is None or isinstance(value, bool):
        return default
    if not isinstance(value, (int, float)):
        return default
    return int(value)


def check_request_within_ceilings(request: Mapping[str, Any]) -> None:
    """Raise :class:`CeilingExceededError` if any ceiling is exceeded.

    Estimates output bytes with conservative upper bounds (raw RGBA for
    images, 16-bit stereo PCM at 44.1 kHz for audio) so a request that
    *might* breach the byte ceiling is rejected up front.
    """
    asset_type = request.get("asset_type")
    spec = _spec(request)

    if asset_type == "image":
        count = _int_field(spec, "count", 1)
        if count > MAX_IMAGES_PER_REQUEST:
            raise CeilingExceededError("image_count", MAX_IMAGES_PER_REQUEST, count)
        width = _int_field(spec, "width", _DEFAULT_IMAGE_W)
        height = _int_field(spec, "height", _DEFAULT_IMAGE_H)
        estimated = (
            max(count, 0)
            * max(width, 0)
            * max(height, 0)
            * _IMAGE_BYTES_PER_PIXEL
        )
        if estimated > MAX_TOTAL_OUTPUT_BYTES:
            raise CeilingExceededError(
                "total_output_bytes", MAX_TOTAL_OUTPUT_BYTES, estimated
            )
        return

    if asset_type in ("music", "sfx"):
        duration = _int_field(spec, "duration_seconds", 0)
        if asset_type == "music" and duration > MAX_MUSIC_DURATION_SECONDS:
            raise CeilingExceededError(
                "music_duration_seconds", MAX_MUSIC_DURATION_SECONDS, duration
            )
        count = _int_field(spec, "count", 1)
        estimated = max(count, 1) * max(duration, 0) * _WAV_BYTES_PER_SECOND
        if estimated > MAX_TOTAL_OUTPUT_BYTES:
            raise CeilingExceededError(
                "total_output_bytes", MAX_TOTAL_OUTPUT_BYTES, estimated
            )
        return


def error_manifest_for_ceiling(
    request: Mapping[str, Any], err: CeilingExceededError
) -> dict[str, Any]:
    """Build a v0.1 ``error`` manifest naming the exceeded ceiling."""
    return {
        "request_id": request.get("request_id"),
        "schema": _SCHEMA,
        "status": "error",
        "producer": "cypherclaw",
        "assets": [],
        "notes": f"per-request ceiling exceeded: {err.ceiling}",
        "error": str(err),
    }
