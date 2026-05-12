"""FastAPI app exposing the contract from cypherclaw-image-contract.md.

Routes:
    POST /api/v1/jobs           — submit a spec, returns job_id
    GET  /api/v1/jobs/{job_id}  — poll status, returns output_urls when complete
    GET  /healthz               — liveness probe (no auth)

Auth: bearer token. The env var `CYPHERCLAW_IMAGE_API_KEYS` is a comma-
separated list of accepted keys (one per consumer so they can be rotated
or revoked individually). Empty/unset = auth disabled (warned at startup).
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status

from .config import Settings, settings as default_settings
from .jobs_db import JobsDB
from .schemas import (
    JobStatus,
    StatusResponse,
    SubmitRequest,
    SubmitResponse,
)
from .spec_parser import SpecParseError, parse_spec_yaml
from .worker import WorkerHooks, schedule_job

logger = logging.getLogger(__name__)


def _allowed_keys() -> set[str]:
    """Parse CYPHERCLAW_IMAGE_API_KEYS env var into a set. Comma-separated."""
    raw = os.environ.get("CYPHERCLAW_IMAGE_API_KEYS", "").strip()
    if not raw:
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}


def _require_bearer(authorization: str | None = Header(default=None)) -> None:
    """Reject requests whose Authorization header doesn't match a known key.

    No-op if `CYPHERCLAW_IMAGE_API_KEYS` is unset (development mode). At
    startup we log a warning so operators don't ship that to prod.
    """
    keys = _allowed_keys()
    if not keys:
        return  # auth disabled
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    if token not in keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_app(
    *,
    s: Optional[Settings] = None,
    db: Optional[JobsDB] = None,
    hooks: Optional[WorkerHooks] = None,
) -> FastAPI:
    """Factory so tests can inject a temp DB + fake worker hooks."""
    s = s or default_settings
    db = db or JobsDB(s.jobs_db_path)

    app = FastAPI(title="cypherclaw-image-api", version="1.0.0")

    if not _allowed_keys():
        logger.warning(
            "CYPHERCLAW_IMAGE_API_KEYS unset — bearer auth is DISABLED. "
            "Set this env var (comma-separated keys) before exposing publicly."
        )

    @app.get("/healthz")
    def healthz() -> dict:
        # Healthz intentionally has no auth so probes / monitoring can hit it.
        return {"status": "ok", "bucket": s.s3_bucket, "region": s.s3_region}

    @app.post(
        "/api/v1/jobs",
        response_model=SubmitResponse,
        status_code=202,
        dependencies=[Depends(_require_bearer)],
    )
    async def submit_job(payload: SubmitRequest, background: BackgroundTasks) -> SubmitResponse:
        # Validate the spec eagerly so callers get a 400 on malformed
        # YAML instead of a job that immediately transitions to failed.
        try:
            spec = parse_spec_yaml(payload.spec_yaml, project_slug=payload.project_slug)
        except SpecParseError as exc:
            raise HTTPException(status_code=400, detail=f"invalid spec_yaml: {exc}")

        job_id = str(uuid.uuid4())
        db.insert(
            job_id=job_id,
            project_slug=payload.project_slug,
            spec_yaml=payload.spec_yaml,
            content_piece_id=spec.content_piece_id,
        )

        background.add_task(_run_job_safely, job_id, db, s, hooks)

        return SubmitResponse(
            job_id=job_id,
            status=JobStatus.queued,
            project_slug=payload.project_slug,
        )

    @app.get(
        "/api/v1/jobs/{job_id}",
        response_model=StatusResponse,
        dependencies=[Depends(_require_bearer)],
    )
    def get_job(job_id: str) -> StatusResponse:
        rec = db.get(job_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"job {job_id} not found")
        return StatusResponse(
            job_id=rec.job_id,
            status=rec.status,
            project_slug=rec.project_slug,
            cost_usd=rec.cost_usd,
            output_urls=list(rec.output_urls),
            error=rec.error,
            content_piece_id=rec.content_piece_id,
        )

    return app


async def _run_job_safely(
    job_id: str,
    db: JobsDB,
    s: Settings,
    hooks: Optional[WorkerHooks],
) -> None:
    """Background task wrapper. Logs any unexpected exceptions instead
    of letting them tear down the FastAPI background runner."""
    try:
        await schedule_job(job_id, db=db, s=s, hooks=hooks)
    except Exception:  # noqa: BLE001
        logger.exception("background job %s failed", job_id)
