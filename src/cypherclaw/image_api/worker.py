"""Worker that walks a job through queued → running → uploading → completed.

Designed so the route handler can call `submit_for_processing(job_id)`
and return immediately; the actual work happens in a background task.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from . import gemini_backend, s3_uploader
from .config import Settings, settings as default_settings
from .gemini_backend import GeminiBackendError
from .jobs_db import JobsDB, JobRecord
from .schemas import InternalSpec, JobStatus
from .spec_parser import SpecParseError, parse_spec_yaml

logger = logging.getLogger(__name__)


# Hooks let tests inject fakes without monkey-patching modules.
GenerateFn = Callable[[InternalSpec], "gemini_backend.GenerationResult"]
UploadFn = Callable[[str, str, bytes, str], "s3_uploader.UploadResult"]


@dataclass
class WorkerHooks:
    """Test injection seam. Production passes None for both."""

    generate: Optional[GenerateFn] = None
    upload: Optional[UploadFn] = None


def process_job_sync(
    job_id: str,
    *,
    db: JobsDB,
    s: Optional[Settings] = None,
    hooks: Optional[WorkerHooks] = None,
) -> JobRecord:
    """Synchronous core. Idempotent for already-terminal jobs.

    Tests call this directly. The async wrapper below schedules it on a
    thread pool so it doesn't block the event loop."""
    s = s or default_settings
    hooks = hooks or WorkerHooks()

    rec = db.get(job_id)
    if rec is None:
        raise KeyError(job_id)
    if rec.status in (JobStatus.completed, JobStatus.failed):
        return rec

    # 1) parse
    try:
        spec = parse_spec_yaml(rec.spec_yaml, project_slug=rec.project_slug)
    except SpecParseError as exc:
        return db.update_status(job_id, JobStatus.failed, error=f"spec: {exc}")

    # 2) generate
    db.update_status(job_id, JobStatus.running)
    generator: GenerateFn = hooks.generate or (lambda spec: gemini_backend.generate_image(spec, s=s))
    try:
        gen = generator(spec)
    except GeminiBackendError as exc:
        return db.update_status(job_id, JobStatus.failed, error=f"gemini: {exc}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("unexpected generation error for %s", job_id)
        return db.update_status(job_id, JobStatus.failed, error=f"unexpected: {exc}")

    # 3) upload
    db.update_status(job_id, JobStatus.uploading, model_used=gen.model_used)
    uploader: UploadFn = hooks.upload or (
        lambda jid, fn, body, ct: s3_uploader.upload_image(
            job_id=jid, filename=fn, image_bytes=body, content_type=ct, s=s,
        )
    )
    try:
        result = uploader(job_id, spec.filename, gen.image_bytes, gen.content_type)
    except Exception as exc:  # noqa: BLE001
        logger.exception("S3 upload failed for %s", job_id)
        return db.update_status(job_id, JobStatus.failed, error=f"upload: {exc}")

    # 4) complete
    return db.update_status(
        job_id,
        JobStatus.completed,
        output_urls=[result.url],
        cost_usd=gen.cost_usd,
        model_used=gen.model_used,
    )


async def schedule_job(
    job_id: str,
    *,
    db: JobsDB,
    s: Optional[Settings] = None,
    hooks: Optional[WorkerHooks] = None,
) -> JobRecord:
    """Run `process_job_sync` on the default thread executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: process_job_sync(job_id, db=db, s=s, hooks=hooks),
    )
