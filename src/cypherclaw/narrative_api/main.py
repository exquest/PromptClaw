"""ASGI entry point exposing the narrative API as ``cypherclaw.narrative_api.main:app``.

Uvicorn (and other ASGI runners) target this module-level ``app`` object.
The ``/health`` route and the rest of the routes are wired in :mod:`.app`.
"""
from __future__ import annotations

from fastapi import FastAPI

from cypherclaw.first_boot import bootstrap_identity

from .app import create_app
from .settings import NarrativeSettings


def _build_app() -> FastAPI:
    bootstrap_identity()
    return create_app(auth_token=settings.auth_token or None)


settings: NarrativeSettings = NarrativeSettings()
app: FastAPI = _build_app()


__all__ = ["app", "settings"]
