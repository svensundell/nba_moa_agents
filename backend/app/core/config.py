"""Centralised application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
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
    log_level: str = Field(default="INFO")
    allowed_origins: str = Field(default="http://localhost:5173")

    groq_api_key: str = Field(default="")
    brave_api_key: str = Field(default="")
    balldontlie_api_key: str = Field(default="")
    reddit_user_agent: str = Field(default="")

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def has_brave(self) -> bool:
        return bool(self.brave_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
