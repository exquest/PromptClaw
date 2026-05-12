"""Tests for image_api.app — FastAPI surface, end-to-end through TestClient.

Uses the create_app factory with WorkerHooks injection so no real Gemini
or S3 is involved. Background tasks run inline within TestClient context."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from cypherclaw.image_api.app import create_app
from cypherclaw.image_api.config import Settings
from cypherclaw.image_api.gemini_backend import GenerationResult, GeminiBackendError
from cypherclaw.image_api.jobs_db import JobsDB
from cypherclaw.image_api.s3_uploader import UploadResult
from cypherclaw.image_api.schemas import InternalSpec
from cypherclaw.image_api.worker import WorkerHooks


def _settings(tmp_path) -> Settings:
    return Settings(jobs_db_path=str(tmp_path / "jobs.db"))


def _ok_generate(spec: InternalSpec) -> GenerationResult:
    return GenerationResult(
        image_bytes=b"\x89PNG\r\n\x1a\n",
        content_type="image/png",
        cost_usd=0.134,
        model_used="gemini-3-pro-image-preview",
    )


def _ok_upload(job_id: str, filename: str, body: bytes, ct: str) -> UploadResult:
    url = f"https://test-bucket.s3.us-west-2.amazonaws.com/jobs/{job_id}/{filename}"
    return UploadResult(bucket="test-bucket", key=f"jobs/{job_id}/{filename}", url=url, bytes_uploaded=len(body))


@pytest.fixture
def client(tmp_path):
    s = _settings(tmp_path)
    db = JobsDB(s.jobs_db_path)
    hooks = WorkerHooks(generate=_ok_generate, upload=_ok_upload)
    app = create_app(s=s, db=db, hooks=hooks)
    with TestClient(app) as tc:
        yield tc, db


# ---------------------------------------------------------------------------
# Healthz
# ---------------------------------------------------------------------------

class TestHealthz:
    def test_returns_200_with_bucket(self, client):
        tc, _ = client
        r = tc.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "bucket" in body


# ---------------------------------------------------------------------------
# Submit — Shape A
# ---------------------------------------------------------------------------

class TestSubmitShapeA:
    def test_returns_202_with_job_id(self, client):
        tc, _ = client
        spec = "prompt: 'a hero image'\ndimensions: 1024x768\nfilename: hero.jpg"
        r = tc.post("/api/v1/jobs", json={"spec_yaml": spec, "project_slug": "hat"})
        assert r.status_code == 202
        body = r.json()
        assert body["job_id"]
        assert body["project_slug"] == "hat"
        assert body["status"] == "queued"
        assert body["cost_usd"] is None

    def test_polling_eventually_returns_completed(self, client):
        tc, db = client
        spec = "prompt: 'simple'"
        r = tc.post("/api/v1/jobs", json={"spec_yaml": spec, "project_slug": "p"})
        job_id = r.json()["job_id"]

        # Background task ran inline-ish; poll until terminal or budget out.
        deadline = time.time() + 5.0
        body = None
        while time.time() < deadline:
            poll = tc.get(f"/api/v1/jobs/{job_id}")
            assert poll.status_code == 200
            body = poll.json()
            if body["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)
        assert body is not None
        assert body["status"] == "completed"
        assert body["output_urls"]
        assert body["output_urls"][0].startswith("https://test-bucket.s3.")
        assert body["cost_usd"] == 0.134


# ---------------------------------------------------------------------------
# Submit — Shape B (content-derived)
# ---------------------------------------------------------------------------

class TestSubmitShapeB:
    def test_accepts_content_derived(self, client):
        tc, _ = client
        spec = (
            "content_type: blog\n"
            "title: '5 ways to handle last-minute event changes'\n"
            "description: 'Short outline of the post body'\n"
            "media_type: hero_image\n"
            "platform: blog\n"
        )
        r = tc.post(
            "/api/v1/jobs",
            json={"spec_yaml": spec, "project_slug": "cascadian-tickets"},
        )
        assert r.status_code == 202


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------

class TestSubmitErrors:
    def test_400_on_malformed_yaml(self, client):
        tc, _ = client
        r = tc.post(
            "/api/v1/jobs",
            json={"spec_yaml": "media_type: hero_image", "project_slug": "p"},
        )
        # No prompt and no title → 400
        assert r.status_code == 400
        assert "prompt" in r.json()["detail"]

    def test_422_on_missing_required_fields(self, client):
        tc, _ = client
        r = tc.post("/api/v1/jobs", json={"spec_yaml": "prompt: x"})
        assert r.status_code == 422  # missing project_slug


# ---------------------------------------------------------------------------
# Status — unknown id
# ---------------------------------------------------------------------------

class TestStatusUnknownId:
    def test_404_on_unknown_job_id(self, client):
        tc, _ = client
        r = tc.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Failure path through the worker surfaces in poll
# ---------------------------------------------------------------------------

class TestFailingWorker:
    def test_status_failed_with_error_field(self, tmp_path):
        s = _settings(tmp_path)
        db = JobsDB(s.jobs_db_path)

        def refuse(spec):
            raise GeminiBackendError("blocked by safety")

        app = create_app(
            s=s,
            db=db,
            hooks=WorkerHooks(generate=refuse, upload=_ok_upload),
        )
        with TestClient(app) as tc:
            r = tc.post(
                "/api/v1/jobs",
                json={"spec_yaml": "prompt: forbidden", "project_slug": "p"},
            )
            jid = r.json()["job_id"]
            deadline = time.time() + 5.0
            body = None
            while time.time() < deadline:
                body = tc.get(f"/api/v1/jobs/{jid}").json()
                if body["status"] in ("completed", "failed"):
                    break
                time.sleep(0.05)
            assert body["status"] == "failed"
            assert "safety" in (body.get("error") or "")
            assert body["output_urls"] == []
