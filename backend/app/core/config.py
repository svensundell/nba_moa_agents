"""Centralised application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = Field(default="development")
    serve_frontend: bool = False
    log_level: str = Field(default="INFO")
    allowed_origins: str = Field(default="http://localhost:5173")
    public_origin: str = ""
    google_oauth_client_id: str = ""
    google_oauth_client_secret: SecretStr = SecretStr("")
    session_secret: SecretStr = SecretStr("")
    # When set, clients must send Authorization: Bearer <token> or X-App-Access-Token.
    app_access_token: str = Field(default="")

    demo_openrouter_key: SecretStr = SecretStr("")
    demo_daily_runs: int = Field(default=20, ge=1)

    balldontlie_api_key: str = Field(default="")

    # Primary SQL database for eval + memory stores.
    database_url: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/nba")
    db_echo: bool = Field(default=False)
    auto_migrate: bool = Field(default=True)
    memory_embedding_dim: int = Field(default=1536, ge=1)

    # Brief memory (RAG over past Daily Briefs for NBA Copilot).
    memory_enabled: bool = Field(default=True)
    memory_embedding_model: str = Field(default="openai/text-embedding-3-small")
    memory_default_days: int = Field(default=14, ge=1, le=365)
    memory_search_top_k: int = Field(default=6, ge=1, le=20)

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def google_sign_in(self) -> bool:
        return bool(
            self.google_oauth_client_id
            and self.google_oauth_client_secret.get_secret_value()
            and len(self.session_secret.get_secret_value()) >= 32
            and self.public_origin
        )

    @property
    def has_balldontlie(self) -> bool:
        return bool(self.balldontlie_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
