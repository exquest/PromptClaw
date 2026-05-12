"""Tests for image_api.s3_uploader — uses an injected fake client (no boto3)."""
from __future__ import annotations

from dataclasses import dataclass, field

from cypherclaw.image_api.config import Settings
from cypherclaw.image_api.s3_uploader import (
    build_upload_report,
    categorize_upload_size,
    guess_content_type,
    summarize_upload,
    summarize_upload_report,
    upload_image,
)


@dataclass
class FakeS3Client:
    """Records put_object calls. Subset of boto3.client('s3') we need."""

    calls: list[dict] = field(default_factory=list)

    def put_object(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"ETag": '"etag"'}


def _settings(**overrides) -> Settings:
    base = dict(
        s3_bucket="test-bucket",
        s3_region="us-west-2",
        s3_key_prefix="jobs",
    )
    base.update(overrides)
    return Settings(**base)


class TestUploadImage:
    def test_url_format_is_direct_s3(self):
        client = FakeS3Client()
        result = upload_image(
            job_id="abc-123",
            filename="hero.jpg",
            image_bytes=b"\x89PNG\r\n\x1a\n",
            content_type="image/png",
            s=_settings(),
            client=client,
        )
        assert (
            result.url
            == "https://test-bucket.s3.us-west-2.amazonaws.com/jobs/abc-123/hero.jpg"
        )
        assert result.bucket == "test-bucket"
        assert result.key == "jobs/abc-123/hero.jpg"
        assert result.bytes_uploaded == 8

    def test_put_object_call_args(self):
        client = FakeS3Client()
        upload_image(
            job_id="job1",
            filename="image.png",
            image_bytes=b"PAYLOAD",
            content_type="image/png",
            s=_settings(),
            client=client,
        )
        assert len(client.calls) == 1
        call = client.calls[0]
        assert call["Bucket"] == "test-bucket"
        assert call["Key"] == "jobs/job1/image.png"
        assert call["Body"] == b"PAYLOAD"
        assert call["ContentType"] == "image/png"
        assert "max-age" in call["CacheControl"]

    def test_alt_region_and_prefix(self):
        client = FakeS3Client()
        result = upload_image(
            job_id="J",
            filename="f.jpg",
            image_bytes=b"x",
            s=_settings(s3_bucket="other", s3_region="eu-west-1", s3_key_prefix="img"),
            client=client,
        )
        assert result.url == "https://other.s3.eu-west-1.amazonaws.com/img/J/f.jpg"

    def test_default_content_type_is_png(self):
        client = FakeS3Client()
        upload_image(
            job_id="j",
            filename="f.png",
            image_bytes=b"x",
            s=_settings(),
            client=client,
        )
        assert client.calls[0]["ContentType"] == "image/png"


class TestImageApiS3UploaderEndToEnd:
    def test_end_to_end_upload_flow(self):
        client = FakeS3Client()
        settings = _settings()
        
        # 1. Given an image file, guess its content type
        filename = "profile.webp"
        content_type = guess_content_type(filename)
        assert content_type == "image/webp"
        
        # 2. Upload the image
        image_bytes = b"fake-webp-data-which-is-small"
        result = upload_image(
            job_id="job-end-to-end",
            filename=filename,
            image_bytes=image_bytes,
            content_type=content_type,
            s=settings,
            client=client,
        )
        
        # Verify direct upload basics
        assert result.bucket == "test-bucket"
        assert result.key == "jobs/job-end-to-end/profile.webp"
        assert result.bytes_uploaded == len(image_bytes)
        
        # 3. Categorize size and summarize upload
        size_category = categorize_upload_size(result)
        assert size_category == "small"
        
        summary = summarize_upload(result)
        assert summary["size_category"] == "small"
        assert summary["url"] == result.url
        
        # 4. Build a report from the results (e.g., a batch)
        report = build_upload_report([result])
        assert report.object_count == 1
        assert report.total_bytes == len(image_bytes)
        
        # 5. Summarize the report into a JSON-safe dict
        report_summary = summarize_upload_report(report)
        assert report_summary["object_count"] == 1
        assert report_summary["urls"] == [result.url]

