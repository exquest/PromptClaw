"""`python -m cypherclaw.image_api` entry point.

Equivalent to `uvicorn cypherclaw.image_api.app:app --host ... --port ...`
but lets us pick host/port from settings without a CLI."""
from __future__ import annotations

import uvicorn

from .config import settings


def main() -> None:
    from .app import create_app  # local import: defers DB-path init
    app = create_app()
    uvicorn.run(
        app,
        host=settings.listen_host,
        port=settings.listen_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
