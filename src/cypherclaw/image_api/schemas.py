"""Pydantic schemas for the image API.

`SubmitRequest` / `SubmitResponse` / `StatusResponse` match the wire
contract in `specs/external/cypherclaw-image-contract.md`. `InternalSpec`
is the normalized internal representation produced by `spec_parser` from
either YAML shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(str, Enum):
    """Lifecycle states. Only `completed` and `failed` are terminal."""

    queued = "queued"
    running = "running"
    uploading = "uploading"
    completed = "completed"
    failed = "failed"


TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.completed, JobStatus.failed}
)
ACTIVE_JOB_STATUSES: tuple[JobStatus, ...] = (
    JobStatus.queued,
    JobStatus.running,
    JobStatus.uploading,
)


def is_terminal_status(status: JobStatus) -> bool:
    """Return whether a job lifecycle status is terminal."""
    normalized = status
    if not isinstance(normalized, JobStatus):
        normalized = JobStatus(normalized)
    return normalized in TERMINAL_JOB_STATUSES


# ---------------------------------------------------------------------------
# Wire contract
# ---------------------------------------------------------------------------


class SubmitRequest(BaseModel):
    """POST /api/v1/jobs body."""

    model_config = ConfigDict(extra="forbid")

    spec_yaml: str = Field(min_length=1, description="YAML spec, Shape A or Shape B.")
    project_slug: str = Field(min_length=1, max_length=128)


class SubmitResponse(BaseModel):
    """202 Accepted response."""

    model_config = ConfigDict(extra="ignore")

    job_id: str
    status: JobStatus = JobStatus.queued
    project_slug: str
    cost_usd: Optional[float] = None


class StatusResponse(BaseModel):
    """GET /api/v1/jobs/{id} response."""

    model_config = ConfigDict(extra="ignore")

    job_id: str
    status: JobStatus
    project_slug: str
    cost_usd: Optional[float] = None
    output_urls: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    content_piece_id: Optional[int] = None


@dataclass(frozen=True)
class JobLifecycleSummary:
    """Operator-friendly lifecycle summary derived from a status response."""

    job_id: str
    project_slug: str
    status: JobStatus
    is_terminal: bool
    output_count: int
    has_outputs: bool
    has_error: bool
    cost_usd: Optional[float]
    content_piece_id: Optional[int]

    def to_dict(self) -> dict[str, object]:
        """Render the summary with enum values converted to strings."""
        payload: dict[str, object] = {
            "job_id": self.job_id,
            "project_slug": self.project_slug,
            "status": self.status.value,
            "is_terminal": self.is_terminal,
            "output_count": self.output_count,
            "has_outputs": self.has_outputs,
            "has_error": self.has_error,
            "content_piece_id": self.content_piece_id,
        }
        if self.cost_usd is not None:
            payload["cost_usd"] = self.cost_usd
        else:
            payload["cost_usd"] = None
        return payload


def build_job_lifecycle_summary(response: StatusResponse) -> JobLifecycleSummary:
    """Build a typed lifecycle summary from one status response."""
    output_count = len(response.output_urls)
    error_text = response.error or ""
    has_error = bool(error_text.strip())
    is_terminal = is_terminal_status(response.status)
    return JobLifecycleSummary(
        job_id=response.job_id,
        project_slug=response.project_slug,
        status=response.status,
        is_terminal=is_terminal,
        output_count=output_count,
        has_outputs=output_count > 0,
        has_error=has_error,
        cost_usd=response.cost_usd,
        content_piece_id=response.content_piece_id,
    )


def summarize_status_response(response: StatusResponse) -> dict[str, object]:
    """Return a JSON-safe status response summary."""
    summary = build_job_lifecycle_summary(response)
    payload = summary.to_dict()
    if summary.is_terminal:
        payload["is_terminal"] = True
    return payload


# ---------------------------------------------------------------------------
# Internal normalized spec
# ---------------------------------------------------------------------------


class InternalSpec(BaseModel):
    """Normalized form derived from either YAML shape.

    `prompt` is always set by `spec_parser`: Shape A passes it through;
    Shape B derives it from title + description + media_type via a
    deterministic template (no LLM call needed for v1)."""

    model_config = ConfigDict(extra="forbid")

    project: str
    prompt: str = Field(min_length=1)
    style: Optional[str] = None
    width: int = 1024
    height: int = 1024
    filename: str = "image.png"
    content_piece_id: Optional[int] = None
    model_override: Optional[str] = None


@dataclass(frozen=True)
class InternalSpecProfile:
    """Operator-friendly image metadata derived from an internal spec."""

    project: str
    filename: str
    width: int
    height: int
    pixel_count: int
    megapixels: float
    prompt_preview: str
    prompt_length: int
    has_style: bool
    style: Optional[str]
    model_override: Optional[str]
    content_piece_id: Optional[int]

    def to_dict(self) -> dict[str, object]:
        """Render the profile as a JSON-safe dictionary."""
        payload: dict[str, object] = {
            "project": self.project,
            "filename": self.filename,
            "width": self.width,
            "height": self.height,
            "pixel_count": self.pixel_count,
            "megapixels": self.megapixels,
            "prompt_preview": self.prompt_preview,
            "prompt_length": self.prompt_length,
            "has_style": self.has_style,
            "style": self.style,
            "content_piece_id": self.content_piece_id,
        }
        if self.model_override is not None:
            payload["model_override"] = self.model_override
        else:
            payload["model_override"] = None
        return payload


def _single_line_prompt(prompt: str) -> str:
    """Collapse prompt whitespace for log-friendly summaries."""
    parts = prompt.split()
    if not parts:
        return ""
    return " ".join(parts)


def build_internal_spec_profile(
    spec: InternalSpec,
    *,
    prompt_preview_chars: int = 96,
) -> InternalSpecProfile:
    """Build a typed image metadata profile from a normalized spec."""
    prompt = _single_line_prompt(spec.prompt)
    preview_budget = max(1, prompt_preview_chars)
    pixel_count = spec.width * spec.height
    megapixels = round(pixel_count / 1_000_000, 3)
    has_style = bool(spec.style)
    return InternalSpecProfile(
        project=spec.project,
        filename=spec.filename,
        width=spec.width,
        height=spec.height,
        pixel_count=pixel_count,
        megapixels=megapixels,
        prompt_preview=prompt[:preview_budget],
        prompt_length=len(prompt),
        has_style=has_style,
        style=spec.style,
        model_override=spec.model_override,
        content_piece_id=spec.content_piece_id,
    )


def summarize_internal_spec(
    spec: InternalSpec,
    *,
    prompt_preview_chars: int = 96,
) -> dict[str, object]:
    """Return a JSON-safe internal spec profile summary."""
    profile = build_internal_spec_profile(
        spec,
        prompt_preview_chars=prompt_preview_chars,
    )
    payload = profile.to_dict()
    if profile.prompt_preview:
        payload["prompt_preview"] = profile.prompt_preview
    return payload
