"""Retry-loop tests for ReplicateClient (T-002 / CCG-011).

These cover only the retry surface — the full ReplicateClient.generate
body lands with T-001. Tests use httpx-style mock responses (an object
with ``status_code`` and ``headers``) and inject a fake sleep so call
counts and delays can be asserted without real waits.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.client_replicate import (  # noqa: E402
    BACKOFF_SCHEDULE,
    MAX_RETRIES,
    GenerationError,
    ReplicateAPIError,
    ReplicateClient,
    raise_for_response,
)


def _fake_response(status_code: int, retry_after: str | None = None) -> SimpleNamespace:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return SimpleNamespace(status_code=status_code, headers=headers)


class _Recorder:
    """Records sleep delays and submission attempts."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []
        self.attempts: int = 0


def _make_client(recorder: _Recorder) -> ReplicateClient:
    return ReplicateClient(api_token="test", sleep=recorder.sleeps.append)


# ── happy path ───────────────────────────────────────────────────────


def test_submit_with_retry_returns_on_first_success() -> None:
    rec = _Recorder()
    client = _make_client(rec)

    def submit() -> str:
        rec.attempts += 1
        return "ok"

    assert client._submit_with_retry(submit) == "ok"
    assert rec.attempts == 1
    assert rec.sleeps == []


# ── retry-eligible status codes ──────────────────────────────────────


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retries_then_succeeds(status: int) -> None:
    rec = _Recorder()
    client = _make_client(rec)

    def submit() -> str:
        rec.attempts += 1
        if rec.attempts == 1:
            raise ReplicateAPIError(status)
        return "ok"

    assert client._submit_with_retry(submit) == "ok"
    assert rec.attempts == 2
    assert rec.sleeps == [BACKOFF_SCHEDULE[0]]


def test_three_retries_then_raises_generation_error() -> None:
    rec = _Recorder()
    client = _make_client(rec)

    def submit() -> str:
        rec.attempts += 1
        raise ReplicateAPIError(503)

    with pytest.raises(GenerationError) as info:
        client._submit_with_retry(submit)

    assert rec.attempts == MAX_RETRIES + 1 == 4
    assert rec.sleeps == list(BACKOFF_SCHEDULE) == [5.0, 30.0, 300.0]
    assert isinstance(info.value.__cause__, ReplicateAPIError)
    assert info.value.__cause__.status_code == 503


# ── non-retryable status codes ───────────────────────────────────────


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_non_429_4xx_does_not_retry(status: int) -> None:
    rec = _Recorder()
    client = _make_client(rec)

    def submit() -> str:
        rec.attempts += 1
        raise ReplicateAPIError(status)

    with pytest.raises(GenerationError) as info:
        client._submit_with_retry(submit)

    assert rec.attempts == 1
    assert rec.sleeps == []
    assert info.value.__cause__.status_code == status  # type: ignore[union-attr]


def test_non_replicate_exception_propagates_without_retry() -> None:
    rec = _Recorder()
    client = _make_client(rec)

    def submit() -> str:
        rec.attempts += 1
        raise RuntimeError("network down")

    with pytest.raises(RuntimeError, match="network down"):
        client._submit_with_retry(submit)

    assert rec.attempts == 1
    assert rec.sleeps == []


# ── Retry-After honoring ─────────────────────────────────────────────


def test_retry_after_overrides_when_larger_than_scheduled() -> None:
    rec = _Recorder()
    client = _make_client(rec)
    attempts: list[int] = []

    def submit() -> str:
        attempts.append(len(attempts) + 1)
        if len(attempts) == 1:
            raise ReplicateAPIError(429, retry_after=60.0)
        return "ok"

    assert client._submit_with_retry(submit) == "ok"
    # scheduled[0] = 5s, header says 60s -> honor 60s
    assert rec.sleeps == [60.0]


def test_retry_after_ignored_when_smaller_than_scheduled() -> None:
    rec = _Recorder()
    client = _make_client(rec)
    n: list[int] = []

    def submit() -> str:
        n.append(1)
        if len(n) == 1:
            raise ReplicateAPIError(429, retry_after=1.0)
        return "ok"

    assert client._submit_with_retry(submit) == "ok"
    # header says 1s but scheduled[0] is 5s -> use 5s
    assert rec.sleeps == [BACKOFF_SCHEDULE[0]]


