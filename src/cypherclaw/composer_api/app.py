"""FastAPI app exposing composer validation endpoints."""

from __future__ import annotations

from fastapi import FastAPI, status

from .schemas import (
    GeneratedMorphPhraseResponse,
    MorphPhraseRequest,
    MorphPhraseResponse,
    build_generated_morph_phrase_response,
    build_morph_phrase_response,
)


MorphPhraseRouteResponse = GeneratedMorphPhraseResponse | MorphPhraseResponse


def create_app() -> FastAPI:
    """Create the composer API app."""

    app = FastAPI(title="cypherclaw-composer-api", version="0.1.0")

    @app.post(
        "/api/v1/composer/morph-phrase",
        response_model=MorphPhraseRouteResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def morph_phrase(payload: MorphPhraseRequest) -> MorphPhraseRouteResponse:
        """Validate and optionally generate a morph phrase request."""

        if payload.phrase_curve is not None:
            return build_generated_morph_phrase_response(payload)
        return build_morph_phrase_response(payload)

    return app


__all__ = ["MorphPhraseRouteResponse", "create_app"]
