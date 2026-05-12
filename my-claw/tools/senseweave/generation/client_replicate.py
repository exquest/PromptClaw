"""Replicate API client with bounded retry on transient failures.

Retry policy (CCG-011 / T-002):
  - Retry on HTTP 429 and 5xx; never on other 4xx and never on 2xx success.
  - Backoff schedule: 5s -> 30s -> 5min before retry attempts 1, 2, 3.
  - If a ``Retry-After`` header is present and *larger* than the scheduled
    backoff, honor the header instead.
  - Maximum 3 retries on top of the initial attempt (4 total submissions).
    If all four fail, ``GenerationError`` is raised.

Submission (CCG-010 / T-001) calls ``replicate.predictions.create`` and maps
HTTP failures to :class:`ReplicateAPIError` so the retry layer engages.
The full submit→poll→download flow is wired through :meth:`ReplicateClient.generate`.
"""

from __future__ import annotations

import logging
import tempfile
import time
import urllib.request
import wave
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar, overload

try:
    import replicate  # type: ignore
except ImportError:
    replicate = None  # type: ignore

from .budget import OVERHEAD_FACTOR, PER_SECOND_USD
from .client_protocol import GenerationResult
from .request import GenerationRequest

logger = logging.getLogger(__name__)

T = TypeVar("T")


class GenerationError(Exception):
    """Generation failure surfaced to callers (queue, composer)."""


