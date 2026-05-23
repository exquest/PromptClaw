"""FastAPI app exposing composer validation endpoints."""

from __future__ import annotations

from fastapi import FastAPI, status

from .schemas import (
    MorphPhraseRequest,
    MorphPhraseResponse,
    build_morph_phrase_response,
)


def create_app() -> FastAPI:
    """Create the composer API app."""

    app = FastAPI(title="cypherclaw-composer-api", version="0.1.0")

    @app.post(
        "/api/v1/composer/morph-phrase",
        response_model=MorphPhraseResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def morph_phrase(payload: MorphPhraseRequest) -> MorphPhraseResponse:
        """Validate and normalize a morph phrase request."""

        return build_morph_phrase_response(payload)

    return app


__all__ = ["create_app"]
