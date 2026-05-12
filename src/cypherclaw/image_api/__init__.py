"""CypherClaw image-generation HTTP API.

Implements the `cypherclaw-image-contract.md` REST surface used by CT
Marketing. Submitting a `spec_yaml` job produces an image (via Gemini
Nano Banana Pro by default) uploaded to S3, returned to callers as a
public HTTPS URL.

Public API:

    from cypherclaw.image_api import app, settings, JobsDB

The `app` symbol is a FastAPI ASGI application. `settings` carries
environment-loaded config. `JobsDB` is the SQLite-backed job store.
"""
from __future__ import annotations

from .app import create_app
from .config import Settings, settings
from .jobs_db import JobsDB
from .schemas import (
    InternalSpec,
    JobStatus,
    SubmitRequest,
    SubmitResponse,
    StatusResponse,
)

__all__ = [
    "InternalSpec",
    "JobStatus",
    "JobsDB",
    "Settings",
    "SubmitRequest",
    "SubmitResponse",
    "StatusResponse",
    "create_app",
    "settings",
]
