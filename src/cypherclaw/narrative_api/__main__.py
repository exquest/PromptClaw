"""Entry point so ``python -m cypherclaw.narrative_api`` boots the API."""
from __future__ import annotations

import os

import uvicorn

from .app import create_app
from .settings import NarrativeSettings


def _resolve_host(settings: NarrativeSettings | None = None) -> str:
    return (settings or NarrativeSettings()).bind_host


def _resolve_port(settings: NarrativeSettings | None = None) -> int:
    return (settings or NarrativeSettings()).bind_port


def main() -> None:
    from cypherclaw.first_boot import bootstrap_identity
    bootstrap_identity()
    settings = NarrativeSettings()
    app = create_app(auth_token=settings.auth_token or None)
    uvicorn.run(
        app,
        host=settings.bind_host,
        port=settings.bind_port,
        log_level=os.environ.get("NARRATIVE_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