def test_retry_after_applied_per_attempt() -> None:
    """A late-attempt Retry-After larger than its scheduled slot wins."""
    rec = _Recorder()
    client = _make_client(rec)
    n: list[int] = []
    # attempt 1 -> 429 retry_after=2 (smaller than 5)  -> sleep 5
    # attempt 2 -> 503 retry_after=600 (larger than 30) -> sleep 600
    # attempt 3 -> success
    plan = [
        ReplicateAPIError(429, retry_after=2.0),
        ReplicateAPIError(503, retry_after=600.0),
        None,
    ]

    def submit() -> str:
        n.append(1)
        item = plan[len(n) - 1]
        if item is None:
            return "ok"
        raise item

    assert client._submit_with_retry(submit) == "ok"
    assert rec.sleeps == [BACKOFF_SCHEDULE[0], 600.0]


# ── raise_for_response helper (httpx-style mocks) ────────────────────


def test_raise_for_response_passes_on_2xx() -> None:
    raise_for_response(_fake_response(200))
    raise_for_response(_fake_response(204))


@pytest.mark.parametrize("status", [400, 429, 500, 503])
def test_raise_for_response_raises_on_non_2xx(status: int) -> None:
    with pytest.raises(ReplicateAPIError) as info:
        raise_for_response(_fake_response(status))
    assert info.value.status_code == status
    assert info.value.retry_after is None


def test_raise_for_response_parses_retry_after_seconds() -> None:
    with pytest.raises(ReplicateAPIError) as info:
        raise_for_response(_fake_response(429, retry_after="42"))
    assert info.value.retry_after == 42.0


def test_raise_for_response_ignores_unparseable_retry_after() -> None:
    # HTTP-date form is intentionally not supported in the seconds parser.
    with pytest.raises(ReplicateAPIError) as info:
        raise_for_response(_fake_response(429, retry_after="Wed, 21 Oct 2026 07:28:00 GMT"))
    assert info.value.retry_after is None


# ── end-to-end integration through generate() with mocked submit ─────


def test_generate_uses_retry_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _Recorder()
    client = _make_client(rec)
    calls: list[int] = []
    completed = SimpleNamespace(id="prediction-id", status="succeeded", output=b"")

    def fake_submit(_request: object) -> object:
        calls.append(1)
        if len(calls) < 3:
            raise ReplicateAPIError(429)
        return completed

    monkeypatch.setattr(client, "_submit_prediction", fake_submit)
    monkeypatch.setattr(client, "_poll_prediction", lambda pred: pred)
    monkeypatch.setattr(client, "_download_output", lambda pred: b"")

    result = client.generate(request={"model": "m"})
    assert result["prediction_id"] == "prediction-id"
    assert len(calls) == 3
    assert rec.sleeps == [BACKOFF_SCHEDULE[0], BACKOFF_SCHEDULE[1]]


# ── _submit_prediction (T-001) ───────────────────────────────────────


class _FakePredictions:
    def __init__(self, response: object | None = None, error: Exception | None = None):
        self.calls: list[dict[str, object]] = []
        self._response = response
        self._error = error

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class _FakeReplicateModule:
    def __init__(self, predictions: _FakePredictions):
        self.predictions = predictions
        self.client_tokens: list[str | None] = []

    def Client(self, api_token: str | None = None) -> "_FakeReplicateModule":  # noqa: N802
        self.client_tokens.append(api_token)
        return self


def _patch_replicate(
    monkeypatch: pytest.MonkeyPatch, predictions: _FakePredictions
) -> _FakeReplicateModule:
    from senseweave.generation import client_replicate as module

    fake = _FakeReplicateModule(predictions)
    monkeypatch.setattr(module, "replicate", fake)
    return fake


def test_submit_prediction_uses_model_and_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predictions = _FakePredictions(response=SimpleNamespace(id="pred-123"))
    fake = _patch_replicate(monkeypatch, predictions)
    client = ReplicateClient(api_token="test")

    request = {
        "model": "meta/musicgen",
        "prompt": "ambient pad",
        "duration_sec": 30.0,
    }
    result = client._submit_prediction(request)

    assert getattr(result, "id", None) == "pred-123"
    assert predictions.calls == [
        {
            "model": "meta/musicgen",
            "input": {"prompt": "ambient pad", "duration_sec": 30.0},
        }
    ]
    assert fake.client_tokens == ["test"]


