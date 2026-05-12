"""Parse the two `spec_yaml` shapes that CT Marketing sends.

Shape A — explicit prompt
    project: hat
    prompt: "..."
    style: modern
    dimensions: 1024x768
    filename: hero.jpg
    content_piece_id: 42

Shape B — content-derived (no prompt; we infer from title/description)
    project: cascadian-tickets
    content_type: blog
    title: "..."
    description: "..."
    media_type: hero_image
    platform: blog

Both shapes resolve to a single `InternalSpec`. We never call an LLM in
v1 for prompt derivation — a deterministic template covers it.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

import yaml

from .schemas import InternalSpec


class SpecParseError(ValueError):
    """Raised when neither YAML shape recognizes the input."""


_DIM_RE = re.compile(r"^\s*(\d{2,5})\s*[xX×]\s*(\d{2,5})\s*$")


def _parse_dimensions(value: object) -> tuple[int, int]:
    """Parse 'WxH' → (W, H). Returns (1024, 1024) on missing input."""
    if value is None or value == "":
        return (1024, 1024)
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return (int(value[0]), int(value[1]))
        except (TypeError, ValueError) as exc:
            raise SpecParseError(f"invalid dimensions {value!r}") from exc
    text = str(value)
    match = _DIM_RE.match(text)
    if not match:
        raise SpecParseError(
            f"dimensions must be 'WxH' (e.g. '1024x768'), got {value!r}"
        )
    return (int(match.group(1)), int(match.group(2)))


def _coerce_str(value: object, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _shape_a_prompt(doc: Mapping[str, Any]) -> str | None:
    """Shape A signal: an explicit `prompt` field."""
    prompt = doc.get("prompt")
    if isinstance(prompt, str) and prompt.strip():
        return prompt.strip()
    return None


def _shape_b_inferred_prompt(doc: Mapping[str, Any]) -> str | None:
    """Shape B: derive a prompt from title + description + media_type.

    Returns None when neither title nor description is present (so the
    caller can decide whether the input is malformed)."""
    title = _coerce_str(doc.get("title"), "title")
    description = _coerce_str(doc.get("description"), "description")
    media_type = _coerce_str(doc.get("media_type"), "media_type") or "image"
    content_type = _coerce_str(doc.get("content_type"), "content_type")
    platform = _coerce_str(doc.get("platform"), "platform")
    style_hint = _coerce_str(doc.get("style"), "style")

    if not title and not description:
        return None

    parts: list[str] = []
    article = "An" if media_type[:1].lower() in "aeiou" else "A"
    parts.append(f"{article} {media_type.replace('_', ' ')}")
    if title:
        parts.append(f'illustrating "{title}"')
    if description:
        parts.append(f"— {description.strip().rstrip('.')}.")
    if platform:
        parts.append(f"Composed for {platform}.")
    if content_type:
        parts.append(f"Treat as a {content_type} accompaniment.")
    if style_hint:
        parts.append(f"Style: {style_hint}.")

    return " ".join(parts).strip()


def parse_spec_yaml(raw: str, *, project_slug: str) -> InternalSpec:
    """Parse a spec_yaml string into an InternalSpec.

    Validates that ``project`` (when present) matches ``project_slug``;
    rejects unknown shapes. The ``project_slug`` arg always wins as the
    project name on the returned spec."""
    if not raw or not raw.strip():
        raise SpecParseError("spec_yaml is empty")

    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise SpecParseError(f"invalid YAML: {exc}") from exc

    if not isinstance(doc, Mapping):
        raise SpecParseError("spec_yaml must be a YAML mapping at the root")

    spec_project = _coerce_str(doc.get("project"), "project")
    if spec_project and spec_project != project_slug:
        raise SpecParseError(
            f"spec project={spec_project!r} disagrees with request project_slug={project_slug!r}"
        )

    prompt = _shape_a_prompt(doc) or _shape_b_inferred_prompt(doc)
    if not prompt:
        raise SpecParseError(
            "spec_yaml must include `prompt` (Shape A) or `title`/`description` (Shape B)"
        )

    width, height = _parse_dimensions(doc.get("dimensions"))

    filename = _coerce_str(doc.get("filename"), "filename") or "image.png"

    content_piece_id_raw = doc.get("content_piece_id")
    content_piece_id: int | None
    if content_piece_id_raw is None:
        content_piece_id = None
    else:
        try:
            content_piece_id = int(content_piece_id_raw)
        except (TypeError, ValueError) as exc:
            raise SpecParseError(
                f"content_piece_id must be an int, got {content_piece_id_raw!r}"
            ) from exc

    return InternalSpec(
        project=project_slug,
        prompt=prompt,
        style=_coerce_str(doc.get("style"), "style"),
        width=width,
        height=height,
        filename=filename,
        content_piece_id=content_piece_id,
        model_override=_coerce_str(doc.get("model"), "model"),
    )
