"""S3 upload helper. Returns a public direct-S3 URL for the uploaded object."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Optional, Protocol

from .config import Settings, settings as default_settings


DEFAULT_CACHE_CONTROL = "public, max-age=31536000, immutable"
DEFAULT_CONTENT_TYPE = "application/octet-stream"
CONTENT_TYPE_BY_EXTENSION: Mapping[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class S3ClientProtocol(Protocol):
    """Subset of boto3.client('s3') used here. Lets tests inject `moto`."""

    def put_object(self, **kwargs) -> dict: ...


@dataclass(frozen=True)
class UploadResult:
    """Successful upload."""

    bucket: str
    key: str
    url: str
    bytes_uploaded: int


@dataclass(frozen=True)
class UploadReport:
    """Aggregate of multiple `UploadResult` records for one batch."""

    bucket: str
    object_count: int
    total_bytes: int
    keys: tuple[str, ...]
    urls: tuple[str, ...]


def _build_client(s: Settings) -> S3ClientProtocol:
    """Build a boto3 S3 client. Imported lazily so tests can avoid boto3
    when they inject their own client."""
    import boto3  # type: ignore[import-untyped]  # noqa: WPS433

    return boto3.client("s3", region_name=s.s3_region)


def guess_content_type(filename: str) -> str:
    """Map a filename's trailing extension to a canonical MIME type."""
    if "." not in filename:
        return DEFAULT_CONTENT_TYPE
    suffix = "." + filename.rsplit(".", 1)[1].lower()
    return CONTENT_TYPE_BY_EXTENSION.get(suffix, DEFAULT_CONTENT_TYPE)


def categorize_upload_size(result: UploadResult) -> str:
    """Coarse byte-size band for `result`: empty / small / medium / large."""
    n = result.bytes_uploaded
    if n <= 0:
        return "empty"
    if n < 64 * 1024:
        return "small"
    if n < 1024 * 1024:
        return "medium"
    return "large"


def build_upload_report(results: Iterable[UploadResult]) -> UploadReport:
    """Aggregate `results` (consumed once) into a typed `UploadReport`."""
    items = tuple(results)
    if not items:
        return UploadReport(
            bucket="", object_count=0, total_bytes=0, keys=(), urls=()
        )
    return UploadReport(
        bucket=items[0].bucket,
        object_count=len(items),
        total_bytes=sum(r.bytes_uploaded for r in items),
        keys=tuple(r.key for r in items),
        urls=tuple(r.url for r in items),
    )


def summarize_upload(result: UploadResult) -> dict[str, object]:
    """JSON-safe summary for one `UploadResult`, including size band."""
    return {
        "bucket": result.bucket,
        "key": result.key,
        "url": result.url,
        "bytes_uploaded": result.bytes_uploaded,
        "size_category": categorize_upload_size(result),
    }


def summarize_upload_report(report: UploadReport) -> dict[str, object]:
    """JSON-safe summary for an `UploadReport` (lists, not tuples)."""
    return {
        "bucket": report.bucket,
        "object_count": report.object_count,
        "total_bytes": report.total_bytes,
        "keys": list(report.keys),
        "urls": list(report.urls),
    }


def upload_image(
    *,
    job_id: str,
    filename: str,
    image_bytes: bytes,
    content_type: str = "image/png",
    s: Optional[Settings] = None,
    client: Optional[S3ClientProtocol] = None,
) -> UploadResult:
    """Upload `image_bytes` to S3 under jobs/{job_id}/{filename}.

    Returns the public HTTPS URL CT Marketing will fetch. Raises on
    boto3 errors (caller wraps into a `failed` job status)."""
    s = s or default_settings
    cli = client or _build_client(s)
    key = s.s3_object_key(job_id, filename)

    cli.put_object(
        Bucket=s.s3_bucket,
        Key=key,
        Body=image_bytes,
        ContentType=content_type,
        CacheControl=DEFAULT_CACHE_CONTROL,
    )

    return UploadResult(
        bucket=s.s3_bucket,
        key=key,
        url=s.s3_object_url(key),
        bytes_uploaded=len(image_bytes),
    )