def test_submit_prediction_prefers_version_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predictions = _FakePredictions(response=object())
    _patch_replicate(monkeypatch, predictions)
    client = ReplicateClient(api_token="t")

    client._submit_prediction(
        {"model": "ignored", "version": "abc123", "input": {"prompt": "p"}}
    )

    assert predictions.calls == [{"version": "abc123", "input": {"prompt": "p"}}]


def test_submit_prediction_maps_http_status_to_replicate_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(status_code=503, headers={"Retry-After": "12"})
    http_error = type("HTTPStatusError", (Exception,), {})()
    http_error.response = response  # type: ignore[attr-defined]
    predictions = _FakePredictions(error=http_error)
    _patch_replicate(monkeypatch, predictions)
    client = ReplicateClient(api_token="t")

    with pytest.raises(ReplicateAPIError) as info:
        client._submit_prediction({"model": "m", "prompt": "p"})

    assert info.value.status_code == 503
    assert info.value.retry_after == 12.0


def test_submit_prediction_maps_replicate_status_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_error = type("ReplicateError", (Exception,), {})()
    sdk_error.status = 429  # type: ignore[attr-defined]
    predictions = _FakePredictions(error=sdk_error)
    _patch_replicate(monkeypatch, predictions)
    client = ReplicateClient(api_token="t")

    with pytest.raises(ReplicateAPIError) as info:
        client._submit_prediction({"model": "m", "prompt": "p"})

    assert info.value.status_code == 429
    assert info.value.retry_after is None


def test_submit_prediction_propagates_non_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predictions = _FakePredictions(error=RuntimeError("network down"))
    _patch_replicate(monkeypatch, predictions)
    client = ReplicateClient(api_token="t")

    with pytest.raises(RuntimeError, match="network down"):
        client._submit_prediction({"model": "m", "prompt": "p"})


def test_submit_prediction_requires_model_or_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predictions = _FakePredictions(response=object())
    _patch_replicate(monkeypatch, predictions)
    client = ReplicateClient(api_token="t")

    with pytest.raises(GenerationError, match="missing both 'model' and 'version'"):
        client._submit_prediction({"prompt": "p"})

    assert predictions.calls == []


def test_submit_prediction_raises_when_sdk_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from senseweave.generation import client_replicate as module

    monkeypatch.setattr(module, "replicate", None)
    client = ReplicateClient(api_token="t")

    with pytest.raises(GenerationError, match="replicate SDK not installed"):
        client._submit_prediction({"model": "m", "prompt": "p"})


