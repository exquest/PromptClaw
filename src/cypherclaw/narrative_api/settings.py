"""Runtime settings for the narrative API.

Values are read from environment variables prefixed with ``NARRATIVE_`` or from
a ``.env`` file in the working directory. Defaults match the historical
``__main__`` resolver behavior so existing deployments keep working.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class NarrativeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NARRATIVE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bind_host: str = "127.0.0.1"
    bind_port: int = 8765
    auth_token: str | None = None


__all__ = ["NarrativeSettings"]