class ReplicateAPIError(Exception):
    """HTTP-level failure from Replicate, inspected by the retry layer.

    Tests construct this directly to emulate httpx-style responses; T-001
    will raise it from the real submission path on non-2xx responses.
    """

    def __init__(
        self,
        status_code: int,
        message: str = "",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(f"Replicate API error {status_code}: {message}".rstrip(": "))
        self.status_code = status_code
        self.retry_after = retry_after


BACKOFF_SCHEDULE: tuple[float, ...] = (5.0, 30.0, 300.0)
MAX_RETRIES: int = len(BACKOFF_SCHEDULE)
POLL_INTERVAL_SEC: float = 1.0


def _should_retry(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def _retry_after_seconds(headers: Mapping[str, str] | None) -> float | None:
    """Parse the seconds form of ``Retry-After``. HTTP-date form returns None."""
    if not headers:
        return None
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def raise_for_response(response: Any) -> None:
    """Raise :class:`ReplicateAPIError` if ``response`` is non-2xx.

    ``response`` is duck-typed httpx-style: it must expose ``status_code``
    and (optionally) ``headers``. Used by the live submission path and by
    tests that mock httpx ``Response`` objects.
    """
    code = int(response.status_code)
    if 200 <= code < 300:
        return
    headers = getattr(response, "headers", None)
    raise ReplicateAPIError(code, retry_after=_retry_after_seconds(headers))


class ReplicateClient:
    """Replicate-backed generation client.

    Only the retry surface is implemented here. The full submission/polling/
    download flow lands with T-001; tests for T-002 exercise
    :meth:`_submit_with_retry` directly with a fake submitter.
    """

    def __init__(
        self,
        api_token: str | None = None,
        timeout_sec: float = 120.0,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api_token = api_token
        self._timeout_sec = timeout_sec
        self._sleep = sleep
        self._clock = clock

    def _submit_with_retry(self, submit: Callable[[], T]) -> T:
        """Run ``submit`` under the retry policy described in the module docstring.

        ``submit`` must raise :class:`ReplicateAPIError` on retryable HTTP
        failures. Other exceptions propagate without retry.
        """
        last_error: ReplicateAPIError | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                return submit()
            except ReplicateAPIError as exc:
                last_error = exc
                if not _should_retry(exc.status_code):
                    raise GenerationError(
                        f"Replicate {exc.status_code}: not retryable"
                    ) from exc
                if attempt >= MAX_RETRIES:
                    break
                scheduled = BACKOFF_SCHEDULE[attempt]
                delay = scheduled
                if exc.retry_after is not None and exc.retry_after > scheduled:
                    delay = exc.retry_after
                logger.warning(
                    "replicate %d on attempt %d/%d; sleeping %.1fs",
                    exc.status_code,
                    attempt + 1,
                    MAX_RETRIES + 1,
                    delay,
                )
                self._sleep(delay)
        assert last_error is not None
        raise GenerationError(
            f"Replicate retry budget exhausted after {MAX_RETRIES + 1} attempts; "
            f"last status {last_error.status_code}"
        ) from last_error

    @overload
    def generate(self, request: GenerationRequest) -> GenerationResult: ...

    @overload
    def generate(self, request: Mapping[str, Any]) -> dict[str, Any]: ...

    def generate(self, request: Any) -> Any:
        """Submit a generation request through Replicate end to end.

        Wires submit (with retry) → poll-until-terminal → download-output.
        Dict-shaped legacy requests still return the downloaded payload
        inline. Typed ``GenerationRequest`` callers receive the shared
        ``GenerationResult`` schema.
        """
        start = self._clock()
        prediction = self._submit_with_retry(
            lambda: self._submit_prediction(request)
        )
        completed = self._poll_prediction(prediction)
        payload = self._download_output(completed)
        latency_ms = int((self._clock() - start) * 1000)
        model_used = (
            _request_field(request, "version")
            or _request_field(request, "model", "model_name")
            or ""
        )
        api_request_id = str(getattr(completed, "id", "") or "")
        if isinstance(request, GenerationRequest):
            audio_path = _write_payload_to_temp_file(payload, api_request_id)
            sample_rate, duration_actual_sec = _wav_metadata(audio_path)
            if duration_actual_sec <= 0.0:
                duration_actual_sec = float(request.duration_sec)
            return GenerationResult(
                audio_path=audio_path,
                sample_rate=sample_rate,
                duration_actual_sec=duration_actual_sec,
                model_used=str(model_used),
                cost_usd=_estimate_cost_usd(request, duration_actual_sec),
                latency_ms=latency_ms,
                api_request_id=api_request_id,
            )
        return {
            "audio_bytes": payload,
            "model_used": str(model_used),
            "prediction_id": api_request_id,
            "latency_ms": latency_ms,
        }

    def _poll_prediction(self, prediction: Any) -> Any:
        """Poll a Replicate prediction until it reaches a terminal status."""
        deadline = self._clock() + self._timeout_sec
        current = prediction
        while True:
            status = str(getattr(current, "status", "")).lower()
            if status == "succeeded":
                return current
            if status in {"failed", "canceled"}:
                detail = _prediction_error_detail(current)
                raise GenerationError(f"Replicate prediction {status}{detail}")

            now = self._clock()
            if now >= deadline:
                raise GenerationError(
                    f"Replicate prediction timed out after {self._timeout_sec:.1f}s"
                )

            self._sleep(min(POLL_INTERVAL_SEC, deadline - now))
            reload_prediction = getattr(current, "reload", None)
            if callable(reload_prediction):
                reloaded = reload_prediction()
                if reloaded is not None:
                    current = reloaded

    def _download_output(self, prediction: Any) -> bytes:
        """Resolve ``prediction.output`` to raw bytes.

        Accepts a single URL string, a list/tuple of URL strings, a
        ``FileOutput``-style object exposing ``read()``, or already-realized
        ``bytes``. Multiple outputs are concatenated in order.
        """
        output = getattr(prediction, "output", None)
        if output is None:
            raise GenerationError("Replicate prediction has no output")
        if isinstance(output, (list, tuple)):
            if not output:
                raise GenerationError("Replicate prediction output is empty")
            return b"".join(self._coerce_output_to_bytes(item) for item in output)
        return self._coerce_output_to_bytes(output)

    def _coerce_output_to_bytes(self, item: Any) -> bytes:
        if isinstance(item, (bytes, bytearray)):
            return bytes(item)
        reader = getattr(item, "read", None)
        if callable(reader):
            return bytes(reader())
        if isinstance(item, str):
            return self._fetch_bytes(item)
        raise GenerationError(
            f"Unsupported Replicate output element type: {type(item).__name__}"
        )

    def _fetch_bytes(self, url: str) -> bytes:
        """Download ``url`` to bytes, bounded by ``self._timeout_sec``."""
        try:
            with urllib.request.urlopen(url, timeout=self._timeout_sec) as resp:
                return resp.read()
        except OSError as exc:
            raise GenerationError(
                f"Replicate output download failed: {exc}"
            ) from exc

    def _submit_prediction(self, request: Any) -> Any:
        """Submit a prediction via ``replicate.predictions.create``.

        Extracts ``model`` (or ``version``) plus ``input`` from ``request``
        (mapping or attribute-bearing object) and forwards them to the
        Replicate SDK. HTTP failures surface as :class:`ReplicateAPIError`
        so :meth:`_submit_with_retry` can retry transient codes.
        """
        if replicate is None:
            raise GenerationError("replicate SDK not installed")

        model = _request_field(request, "model", "model_name")
        version = _request_field(request, "version")
        inputs = _request_field(request, "input", "inputs")
        if inputs is None:
            inputs = _derive_inputs(request)

        kwargs: dict[str, Any] = {"input": inputs}
        if version is not None:
            kwargs["version"] = str(version)
        elif model is not None:
            kwargs["model"] = str(model)
        else:
            raise GenerationError(
                "Replicate request missing both 'model' and 'version'"
            )

        client: Any = (
            replicate.Client(api_token=self._api_token)
            if self._api_token
            else replicate
        )
        try:
            return client.predictions.create(**kwargs)
        except Exception as exc:
            status_code, retry_after = _http_failure_info(exc)
            if status_code is None:
                raise
            raise ReplicateAPIError(
                status_code, str(exc), retry_after=retry_after
            ) from exc


_ROUTING_KEYS = frozenset({"model", "model_name", "version", "input", "inputs"})


def _request_field(request: Any, *names: str) -> Any:
    if isinstance(request, Mapping):
        for name in names:
            if name in request:
                return request[name]
        return None
    for name in names:
        if hasattr(request, name):
            return getattr(request, name)
    return None


def _derive_inputs(request: Any) -> dict[str, Any]:
    """Treat any non-routing fields on the request as Replicate inputs."""
    if isinstance(request, Mapping):
        return {k: v for k, v in request.items() if k not in _ROUTING_KEYS}
    return {}


def _prediction_error_detail(prediction: Any) -> str:
    error = getattr(prediction, "error", None)
    return f": {error}" if error else ""


def _http_failure_info(exc: BaseException) -> tuple[int | None, float | None]:
    """Pull a status code + Retry-After hint off an HTTP-style exception.

    Recognizes both httpx-style (``exc.response.status_code``) and
    replicate-SDK-style (``exc.status``) failure objects.
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    status_code = getattr(response, "status_code", None) if response is not None else None
    if not isinstance(status_code, int):
        candidate = getattr(exc, "status", None)
        status_code = candidate if isinstance(candidate, int) else None
    if status_code is None:
        return None, None
    return status_code, _retry_after_seconds(headers)


def _write_payload_to_temp_file(payload: bytes, api_request_id: str) -> Path:
    safe_id = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-"
        for char in api_request_id
    )
    filename = f"{safe_id or 'replicate-generation'}.wav"
    directory = Path(tempfile.gettempdir()) / "senseweave-generation"
    directory.mkdir(parents=True, exist_ok=True)
    audio_path = directory / filename
    audio_path.write_bytes(payload)
    return audio_path


def _wav_metadata(audio_path: Path) -> tuple[int, float]:
    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            sample_rate = int(wav_file.getframerate())
            frames = int(wav_file.getnframes())
    except (EOFError, OSError, wave.Error):
        return 0, 0.0
    if sample_rate <= 0:
        return 0, 0.0
    return sample_rate, float(frames / sample_rate)


def _estimate_cost_usd(
    request: GenerationRequest, duration_actual_sec: float
) -> float:
    rate = PER_SECOND_USD.get(str(request.model), max(PER_SECOND_USD.values()))
    duration = duration_actual_sec if duration_actual_sec > 0.0 else request.duration_sec
    return float(rate * duration * OVERHEAD_FACTOR)
