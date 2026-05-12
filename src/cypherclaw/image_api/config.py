"""Environment-loaded configuration for the image API."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """All knobs come from environment variables. Defaults match the
    contract in `specs/external/cypherclaw-image-contract.md`."""

    # S3 destination
    s3_bucket: str = "ctmarketing-cypherclaw-images"
    s3_region: str = "us-west-2"
    s3_key_prefix: str = "jobs"

    # AWS credentials are read by boto3 from env/IAM/etc — not injected here.

    # Gemini model. CT Marketing may pass `model:` in spec_yaml to override.
    gemini_default_model: str = "gemini-3-pro-image-preview"
    gemini_api_key_env: str = "GEMINI_API_KEY"

    # SQLite job state lives outside the package so it survives upgrades.
    jobs_db_path: str = "/home/user/cypherclaw-data/image_jobs.db"

    # HTTP server bind
    listen_host: str = "0.0.0.0"
    listen_port: int = 9000

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            s3_bucket=os.environ.get("CYPHERCLAW_IMAGE_S3_BUCKET", cls.s3_bucket),
            s3_region=os.environ.get("CYPHERCLAW_IMAGE_S3_REGION", cls.s3_region),
            s3_key_prefix=os.environ.get("CYPHERCLAW_IMAGE_S3_PREFIX", cls.s3_key_prefix),
            gemini_default_model=os.environ.get("CYPHERCLAW_IMAGE_MODEL", cls.gemini_default_model),
            gemini_api_key_env=os.environ.get("CYPHERCLAW_GEMINI_API_KEY_ENV", cls.gemini_api_key_env),
            jobs_db_path=os.environ.get("CYPHERCLAW_IMAGE_JOBS_DB", cls.jobs_db_path),
            listen_host=os.environ.get("CYPHERCLAW_IMAGE_LISTEN_HOST", cls.listen_host),
            listen_port=int(os.environ.get("CYPHERCLAW_IMAGE_LISTEN_PORT", cls.listen_port)),
        )

    def s3_object_url(self, key: str) -> str:
        """Build the direct-S3 public URL for an object key."""
        return f"https://{self.s3_bucket}.s3.{self.s3_region}.amazonaws.com/{key}"

    def s3_object_key(self, job_id: str, filename: str) -> str:
        return f"{self.s3_key_prefix}/{job_id}/{filename}"


settings = Settings.from_env()
