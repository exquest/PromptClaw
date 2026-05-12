"""Tests for image_api.jobs_db — SQLite job state."""
from __future__ import annotations

import time

import pytest

from cypherclaw.image_api.jobs_db import JobsDB
from cypherclaw.image_api.schemas import JobStatus


@pytest.fixture
def db(tmp_path):
    return JobsDB(tmp_path / "jobs.db")


class TestInsertGet:
    def test_insert_creates_queued_record(self, db):
        rec = db.insert(job_id="j1", project_slug="proj", spec_yaml="prompt: x")
        assert rec.job_id == "j1"
        assert rec.status == JobStatus.queued
        assert rec.output_urls == []
        assert rec.cost_usd is None
        assert rec.error is None

    def test_insert_round_trips_via_get(self, db):
        db.insert(job_id="j1", project_slug="proj", spec_yaml="prompt: x", content_piece_id=42)
        rec = db.get("j1")
        assert rec is not None
        assert rec.content_piece_id == 42

    def test_get_unknown_returns_none(self, db):
        assert db.get("missing") is None

    def test_created_and_updated_set_to_now(self, db):
        rec = db.insert(job_id="j1", project_slug="p", spec_yaml="x", now=1000.0)
        assert rec.created_at == 1000.0
        assert rec.updated_at == 1000.0


class TestUpdateStatus:
    def test_running_transition(self, db):
        db.insert(job_id="j1", project_slug="p", spec_yaml="x")
        rec = db.update_status("j1", JobStatus.running, now=2000.0)
        assert rec.status == JobStatus.running
        assert rec.updated_at == 2000.0

    def test_completed_with_output_urls(self, db):
        db.insert(job_id="j1", project_slug="p", spec_yaml="x")
        rec = db.update_status(
            "j1",
            JobStatus.completed,
            output_urls=["https://example.com/a.jpg", "https://example.com/a@2x.jpg"],
            cost_usd=0.134,
            model_used="gemini-3-pro-image-preview",
        )
        assert rec.status == JobStatus.completed
        assert rec.output_urls == ["https://example.com/a.jpg", "https://example.com/a@2x.jpg"]
        assert rec.cost_usd == 0.134
        assert rec.model_used == "gemini-3-pro-image-preview"

    def test_failed_with_error(self, db):
        db.insert(job_id="j1", project_slug="p", spec_yaml="x")
        rec = db.update_status("j1", JobStatus.failed, error="gemini refused")
        assert rec.status == JobStatus.failed
        assert rec.error == "gemini refused"

    def test_update_unknown_raises(self, db):
        with pytest.raises(KeyError):
            db.update_status("missing", JobStatus.running)


class TestListPending:
    def test_excludes_terminal_states(self, db):
        db.insert(job_id="a", project_slug="p", spec_yaml="x", now=time.time())
        db.insert(job_id="b", project_slug="p", spec_yaml="x", now=time.time())
        db.insert(job_id="c", project_slug="p", spec_yaml="x", now=time.time())
        db.update_status("b", JobStatus.completed, output_urls=["u"])
        db.update_status("c", JobStatus.failed, error="x")
        pending = db.list_pending()
        ids = [r.job_id for r in pending]
        assert ids == ["a"]

    def test_oldest_first(self, db):
        db.insert(job_id="a", project_slug="p", spec_yaml="x", now=1000.0)
        db.insert(job_id="b", project_slug="p", spec_yaml="x", now=2000.0)
        pending = db.list_pending()
        assert [r.job_id for r in pending] == ["a", "b"]


class TestPersistence:
    def test_db_survives_reopen(self, tmp_path):
        path = tmp_path / "jobs.db"
        db1 = JobsDB(path)
        db1.insert(job_id="j1", project_slug="p", spec_yaml="x")
        db2 = JobsDB(path)
        rec = db2.get("j1")
        assert rec is not None
        assert rec.job_id == "j1"

    def test_creates_parent_dir(self, tmp_path):
        nested = tmp_path / "deep" / "nest" / "jobs.db"
        db = JobsDB(nested)
        db.insert(job_id="j1", project_slug="p", spec_yaml="x")
        assert nested.exists()
