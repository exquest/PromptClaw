"""Smoke probe for the google.genai client default-auth path.

Provides typed helpers around the previous one-shot script so callers, tests,
and operator dashboards can drive `probe → summarize → render → main` without
re-implementing the conditional script logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GenAIProbeResult:
    ok: bool
    error: str
    model_count: int
    sampled_models: tuple[str, ...]


def create_genai_client(api_key: str | None = None) -> Any:
    from google import genai

    if api_key is None:
        return genai.Client()
    return genai.Client(api_key=api_key)


def list_model_names(client: Any, *, limit: int) -> tuple[str, ...]:
    names: list[str] = []
    for model in client.models.list():
        names.append(model.name)
        if len(names) >= limit:
            break
    return tuple(names)


def probe_genai_client(
    *, max_models: int = 1, client: Any | None = None
) -> GenAIProbeResult:
    try:
        active = client if client is not None else create_genai_client()
        names = list_model_names(active, limit=max_models)
        return GenAIProbeResult(
            ok=True, error="", model_count=len(names), sampled_models=names
        )
    except Exception as exc:
        return GenAIProbeResult(
            ok=False, error=str(exc), model_count=0, sampled_models=()
        )


def summarize_probe_result(result: GenAIProbeResult) -> dict[str, object]:
    return {
        "ok": result.ok,
        "error": result.error,
        "model_count": result.model_count,
        "sampled_models": list(result.sampled_models),
    }


def format_probe_lines(result: GenAIProbeResult) -> tuple[str, ...]:
    if result.ok:
        head = "Successfully created client without explicit API key."
        body = tuple(f"Model: {name}" for name in result.sampled_models)
        return (head, *body)
    return (f"Error: {result.error}",)


def main() -> int:
    result = probe_genai_client()
    for line in format_probe_lines(result):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