def test_submit_prediction_retry_layer_engages_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: HTTP 503 from the SDK retries via the existing loop."""
    response = SimpleNamespace(status_code=503, headers={})
    http_error = type("HTTPStatusError", (Exception,), {})()
    http_error.response = response  # type: ignore[attr-defined]

    call_count = {"n": 0}
    success = SimpleNamespace(id="ok", status="succeeded", output=b"")

    class _FlakyPredictions:
        def create(self, **_kwargs: object) -> object:
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise http_error
            return success

    _patch_replicate(monkeypatch, _FlakyPredictions())  # type: ignore[arg-type]
    rec = _Recorder()
    client = _make_client(rec)

    result = client.generate({"model": "m", "prompt": "p"})

    assert result["prediction_id"] == "ok"
    assert call_count["n"] == 2
    assert rec.sleeps == [BACKOFF_SCHEDULE[0]]


# ── _poll_prediction (T-001) ─────────────────────────────────────────


class _PollingPrediction:
    def __init__(self, statuses: list[str], error: str | None = None) -> None:
        self._statuses = statuses
        self._index = 0
        self.status = statuses[0]
        self.error = error
        self.reloads = 0

    def reload(self) -> "_PollingPrediction":
        self.reloads += 1
        self._index = min(self._index + 1, len(self._statuses) - 1)
        self.status = self._statuses[self._index]
        return self


def test_poll_prediction_returns_when_succeeded() -> None:
    rec = _Recorder()
    client = _make_client(rec)
    prediction = _PollingPrediction(["starting", "processing", "succeeded"])

    result = client._poll_prediction(prediction)

    assert result is prediction
    assert prediction.reloads == 2
    assert rec.sleeps == [1.0, 1.0]


@pytest.mark.parametrize("status", ["failed", "canceled"])
def test_poll_prediction_raises_on_terminal_failure(status: str) -> None:
    rec = _Recorder()
    client = _make_client(rec)
    prediction = _PollingPrediction(["processing", status], error="render failed")

    with pytest.raises(GenerationError, match=rf"{status}.*render failed"):
        client._poll_prediction(prediction)

    assert prediction.reloads == 1
    assert rec.sleeps == [1.0]


def test_poll_prediction_returns_immediately_when_already_succeeded() -> None:
    rec = _Recorder()
    client = _make_client(rec)
    prediction = _PollingPrediction(["succeeded"])

    result = client._poll_prediction(prediction)

    assert result is prediction
    assert prediction.reloads == 0
    assert rec.sleeps == []


def test_poll_prediction_raises_on_timeout() -> None:
    rec = _Recorder()
    ticks = iter([0.0, 0.0, 0.25, 0.5])
    client = ReplicateClient(
        api_token="test",
        timeout_sec=0.5,
        sleep=rec.sleeps.append,
        clock=lambda: next(ticks),
    )
    prediction = _PollingPrediction(["starting", "processing", "processing"])

    with pytest.raises(GenerationError, match="timed out after 0.5s"):
        client._poll_prediction(prediction)

    assert prediction.reloads == 2
    assert rec.sleeps == [0.5, 0.25]


# ── _download_output (T-001) ─────────────────────────────────────────


class _FakeReader:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.reads = 0

    def read(self) -> bytes:
        self.reads += 1
        return self._payload


def test_download_output_handles_single_url(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ReplicateClient(api_token="t")
    fetched: list[str] = []

    def fake_fetch(url: str) -> bytes:
        fetched.append(url)
        return b"WAVDATA"

    monkeypatch.setattr(client, "_fetch_bytes", fake_fetch)
    prediction = SimpleNamespace(output="https://example.com/out.wav")

    assert client._download_output(prediction) == b"WAVDATA"
    assert fetched == ["https://example.com/out.wav"]


def test_download_output_concatenates_url_list(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ReplicateClient(api_token="t")
    monkeypatch.setattr(
        client, "_fetch_bytes", lambda url: f"<{url}>".encode()
    )
    prediction = SimpleNamespace(output=["u1", "u2"])

    assert client._download_output(prediction) == b"<u1><u2>"


def test_download_output_handles_file_output_reader() -> None:
    client = ReplicateClient(api_token="t")
    reader = _FakeReader(b"PAYLOAD")
    prediction = SimpleNamespace(output=reader)

    assert client._download_output(prediction) == b"PAYLOAD"
    assert reader.reads == 1


def test_download_output_handles_inline_bytes() -> None:
    client = ReplicateClient(api_token="t")
    prediction = SimpleNamespace(output=b"INLINE")

    assert client._download_output(prediction) == b"INLINE"


def test_download_output_raises_when_output_missing() -> None:
    client = ReplicateClient(api_token="t")
    prediction = SimpleNamespace(output=None)

    with pytest.raises(GenerationError, match="no output"):
        client._download_output(prediction)


def test_download_output_raises_on_unsupported_type() -> None:
    client = ReplicateClient(api_token="t")
    prediction = SimpleNamespace(output=12345)

    with pytest.raises(GenerationError, match="Unsupported"):
        client._download_output(prediction)


# ── generate() end-to-end wiring (T-001) ─────────────────────────────


class _FakeDownloadResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeDownloadResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_generate_with_fake_sdk_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from senseweave.generation import client_replicate as module

    rec = _Recorder()
    ticks = iter([10.0, 10.0, 10.0, 12.5])
    prediction = _PollingPrediction(["processing", "succeeded"])
    prediction.id = "pred-sdk-ok"  # type: ignore[attr-defined]
    prediction.output = "https://example.com/generated.wav"  # type: ignore[attr-defined]
    predictions = _FakePredictions(response=prediction)
    fake = _patch_replicate(monkeypatch, predictions)
    downloads: list[tuple[str, float]] = []

    def fake_urlopen(url: str, timeout: float) -> _FakeDownloadResponse:
        downloads.append((url, timeout))
        return _FakeDownloadResponse(b"SDK-AUDIO")

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    client = ReplicateClient(
        api_token="test-token",
        timeout_sec=9.0,
        sleep=rec.sleeps.append,
        clock=lambda: next(ticks),
    )

    result = client.generate({"model": "musicgen-medium", "prompt": "p"})

    assert result == {
        "audio_bytes": b"SDK-AUDIO",
        "model_used": "musicgen-medium",
        "prediction_id": "pred-sdk-ok",
        "latency_ms": 2500,
    }
    assert predictions.calls == [
        {"model": "musicgen-medium", "input": {"prompt": "p"}}
    ]
    assert fake.client_tokens == ["test-token"]
    assert prediction.reloads == 1
    assert rec.sleeps == [1.0]
    assert downloads == [("https://example.com/generated.wav", 9.0)]


def test_generate_with_fake_sdk_raises_on_polling_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rec = _Recorder()
    ticks = iter([0.0, 0.0, 0.0, 0.25, 0.5])
    prediction = _PollingPrediction(["starting", "processing", "processing"])
    predictions = _FakePredictions(response=prediction)
    _patch_replicate(monkeypatch, predictions)
    client = ReplicateClient(
        api_token="test-token",
        timeout_sec=0.5,
        sleep=rec.sleeps.append,
        clock=lambda: next(ticks),
    )

    with pytest.raises(GenerationError, match="timed out after 0.5s"):
        client.generate({"model": "musicgen-medium", "prompt": "p"})

    assert predictions.calls == [
        {"model": "musicgen-medium", "input": {"prompt": "p"}}
    ]
    assert prediction.reloads == 2
    assert rec.sleeps == [0.5, 0.25]


def test_generate_with_fake_sdk_raises_on_terminal_failure_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rec = _Recorder()
    ticks = iter([0.0, 0.0, 0.0])
    prediction = _PollingPrediction(["processing", "failed"], error="render failed")
    predictions = _FakePredictions(response=prediction)
    _patch_replicate(monkeypatch, predictions)
    client = ReplicateClient(
        api_token="test-token",
        sleep=rec.sleeps.append,
        clock=lambda: next(ticks),
    )

    with pytest.raises(GenerationError, match="failed.*render failed"):
        client.generate({"model": "musicgen-medium", "prompt": "p"})

    assert predictions.calls == [
        {"model": "musicgen-medium", "input": {"prompt": "p"}}
    ]
    assert prediction.reloads == 1
    assert rec.sleeps == [1.0]


def test_generate_with_fake_sdk_raises_on_download_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from senseweave.generation import client_replicate as module

    ticks = iter([0.0, 0.0])
    prediction = SimpleNamespace(
        id="pred-download-error",
        status="succeeded",
        output="https://example.com/broken.wav",
    )
    predictions = _FakePredictions(response=prediction)
    _patch_replicate(monkeypatch, predictions)

    def fail_urlopen(url: str, timeout: float) -> object:
        assert url == "https://example.com/broken.wav"
        assert timeout == 120.0
        raise OSError("download refused")

    monkeypatch.setattr(module.urllib.request, "urlopen", fail_urlopen)
    client = ReplicateClient(api_token="test-token", clock=lambda: next(ticks))

    with pytest.raises(GenerationError, match="download failed.*download refused") as info:
        client.generate({"model": "musicgen-medium", "prompt": "p"})

    assert isinstance(info.value.__cause__, OSError)
    assert predictions.calls == [
        {"model": "musicgen-medium", "input": {"prompt": "p"}}
    ]


def test_generate_wires_submit_poll_download(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _Recorder()
    # clock is called at: generate-start, poll-deadline, generate-end
    ticks = iter([10.0, 10.0, 12.5])
    client = ReplicateClient(
        api_token="t", sleep=rec.sleeps.append, clock=lambda: next(ticks)
    )
    completed = _PollingPrediction(["succeeded"])
    completed.id = "pred-xyz"  # type: ignore[attr-defined]
    completed.output = "https://example.com/a.wav"  # type: ignore[attr-defined]

    monkeypatch.setattr(client, "_submit_prediction", lambda req: completed)
    monkeypatch.setattr(client, "_fetch_bytes", lambda url: b"AUDIO")

    result = client.generate({"model": "musicgen-medium", "prompt": "p"})

    assert result == {
        "audio_bytes": b"AUDIO",
        "model_used": "musicgen-medium",
        "prediction_id": "pred-xyz",
        "latency_ms": 2500,
    }


def test_generate_prefers_version_for_model_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ReplicateClient(api_token="t", clock=lambda: 0.0)
    completed = SimpleNamespace(id="p1", status="succeeded", output=b"x")
    monkeypatch.setattr(client, "_submit_prediction", lambda req: completed)
    monkeypatch.setattr(client, "_poll_prediction", lambda pred: pred)

    result = client.generate({"model": "ignored", "version": "abc123", "prompt": "p"})

    assert result["model_used"] == "abc123"
