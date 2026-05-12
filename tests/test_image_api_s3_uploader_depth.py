"""Depth-2 tests for image_api.s3_uploader [frac-0049]."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import sdp.fractal as fractal

from cypherclaw.image_api.config import Settings
from cypherclaw.image_api.s3_uploader import (
    CONTENT_TYPE_BY_EXTENSION,
    DEFAULT_CACHE_CONTROL,
    DEFAULT_CONTENT_TYPE,
    UploadReport,
    UploadResult,
    build_upload_report,
    categorize_upload_size,
    guess_content_type,
    summarize_upload,
    summarize_upload_report,
    upload_image,
)


S3_UPLOADER_MODULE_PATH = Path("src/cypherclaw/image_api/s3_uploader.py")


@dataclass
class _FakeS3Client:
    calls: list[dict] = field(default_factory=list)

    def put_object(self, **kwargs: object) -> dict:
        self.calls.append(kwargs)
        return {"ETag": '"etag"'}


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "s3_bucket": "test-bucket",
        "s3_region": "us-west-2",
        "s3_key_prefix": "jobs",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _result(
    *,
    bucket: str = "test-bucket",
    key: str = "jobs/job/file.png",
    url: str = "https://test-bucket.s3.us-west-2.amazonaws.com/jobs/job/file.png",
    bytes_uploaded: int = 0,
) -> UploadResult:
    return UploadResult(bucket=bucket, key=key, url=url, bytes_uploaded=bytes_uploaded)


def test_guess_content_type_classifies_known_and_unknown() -> None:
    assert guess_content_type("hero.png") == "image/png"
    assert guess_content_type("hero.PNG") == "image/png"
    assert guess_content_type("photo.jpg") == "image/jpeg"
    assert guess_content_type("photo.jpeg") == "image/jpeg"
    assert guess_content_type("animation.gif") == "image/gif"
    assert guess_content_type("modern.webp") == "image/webp"
    assert guess_content_type("legacy.tiff") == DEFAULT_CONTENT_TYPE
    assert guess_content_type("nodot") == DEFAULT_CONTENT_TYPE
    assert CONTENT_TYPE_BY_EXTENSION[".png"] == "image/png"


def test_build_upload_report_aggregates_results() -> None:
    results = [
        _result(key="jobs/j/a.png", bytes_uploaded=10),
        _result(key="jobs/j/b.png", bytes_uploaded=2048),
        _result(key="jobs/j/c.png", bytes_uploaded=200_000),
    ]

    report = build_upload_report(results)

    assert isinstance(report, UploadReport)
    assert report.bucket == "test-bucket"
    assert report.object_count == 3
    assert report.total_bytes == 10 + 2048 + 200_000
    assert report.keys == ("jobs/j/a.png", "jobs/j/b.png", "jobs/j/c.png")
    assert report.urls == tuple(r.url for r in results)


def test_build_upload_report_handles_empty_iterable() -> None:
    report = build_upload_report(iter(()))

    assert isinstance(report, UploadReport)
    assert report.bucket == ""
    assert report.object_count == 0
    assert report.total_bytes == 0
    assert report.keys == ()
    assert report.urls == ()


def test_categorize_upload_size_thresholds() -> None:
    assert categorize_upload_size(_result(bytes_uploaded=0)) == "empty"
    assert categorize_upload_size(_result(bytes_uploaded=1)) == "small"
    assert categorize_upload_size(_result(bytes_uploaded=64 * 1024 - 1)) == "small"
    assert categorize_upload_size(_result(bytes_uploaded=64 * 1024)) == "medium"
    assert categorize_upload_size(_result(bytes_uploaded=1024 * 1024 - 1)) == "medium"
    assert categorize_upload_size(_result(bytes_uploaded=1024 * 1024)) == "large"
    assert categorize_upload_size(_result(bytes_uploaded=10 * 1024 * 1024)) == "large"


def test_summarize_helpers_are_json_safe() -> None:
    one = _result(key="jobs/j/a.png", bytes_uploaded=4096)
    summary = summarize_upload(one)
    json.dumps(summary)

    assert summary["bucket"] == "test-bucket"
    assert summary["key"] == "jobs/j/a.png"
    assert summary["url"] == one.url
    assert summary["bytes_uploaded"] == 4096
    assert summary["size_category"] == "small"

    report = build_upload_report(
        [
            _result(key="jobs/j/a.png", bytes_uploaded=4096),
            _result(key="jobs/j/b.png", bytes_uploaded=2 * 1024 * 1024),
        ]
    )
    report_summary = summarize_upload_report(report)
    json.dumps(report_summary)

    assert report_summary["bucket"] == "test-bucket"
    assert report_summary["object_count"] == 2
    assert report_summary["total_bytes"] == 4096 + 2 * 1024 * 1024
    assert report_summary["keys"] == ["jobs/j/a.png", "jobs/j/b.png"]
    assert isinstance(report_summary["keys"], list)
    assert isinstance(report_summary["urls"], list)


def test_upload_image_uses_default_cache_control() -> None:
    client = _FakeS3Client()

    result = upload_image(
        job_id="job",
        filename="hero.png",
        image_bytes=b"PAYLOAD",
        content_type="image/png",
        s=_settings(),
        client=client,
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["CacheControl"] == DEFAULT_CACHE_CONTROL
    assert call["Bucket"] == "test-bucket"
    assert call["Key"] == "jobs/job/hero.png"
    assert call["Body"] == b"PAYLOAD"
    assert call["ContentType"] == "image/png"
    assert result.bytes_uploaded == len(b"PAYLOAD")


def test_s3_uploader_module_reaches_depth_two() -> None:
    module = fractal.classify_depth(S3_UPLOADER_MODULE_PATH)
    assert module.depth >= 2, (
        f"expected s3_uploader.py depth >= 2, got {module.depth}: {module.reason}"
    )
