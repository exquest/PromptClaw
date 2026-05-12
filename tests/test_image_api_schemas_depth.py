"""Depth-2 tests for image_api.schemas [frac-0050]."""

from __future__ import annotations

import json
from pathlib import Path

import sdp.fractal as fractal

from cypherclaw.image_api.schemas import (
    ACTIVE_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    InternalSpec,
    InternalSpecProfile,
    JobLifecycleSummary,
    JobStatus,
    StatusResponse,
    build_internal_spec_profile,
    build_job_lifecycle_summary,
    is_terminal_status,
    summarize_internal_spec,
    summarize_status_response,
)


SCHEMAS_MODULE_PATH = Path("src/cypherclaw/image_api/schemas.py")


def test_is_terminal_status_classifies_lifecycle_values() -> None:
    assert TERMINAL_JOB_STATUSES == frozenset({JobStatus.completed, JobStatus.failed})
    assert ACTIVE_JOB_STATUSES == (
        JobStatus.queued,
        JobStatus.running,
        JobStatus.uploading,
    )

    assert is_terminal_status(JobStatus.completed) is True
    assert is_terminal_status(JobStatus.failed) is True
    assert is_terminal_status(JobStatus.queued) is False
    assert is_terminal_status(JobStatus.running) is False
    assert is_terminal_status(JobStatus.uploading) is False


def test_build_job_lifecycle_summary_for_completed_response() -> None:
    response = StatusResponse(
        job_id="job-1",
        status=JobStatus.completed,
        project_slug="ct-marketing",
        cost_usd=0.134,
        output_urls=[
            "https://bucket.s3.us-west-2.amazonaws.com/jobs/job-1/a.png",
            "https://bucket.s3.us-west-2.amazonaws.com/jobs/job-1/b.png",
        ],
        content_piece_id=42,
    )

    summary = build_job_lifecycle_summary(response)

    assert isinstance(summary, JobLifecycleSummary)
    assert summary.job_id == "job-1"
    assert summary.project_slug == "ct-marketing"
    assert summary.status == JobStatus.completed
    assert summary.is_terminal is True
    assert summary.output_count == 2
    assert summary.has_outputs is True
    assert summary.has_error is False
    assert summary.cost_usd == 0.134
    assert summary.content_piece_id == 42
    assert summary.to_dict() == {
        "job_id": "job-1",
        "project_slug": "ct-marketing",
        "status": "completed",
        "is_terminal": True,
        "output_count": 2,
        "has_outputs": True,
        "has_error": False,
        "cost_usd": 0.134,
        "content_piece_id": 42,
    }


def test_build_job_lifecycle_summary_for_failed_response() -> None:
    response = StatusResponse(
        job_id="job-2",
        status=JobStatus.failed,
        project_slug="ct-marketing",
        error="gemini: safety filter blocked",
    )

    summary = build_job_lifecycle_summary(response)

    assert summary.status == JobStatus.failed
    assert summary.is_terminal is True
    assert summary.output_count == 0
    assert summary.has_outputs is False
    assert summary.has_error is True
    assert summary.cost_usd is None
    assert summary.content_piece_id is None


def test_build_internal_spec_profile_derives_image_metadata() -> None:
    spec = InternalSpec(
        project="ct-marketing",
        prompt="  A dramatic\nhero image for launch  ",
        style="editorial",
        width=2048,
        height=1024,
        filename="hero.png",
        content_piece_id=7,
        model_override="gemini-3-pro-image-preview",
    )

    profile = build_internal_spec_profile(spec, prompt_preview_chars=15)

    assert isinstance(profile, InternalSpecProfile)
    assert profile.project == "ct-marketing"
    assert profile.filename == "hero.png"
    assert profile.width == 2048
    assert profile.height == 1024
    assert profile.pixel_count == 2_097_152
    assert profile.megapixels == 2.097
    assert profile.prompt_preview == "A dramatic hero"
    assert profile.prompt_length == len("A dramatic hero image for launch")
    assert profile.has_style is True
    assert profile.style == "editorial"
    assert profile.model_override == "gemini-3-pro-image-preview"
    assert profile.content_piece_id == 7


def test_schema_summaries_are_json_safe() -> None:
    status = StatusResponse(
        job_id="job-3",
        status=JobStatus.queued,
        project_slug="smoke",
    )
    status_summary = summarize_status_response(status)
    json.dumps(status_summary)

    assert status_summary["status"] == "queued"
    assert status_summary["is_terminal"] is False
    assert status_summary["has_outputs"] is False

    spec = InternalSpec(
        project="smoke",
        prompt="A single product photo",
        width=1024,
        height=768,
        filename="image.png",
    )
    spec_summary = summarize_internal_spec(spec, prompt_preview_chars=8)
    json.dumps(spec_summary)

    assert spec_summary["project"] == "smoke"
    assert spec_summary["filename"] == "image.png"
    assert spec_summary["width"] == 1024
    assert spec_summary["height"] == 768
    assert spec_summary["pixel_count"] == 786_432
    assert spec_summary["megapixels"] == 0.786
    assert spec_summary["prompt_preview"] == "A single"
    assert spec_summary["has_style"] is False


def test_image_api_schemas_module_reaches_depth_two() -> None:
    module = fractal.classify_depth(SCHEMAS_MODULE_PATH)
    assert module.depth >= 2, (
        f"expected schemas.py depth >= 2, got {module.depth}: {module.reason}"
    )
