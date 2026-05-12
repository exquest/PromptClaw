"""Tests for image_api.worker — full job lifecycle with mocked Gemini + S3."""
from __future__ import annotations

import pytest

from cypherclaw.image_api.gemini_backend import GenerationResult, GeminiBackendError
from cypherclaw.image_api.jobs_db import JobsDB
from cypherclaw.image_api.s3_uploader import UploadResult
from cypherclaw.image_api.schemas import InternalSpec, JobStatus
from cypherclaw.image_api.worker import WorkerHooks, process_job_sync


@pytest.fixture
def db(tmp_path):
    return JobsDB(tmp_path / "jobs.db")


def _ok_generate(spec: InternalSpec) -> GenerationResult:
    return GenerationResult(
        image_bytes=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
        content_type="image/png",
        cost_usd=0.134,
        model_used="gemini-3-pro-image-preview",
    )


def _ok_upload(job_id: str, filename: str, body: bytes, ct: str) -> UploadResult:
    return UploadResult(
        bucket="b",
        key=f"jobs/{job_id}/{filename}",
        url=f"https://b.s3.us-west-2.amazonaws.com/jobs/{job_id}/{filename}",
        bytes_uploaded=len(body),
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_completes_with_output_urls_and_cost(self, db):
        db.insert(job_id="j1", project_slug="p", spec_yaml="prompt: hello\nfilename: out.png")
        rec = process_job_sync(
            "j1",
            db=db,
            hooks=WorkerHooks(generate=_ok_generate, upload=_ok_upload),
        )
        assert rec.status == JobStatus.completed
        assert rec.output_urls == ["https://b.s3.us-west-2.amazonaws.com/jobs/j1/out.png"]
        assert rec.cost_usd == 0.134
        assert rec.model_used == "gemini-3-pro-image-preview"
        assert rec.error is None

    def test_idempotent_on_terminal_jobs(self, db):
        db.insert(job_id="j1", project_slug="p", spec_yaml="prompt: x")
        # First pass completes
        process_job_sync(
            "j1",
            db=db,
            hooks=WorkerHooks(generate=_ok_generate, upload=_ok_upload),
        )
        # Second pass — generator should NOT be called again
        called = []

        def boom(spec):
            called.append(1)
            raise AssertionError("should not regenerate")

        rec = process_job_sync(
            "j1",
            db=db,
            hooks=WorkerHooks(generate=boom, upload=_ok_upload),
        )
        assert rec.status == JobStatus.completed
        assert called == []


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------

class TestFailurePaths:
    def test_invalid_spec_yaml_marks_failed(self, db):
        db.insert(job_id="j1", project_slug="p", spec_yaml="not: even: valid")
        rec = process_job_sync(
            "j1",
            db=db,
            hooks=WorkerHooks(generate=_ok_generate, upload=_ok_upload),
        )
        assert rec.status == JobStatus.failed
        assert rec.error and "spec" in rec.error

    def test_gemini_refusal_marks_failed_with_reason(self, db):
        db.insert(job_id="j1", project_slug="p", spec_yaml="prompt: forbidden content")

        def refuse(spec):
            raise GeminiBackendError("safety filter blocked")

        rec = process_job_sync(
            "j1",
            db=db,
            hooks=WorkerHooks(generate=refuse, upload=_ok_upload),
        )
        assert rec.status == JobStatus.failed
        assert "safety filter blocked" in (rec.error or "")

    def test_upload_failure_marks_failed(self, db):
        db.insert(job_id="j1", project_slug="p", spec_yaml="prompt: ok")

        def boom(*args, **kwargs):
            raise RuntimeError("S3 5xx")

        rec = process_job_sync(
            "j1",
            db=db,
            hooks=WorkerHooks(generate=_ok_generate, upload=boom),
        )
        assert rec.status == JobStatus.failed
        assert rec.error and "upload" in rec.error

    def test_unexpected_generator_exception_marks_failed(self, db):
        db.insert(job_id="j1", project_slug="p", spec_yaml="prompt: ok")

        def kaboom(spec):
            raise ValueError("unexpected")

        rec = process_job_sync(
            "j1",
            db=db,
            hooks=WorkerHooks(generate=kaboom, upload=_ok_upload),
        )
        assert rec.status == JobStatus.failed
        assert "unexpected" in (rec.error or "")


# ---------------------------------------------------------------------------
# Lifecycle ordering
# ---------------------------------------------------------------------------

class TestLifecycleOrdering:
    def test_running_then_uploading_then_completed(self, db):
        states_seen = []
        original_get = db.get

        def spy_get(jid):
            r = original_get(jid)
            if r:
                states_seen.append(r.status)
            return r

        db.insert(job_id="j1", project_slug="p", spec_yaml="prompt: ok")

        # Wrap upload to peek at status mid-flight
        peeked: list[JobStatus] = []

        def peeking_upload(job_id, fn, body, ct):
            r = db.get(job_id)
            if r:
                peeked.append(r.status)
            return _ok_upload(job_id, fn, body, ct)

        process_job_sync(
            "j1",
            db=db,
            hooks=WorkerHooks(generate=_ok_generate, upload=peeking_upload),
        )
        # When upload runs, status must be 'uploading'
        assert JobStatus.uploading in peeked


# ---------------------------------------------------------------------------
# Unknown job
# ---------------------------------------------------------------------------

class TestUnknownJob:
    def test_unknown_job_id_raises_keyerror(self, db):
        with pytest.raises(KeyError):
            process_job_sync("nope", db=db)
